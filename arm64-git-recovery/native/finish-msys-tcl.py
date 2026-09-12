"""Finish an owned Tcl build after correcting only the Windows test executable target name."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from native_job_runner import run_observed
from sources import ContractError, digest, inventory
from tcl_build_inputs import forward_dltest_ldflags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build-result", "recipe-snapshot", "output", "native-job-prefix", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if args.output.exists() or digest(args.build_result) != args.sha256:
        raise ContractError("Tcl completion requires a new output and exact preserved failure result")
    original = json.loads(args.build_result.read_text())
    old = args.build_result.parent
    if (original.get("package") != "tcl-msys" or original.get("version") != "8.6.12"
            or original.get("status") != "failed" or original.get("inputs_unchanged") is not True
            or "No rule to make target 'tcltest'." not in (old / "build.log").read_text(errors="replace")):
        raise ContractError("Only the known post-build Tcl executable-target error is eligible for this continuation")
    snapshots = json.loads(args.recipe_snapshot.read_text())
    replacements = {Path(row["path"]).resolve(): row for row in snapshots}
    inputs = {}
    for path, sha in original["input_identities"].items():
        key = Path(path).resolve()
        actual = Path(replacements[key]["snapshot"]) if key in replacements else key
        if digest(actual) != sha:
            raise ContractError("Preserved Tcl input or original recipe identity changed")
        inputs[str(actual)] = sha
    command = original["command"]
    if len(command) != 9 or Path(command[4]).resolve() != old:
        raise ContractError("Unexpected original Tcl build invocation")
    bootstrap, prefix, zlib = Path(command[0]).parents[2], Path(command[5]), Path(command[6])
    external = {str(path): inventory(path) for path in (bootstrap, prefix, zlib)}
    build = old / "build"
    libraries = {str(path): digest(path) for path in build.rglob("*")
                 if path.is_file() and path.suffix in (".dll", ".a")
                 and not path.is_relative_to(build / "dltest")}
    if str(build / "libtcl8.6.dll") not in libraries or not (build / "tclsh.exe").is_file():
        raise ContractError("The actual native Tcl core must already be built")
    script = Path(__file__).with_suffix(".sh")
    if b"\r" in script.read_bytes():
        raise ContractError("Tcl completion shell script must be LF-only")
    inputs.update({str(path): digest(path) for path in
                   (args.build_result, args.recipe_snapshot, script, Path(__file__),
                    Path(__file__).with_name("native_job_runner.py"), Path(__file__).with_name("tcl_build_inputs.py"))})
    args.output.mkdir(parents=True)
    for name in ("home", "temp", "native-exits"):
        (args.output / name).mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    target_root = Path(os.path.commonpath((old, args.output)))
    if target_root == Path(target_root.anchor):
        raise ContractError("Tcl completion roots must share an owned non-root directory")
    env.update({"PATH": os.pathsep.join(map(str, (prefix / "bin", zlib / "usr/bin", build,
                                                 bootstrap / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp"),
                "WOARM64_NATIVE_TEST_ROOT": str(target_root), "WOARM64_NATIVE_ARG_CONVERSION": "none"})
    report = {"schema": 1, "status": "failed", "package": "tcl-msys", "version": "8.6.12",
              "original_build": {"path": str(args.build_result), "sha256": args.sha256},
              "compiler_receipt_sha256": original["compiler_receipt_sha256"],
              "source_manifest_sha256": original["source_manifest_sha256"],
              "input_identities": inputs, "existing_library_identities": libraries,
              "external_input_file_counts": {name: len(files) for name, files in external.items()},
              "scope": "Resume test-executable build and complete private installation; retain existing native core/package library bytes",
              "pending": original["pending"]}
    try:
        test_makefile = build / "dltest/Makefile"
        if test_makefile.exists():
            before = digest(test_makefile)
            test_makefile.write_text(forward_dltest_ldflags(test_makefile.read_text()), encoding="utf-8", newline="\n")
            report["dltest_link_flags_fix"] = {"path": str(test_makefile), "before_sha256": before,
                                              "after_sha256": digest(test_makefile)}
        argv = [bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(),
                old, args.output, prefix, zlib, str(args.jobs)]
        report["command"] = list(map(str, argv))
        report["process"] = run_observed(
            argv, cwd=args.output, env=env, log_path=args.output / "finish.log",
            result_path=args.output / "native-job.json", relay_records=args.output / "native-exits",
            timeout=3600, driver_prefix=args.native_job_prefix)
        if not report["process"]["passed"]:
            raise ContractError("Tcl test-executable build or private installation failed")
        stage = args.output / "stage"
        files = inventory(stage)
        for name in ("usr/bin/tclsh8.6.exe", "usr/lib/libtcl8.6.dll.a", "usr/lib/libtclstub8.6.a",
                     "usr/include/tcl.h", "usr/lib/tcl8.6/init.tcl"):
            if name not in files:
                raise ContractError(f"Tcl private installation is incomplete: {name}")
        pe = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(stage), "-ReportPath", str(pe)], check=True, timeout=120)
        if json.loads(pe.read_text()).get("Passed") is not True:
            raise ContractError("Tcl private stage native PE gate failed")
        report.update({"status": "native-msys-tcl-built-installed-tests-pending", "files": files})
    finally:
        try:
            if any(digest(path) != sha for path, sha in {**inputs, **libraries}.items()):
                raise ContractError("Tcl completion changed an existing library or immutable input")
            if any(inventory(path) != files for path, files in external.items()):
                raise ContractError("Tcl completion changed a bootstrap, SDK or zlib input tree")
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
