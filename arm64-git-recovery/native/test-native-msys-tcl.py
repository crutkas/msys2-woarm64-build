"""Qualify installed MSYS Tcl core APIs without substituting the MinGW GUI interpreter."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

from native_job_runner import run_observed
from sources import ContractError, digest, inventory, verify_tree


def configured_msys_path(path):
    match = re.fullmatch(r"([A-Za-z]):/(.*)", Path(path).resolve().as_posix())
    if match is None:
        raise ContractError("The configured MSYS drive view requires an owned local-drive path")
    return "/" + match[1].lower() + "/" + match[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stage", "manifest", "compiler-receipt", "zlib-stage", "zlib-manifest",
                 "native-job-prefix", "runtime-fstab", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--fstab-sha256", required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if args.output.exists() or digest(args.manifest) != args.sha256:
        raise ContractError("Native Tcl API control requires a fresh output and exact stage receipt")
    if digest(args.runtime_fstab) != args.fstab_sha256:
        raise ContractError("The exact approved private MSYS runtime mount configuration is required")
    stage_record = json.loads(args.manifest.read_text())
    if (stage_record.get("package") != "tcl-msys" or stage_record.get("version") != "8.6.12"
            or stage_record.get("status") != "native-msys-tcl-built-installed-tests-pending"
            or stage_record.get("inputs_unchanged") is not True
            or stage_record.get("compiler_receipt_sha256") != digest(args.compiler_receipt)):
        raise ContractError("The actual coherent MSYS Tcl stage is required")
    verify_tree(args.stage, args.manifest)
    verify_tree(args.zlib_stage, args.zlib_manifest)
    compiler = json.loads(args.compiler_receipt.read_text())
    verify_tree(compiler["prefix"], args.compiler_receipt)
    relocated = args.output / "relocated"
    shutil.copytree(args.stage, relocated)
    runtime = relocated / "usr/bin"
    runtime_sources = [Path(compiler["prefix"]) / "bin/msys-2.0.dll", args.zlib_stage / "usr/bin/msys-z.dll"]
    for path in runtime_sources:
        if (runtime / path.name).exists():
            raise ContractError("Runtime augmentation may not overwrite an installed Tcl file")
        shutil.copyfile(path, runtime / path.name)
    (relocated / "etc").mkdir()
    shutil.copyfile(args.runtime_fstab, relocated / "etc/fstab")
    relocated_files = inventory(relocated)
    (args.output / "native-exits").mkdir()
    fixture = Path(__file__).parent / "fixtures/native-msys-tcl-core.tcl"
    private_fixture = args.output / "fixture.tcl"
    shutil.copyfile(fixture, private_fixture)
    capture = Path(__file__).with_name("capture-native-exception.py")
    executable = relocated / "usr/bin/tclsh8.6.exe"
    identities = {str(path): digest(path) for path in
                  (args.manifest, args.compiler_receipt, args.zlib_manifest, fixture, capture, Path(__file__),
                   Path(__file__).with_name("native_job_runner.py"), args.runtime_fstab, *runtime_sources)}
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (relocated / "usr/bin", runtime,
                                                 Path(os.environ["SystemRoot"]) / "System32"))),
                "TCL_LIBRARY": configured_msys_path(relocated / "usr/lib/tcl8.6"),
                "TCLLIBPATH": configured_msys_path(relocated / "usr/lib"),
                "HOME": str(args.output), "USERPROFILE": str(args.output),
                "TEMP": str(args.output), "TMP": str(args.output),
                "WOARM64_NATIVE_TEST_ROOT": str(args.output), "WOARM64_NATIVE_ARG_CONVERSION": "none"})
    report = {"schema": 1, "status": "failed", "package": "tcl-msys", "input_identities": identities,
              "runtime_configuration": {"path": str(relocated / "etc/fstab"), "sha256": args.fstab_sha256,
                                        "scope": "Exact distro configuration in this private relocated runtime only; no SDK, registry or global mount changes"},
              "scope": "Installed native MSYS LP64 Tcl arithmetic/Unicode/file/zlib/Itcl/TDBC-core/thread APIs and actual DLL closure; no database connections, GUI, accounts or full-suite claim"}
    try:
        report["process"] = run_observed(
            [sys.executable, "-B", capture, "--executable", executable,
             "--path-directory", relocated / "usr/bin", "--runtime-directory", runtime,
             "--output", args.output / "capture", "--tcl-environment",
             configured_msys_path(private_fixture), configured_msys_path(args.output / "work")],
            cwd=args.output, env=env, log_path=args.output / "observer.log",
            result_path=args.output / "native-job.json", relay_records=args.output / "native-exits",
            timeout=60, driver_prefix=args.native_job_prefix)
        observed = json.loads((args.output / "capture/result.json").read_text())
        text = (args.output / "capture/stdout.bin").read_bytes() + (args.output / "capture/stderr.bin").read_bytes()
        if (not report["process"]["passed"] or observed["exit_code"] != 0 or observed["timed_out"]
                or b"native-msys-tcl-core-api-passed" not in text):
            raise ContractError("Installed native MSYS Tcl functional fixture failed")
        loaded = {}
        for row in observed["modules"]:
            path = Path(row["path"].removeprefix("\\\\?\\")).resolve()
            loaded[path.name.lower()] = {"path": str(path), "sha256": digest(path)}
        for name in ("libtcl8.6.dll", "libitcl4.2.2.dll", "libtdbc1.1.3.dll", "libthread2.8.7.dll"):
            row = loaded.get(name)
            if row is None or not Path(row["path"]).is_relative_to(relocated):
                raise ContractError(f"Required Tcl module was not loaded from the private stage: {name}")
            relative = Path(row["path"]).relative_to(relocated).as_posix()
            if row["sha256"] != stage_record["files"][relative]["sha256"]:
                raise ContractError("Loaded Tcl package DLL differs from its installed receipt")
        for path in runtime_sources:
            row = loaded.get(path.name.lower())
            if row is None or Path(row["path"]) != runtime / path.name or row["sha256"] != digest(path):
                raise ContractError("Tcl loaded an unexpected runtime or zlib DLL")
        if inventory(relocated) != relocated_files:
            raise ContractError("Tcl execution changed its private relocated runtime or payload")
        if (args.output / "work/roundtrip-\u03bb.txt").read_bytes() != "native Tcl \u03bb \u96ea caf\u00e9".encode():
            raise ContractError("Tcl did not preserve the actual Unicode filename and UTF-8 contents")
        report.update({"status": "installed-native-msys-tcl-core-api-and-dll-closure-passed",
                       "loaded_modules": loaded, "stage_files": inventory(relocated)})
    finally:
        try:
            if any(digest(path) != sha for path, sha in identities.items()):
                raise ContractError("Tcl API fixture input or recipe changed")
            if digest(private_fixture) != digest(fixture):
                raise ContractError("The private Tcl fixture copy changed")
            verify_tree(args.stage, args.manifest)
            verify_tree(args.zlib_stage, args.zlib_manifest)
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
