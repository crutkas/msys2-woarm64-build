"""Test unchanged, completed Tcl binaries and install them into a new private stage."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from bounded_process import run
from package_tcl import finalize_tcl
from sources import ContractError, digest, inventory


def compiled_inputs(root):
    return {str(path): digest(path) for path in root.rglob("*") if path.is_file() and
            path.suffix.lower() in (".exe", ".dll", ".a", ".o")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "zlib", "bootstrap", "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A fresh test/install output is required")
    original = compiled_inputs(args.build)
    source_files = inventory(args.build / "source")
    old_stage_files = inventory(args.build / "stage")
    input_files = {str(root): inventory(root) for root in (args.prefix, args.zlib, args.bootstrap / "usr")}
    required = (args.build / "build/tclsh86.exe", args.build / "build/tcl86.dll", args.build / "build/tcltest86.dll")
    if any(str(path) not in original for path in required):
        raise ContractError("The real Tcl compiler/test outputs are incomplete")
    args.output.mkdir(parents=True)
    (args.output / "temp").mkdir()
    (args.output / "home").mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (args.build / "build", args.prefix / "bin",
                                                args.bootstrap / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
                "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp"),
                "HOME": str(args.output / "home"), "TCL_LIBRARY": str(args.build / "source/library")})
    load = (f"package ifneeded Tcltest 8.6.18 [list load {{{(args.build / 'build/tcltest86.dll').as_posix()}}}];"
            f"lappend ::auto_path {{{(args.build / 'source/tests').as_posix()}}}")
    test_command = [required[0], args.build / "source/tests/all.tcl", "-file",
                    "basic.test expr.test dict.test list.test regexp.test encoding.test zlib.test",
                    "-load", load, "-tmpdir", args.output / "temp"]
    report = {"schema": 1, "status": "failed", "compiled_inputs": original,
              "test_command": list(map(str, test_command)),
              "scope": "Unchanged existing source build; explicit GNU installer and new stage, no compilation flags changed"}
    try:
        with (args.output / "tests.log").open("xb") as log:
            report["test_process"] = run(test_command, cwd=args.output, env=env, log=log, timeout=900)
        text = (args.output / "tests.log").read_text(errors="replace")
        summaries = re.findall(r"Total\s+(\d+)\s+Passed\s+(\d+)\s+Skipped\s+(\d+)\s+Failed\s+(\d+)", text)
        if (not report["test_process"]["passed"] or not summaries or
                not any(int(row[1]) for row in summaries) or any(int(row[3]) for row in summaries)):
            raise ContractError("Targeted native Tcl suite did not pass")
        report["test_summaries"] = summaries
        script = Path(__file__).with_suffix(".sh")
        report["recipe_sha256"] = digest(script)
        report["package_recipe_sha256"] = digest(Path(__file__).with_name("package_tcl.py"))
        command = [args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
                   args.build, args.prefix, args.zlib, args.output]
        with (args.output / "install.log").open("xb") as log:
            report["install_process"] = run(command, cwd=args.output, env=env, log=log, timeout=1200)
        if (not report["install_process"]["passed"] or compiled_inputs(args.build) != original
                or inventory(args.build / "source") != source_files
                or inventory(args.build / "stage") != old_stage_files
                or any(inventory(Path(root)) != files for root, files in input_files.items())):
            raise ContractError("Installation failed or changed an original source, stage, or build input")
        stage = args.output / "stage"
        finalize_tcl(args.build / "source", stage)
        gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(stage), "-ReportPath", str(gate)], check=True)
        if json.loads(gate.read_text()).get("Passed") is not True:
            raise ContractError("Installed Tcl native PE gate failed")
        report["files"] = inventory(stage)
        report["status"] = "native-Tcl-built-targeted-tested-new-stage"
        report["pending"] = ["Relocated interpreter/DLL checks", "Tk source build", "Complete Tcl upstream suite"]
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
