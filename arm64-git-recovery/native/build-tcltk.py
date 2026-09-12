"""Build pinned Tcl/Tk with the qualified custom native GCC and explicit source-built dependencies."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from bounded_process import run
from compiler_tools import support_identities, verify_support
from package_tcl import finalize_tcl
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=("tcl", "tk"), required=True)
    for name in ("source", "manifest", "prefix", "compiler-receipt", "dependency",
                 "bootstrap", "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 11), required=True)
    args = parser.parse_args()
    if os.name != "nt" or args.output.exists():
        raise ContractError("Native Windows and fresh output required")
    verify_tree(args.source, args.manifest)
    source_record = json.loads(args.manifest.read_text())
    if source_record["source"]["id"] != args.package or source_record["source"]["version"] != "8.6.18":
        raise ContractError("Tcl/Tk source differs from the pinned prepared recipe")
    compiler_record = json.loads(args.compiler_receipt.read_text())
    verify_tree(args.prefix, args.compiler_receipt)
    if Path(compiler_record["prefix"]).resolve() != args.prefix.resolve():
        raise ContractError("Compiler receipt identifies a different private input")
    dependency_files = inventory(args.dependency)
    required = ("lib/libz.dll.a", "bin/libz.dll", "include/zlib.h") if args.package == "tcl" else (
        "lib/tclConfig.sh", "bin/tcl86.dll", "bin/tclsh.exe")
    if any(path not in dependency_files for path in required):
        raise ContractError("A real source-built Tcl/zlib dependency is missing")
    bootstrap_files = inventory(args.bootstrap / "usr")
    args.output.mkdir(parents=True)
    shutil.copytree(args.source, args.output / "source")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (args.prefix / "bin", args.dependency / "bin",
                                           args.bootstrap / "usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
    env["MSYSTEM"] = "MSYS"
    env["MSYS2_PATH_TYPE"] = "minimal"
    env["CHERE_INVOKING"] = "1"
    env["HOME"] = env["USERPROFILE"] = str(args.output / "home")
    script = Path(__file__).with_suffix(".sh")
    patch = Path(__file__).parent / "patches/tcl-external-native-zlib.patch"
    compiler = args.prefix / "bin/gcc.exe"
    support = support_identities(compiler, args.prefix, env)
    tools = {str(path): digest(path) for path in (compiler, args.prefix / "bin/windres.exe",
                                                args.bootstrap / "usr/bin/bash.exe", args.bootstrap / "usr/bin/make.exe")}
    command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
               args.package, args.output, args.prefix, args.dependency, patch.resolve(), str(args.jobs)]
    report = {"schema": 1, "status": "failed", "package": args.package, "source": source_record["source"],
              "source_manifest_sha256": digest(args.manifest), "compiler_receipt_sha256": digest(args.compiler_receipt),
              "recipe_sha256": digest(script), "patch_sha256": digest(patch), "tools": tools, "support": support,
              "dependency_files": dependency_files, "command": list(map(str, command)),
              "compiler_host": "native Windows ARM64", "orchestration": "explicit private x64 MSYS bootstrap",
              "pending": ["Native interpreter or GUI behavior and exact loaded-module closure",
                          "Complete interpreter package test suite", "Full Git assembly integration"]}
    try:
        with (args.output / "build.log").open("xb") as log:
            report["process"] = run(command, cwd=args.output, env=env, log=log, timeout=3600)
        if not report["process"]["passed"]:
            raise ContractError(f"Tcl/Tk build failed; inspect {args.output / 'build.log'}")
        if args.package == "tcl":
            text = (args.output / "build.log").read_text(errors="replace")
            summaries = re.findall(r"Total\s+(\d+)\s+Passed\s+(\d+)\s+Skipped\s+(\d+)\s+Failed\s+(\d+)", text)
            if not summaries or not any(int(row[1]) for row in summaries) or any(int(row[3]) for row in summaries):
                raise ContractError("Tcl targeted upstream tests did not complete with nonempty passing coverage")
            report["upstream_test_summaries"] = summaries
        stage = args.output / "stage"
        if args.package == "tcl":
            finalize_tcl(args.output / "source", stage)
        report["files"] = inventory(stage)
        expected = ("bin/tcl86.dll", "bin/tclsh.exe", "lib/tcl8.6/init.tcl", "lib/libtcl86.dll.a") if args.package == "tcl" else (
            "bin/tk86.dll", "bin/wish.exe", "lib/tk8.6/tk.tcl", "lib/libtk86.dll.a")
        if any(path not in report["files"] for path in expected):
            raise ContractError("Interpreter installation is incomplete")
        gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(stage), "-ReportPath", str(gate)], check=True)
        if json.loads(gate.read_text()).get("Passed") is not True:
            raise ContractError("Interpreter stage native PE gate failed")
        verify_tree(args.source, args.manifest)
        verify_tree(args.prefix, args.compiler_receipt)
        verify_support(support, compiler, args.prefix, env)
        if (inventory(args.dependency) != dependency_files or inventory(args.bootstrap / "usr") != bootstrap_files
                or any(digest(path) != sha for path, sha in tools.items())):
            raise ContractError("A build input changed")
        report["status"] = "native-interpreter-built-not-functionally-accepted"
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
