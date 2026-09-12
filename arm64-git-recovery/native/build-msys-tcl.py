"""Build the actual pinned MSYS Tcl Unix port, distinct from the MinGW Git GUI Tcl."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from compiler_tools import require_msys_ucontext_receipt, support_identities, verify_support
from fido_build_inputs import retained_abi
from native_job_runner import run_observed
from pe_exports import export_names
from sources import ContractError, digest, inventory, verify_tree
from tcl_build_inputs import forward_dltest_ldflags


def verify_bootstrap(prefix, manifest):
    bootstrap = json.loads(manifest.read_text())
    if Path(bootstrap["prefix"]).resolve() != prefix.resolve():
        raise ContractError("Tcl bootstrap receipt identifies a different private prefix")
    if bootstrap.get("status") == "private-bootstrap-with-signature-verified-host-generators":
        base_ref = bootstrap["base_copy"]
        if digest(base_ref["path"]) != base_ref["sha256"]:
            raise ContractError("Original private bootstrap copy receipt changed")
        base = json.loads(Path(base_ref["path"]).read_text())
        if (base.get("status") != "private-ssh-bootstrap-byte-identical-not-executed"
                or Path(base["prefix"]).resolve() != prefix.resolve()):
            raise ContractError("Host generators must augment the declared owned bootstrap, not a shared prefix")
        packages = bootstrap["packages"]
        signature = bootstrap["signature_verification"]
        if (not packages or bootstrap["install"].get("raw_exit") != 0
                or bootstrap["install"].get("signature_policy") != "Required"
                or signature.get("raw_exit") != 0 or signature.get("valid_signatures") != len(packages)
                or len(signature.get("signers", [])) != len(packages)):
            raise ContractError("Every actual host-generator package must have a verified original signature")
        for item in [*bootstrap["evidence"], *packages, *[row["signature"] for row in packages]]:
            if digest(item["path"]) != item["sha256"]:
                raise ContractError("Host-generator archive, signature or install evidence changed")
        modified = {name for name, row in base["files"].items() if bootstrap["files"].get(name) != row}
        if not modified.issubset({"usr/share/info/dir", "var/log/pacman.log"}):
            raise ContractError("Generator installation unexpectedly changed an existing bootstrap program or input")
    elif bootstrap.get("status") != "private-ssh-bootstrap-byte-identical-not-executed":
        raise ContractError("Explicit verified private bootstrap input required")
    verify_tree(prefix, manifest)
    return bootstrap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "prefix", "compiler-receipt", "zlib-stage", "zlib-result",
                 "zlib-compiler", "bootstrap", "bootstrap-manifest", "patch", "native-job-prefix",
                 "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--compiler-ancestor", type=Path, action="append", default=[])
    parser.add_argument("--jobs", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    if os.name != "nt" or args.output.exists():
        raise ContractError("MSYS Tcl requires Windows and a fresh owned output")
    record = json.loads(args.manifest.read_text())
    if (record["source"]["id"] != "tcl-msys" or record["source"]["version"] != "8.6.12"
            or record["source"]["sha256"] != "26c995dd0f167e48b11961d891ee555f680c175f7173ff8cb829f4ebcde4c1a6"):
        raise ContractError("Use the actual pinned MSYS Tcl source, not MinGW Tcl 8.6.18")
    if digest(args.patch) != "322c7e17c63249fc5f6b0d89b1c77fa67406aa91f44efa4964be3f75bb271568":
        raise ContractError("MSYS Tcl requires its exact published source patch")
    verify_tree(args.source, args.manifest)
    compiler = json.loads(args.compiler_receipt.read_text())
    require_msys_ucontext_receipt(compiler)
    if Path(compiler["prefix"]).resolve() != args.prefix or compiler["source_target"]["Triple"] != "aarch64-pc-cygwin":
        raise ContractError("Tcl Unix port requires the real MSYS LP64 compiler/runtime")
    verify_tree(args.prefix, args.compiler_receipt)
    zlib = json.loads(args.zlib_result.read_text())
    if (zlib.get("package") != "zlib-msys" or
            zlib.get("status") != "native-msys-library-built-checked-bootstrap-driver"
            or zlib["compiler_receipt_sha256"] != digest(args.zlib_compiler)):
        raise ContractError("Tcl requires the genuine MSYS zlib cohort, not a MinGW substitute")
    verify_tree(args.zlib_stage, args.zlib_result)
    abi = retained_abi(args.compiler_receipt, args.zlib_compiler, args.compiler_ancestor)
    verify_bootstrap(args.bootstrap, args.bootstrap_manifest)
    script = Path(__file__).with_suffix(".sh")
    if b"\r" in script.read_bytes():
        raise ContractError("The maintained MSYS Tcl shell driver must use LF")
    identities = {str(path): digest(path) for path in
                  (args.manifest, args.compiler_receipt, args.zlib_result, args.zlib_compiler,
                   args.bootstrap_manifest, args.patch, script, Path(__file__),
                   Path(__file__).with_name("native_job_runner.py"), Path(__file__).with_name("tcl_build_inputs.py"))}
    args.output.mkdir(parents=True)
    for name in ("home", "temp", "native-exits"):
        (args.output / name).mkdir()
    source = args.output / "source"
    shutil.copytree(args.source, source)
    bundled_sqlite = source / "pkgs/sqlite3.36.0"
    if not bundled_sqlite.is_dir() or bundled_sqlite.is_symlink() or bundled_sqlite.is_junction():
        raise ContractError("Expected the exact bundled SQLite directory removed by the pinned Tcl recipe")
    removed = inventory(bundled_sqlite)
    shutil.rmtree(bundled_sqlite)
    test_makefile = source / "unix/dltest/Makefile.in"
    test_before = digest(test_makefile)
    test_makefile.write_text(forward_dltest_ldflags(test_makefile.read_text()), encoding="utf-8", newline="\n")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (args.prefix / "bin", args.zlib_stage / "usr/bin",
                                                 args.bootstrap / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                "TEMP": str(args.output / "temp"), "TMP": str(args.output / "temp"),
                "WOARM64_NATIVE_TEST_ROOT": str(args.output), "WOARM64_NATIVE_ARG_CONVERSION": "none"})
    support = support_identities(args.prefix / "bin/gcc.exe", args.prefix, env)
    command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
               args.output, args.prefix, args.zlib_stage, args.patch, str(args.jobs)]
    report = {"schema": 1, "status": "failed", "package": "tcl-msys", "version": "8.6.12",
              "source_manifest_sha256": digest(args.manifest), "compiler_receipt_sha256": digest(args.compiler_receipt),
              "input_identities": identities, "retained_zlib_abi": abi, "support": support,
              "command": list(map(str, command)), "removed_recipe_bundled_sqlite": removed,
              "dltest_link_flags_fix": {"path": "unix/dltest/Makefile.in", "before_sha256": test_before,
                                        "after_sha256": digest(test_makefile),
                                        "scope": "Preserve existing LDFLAGS in all14 upstream dynamic-load test links"},
              "scope": "Pinned MSYS Unix-port Tcl build/install, not MinGW GUI Tcl or complete test/package admission",
              "pending": ["Complete native Tcl suite and reviewed platform constraints",
                          "Installed native interpreter/extension/loaded-DLL proof", "Relocatable package metadata/aliases and provider admission"]}
    try:
        report["process"] = run_observed(
            command, cwd=args.output, env=env, log_path=args.output / "build.log",
            result_path=args.output / "native-job.json", relay_records=args.output / "native-exits",
            timeout=7200, driver_prefix=args.native_job_prefix)
        if not report["process"]["passed"]:
            raise ContractError("MSYS Tcl build/install or native child observation failed")
        stage = args.output / "stage"
        files = inventory(stage)
        for name in ("usr/bin/tclsh8.6.exe", "usr/lib/libtcl8.6.dll.a",
                     "usr/lib/libtclstub8.6.a", "usr/lib/tcl8.6/init.tcl", "usr/include/tcl.h"):
            if name not in files:
                raise ContractError(f"MSYS Tcl stage missing: {name}")
        core = [path for path in (stage / "usr/bin").glob("*.dll")
                if {"Tcl_CreateInterp", "Tcl_GetVersion", "Tcl_Init"}.issubset(export_names(path.read_bytes()))]
        if len(core) != 1:
            raise ContractError("Expected one real Tcl API DLL in the private stage")
        pe = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(stage), "-ReportPath", str(pe)], check=True, timeout=120)
        if json.loads(pe.read_text()).get("Passed") is not True:
            raise ContractError("MSYS Tcl stage native PE classification failed")
        report.update({"status": "native-msys-tcl-built-installed-tests-pending", "files": files,
                       "core_dll": str(core[0]), "working_source_files": inventory(source)})
    finally:
        try:
            if any(digest(path) != sha for path, sha in identities.items()):
                raise ContractError("Tcl immutable input or recipe changed")
            verify_tree(args.source, args.manifest)
            verify_tree(args.prefix, args.compiler_receipt)
            verify_tree(args.zlib_stage, args.zlib_result)
            verify_bootstrap(args.bootstrap, args.bootstrap_manifest)
            verify_support(support, args.prefix / "bin/gcc.exe", args.prefix, env)
            report["inputs_unchanged"] = True
        except (OSError, ContractError) as error:
            report.update({"status": "failed", "inputs_unchanged": False, "input_error": str(error)})
            raise
        finally:
            (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
