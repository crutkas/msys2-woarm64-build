"""Relink the existing native Tk objects with a new verified CRT, preserving source, flags and failed artifacts."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from bounded_process import run
from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


def link_command(lines, compiler, stage):
    commands = []
    for index, line in enumerate(lines):
        if line.startswith("gcc -shared") and "-o tk86.dll" in line:
            command = line
            while command.endswith("\\"):
                index += 1
                if index >= len(lines):
                    raise ContractError("Incomplete Tk link command")
                command = command[:-1] + " " + lines[index]
            commands.append(shlex.split(command))
    if len(commands) != 1:
        raise ContractError("Expected one exact Tk shared-library command")
    original = commands[0]
    if (original.count("-o") != 1 or original[original.index("-o") + 1] != "tk86.dll" or
            original.count("-Wl,--out-implib,libtk86.dll.a") != 1):
        raise ContractError("Unexpected Tk DLL or import-library output arguments")
    if any("--output-def" in value or "-Map" in value for value in original):
        raise ContractError("Unmanaged additional Tk linker output")
    command = list(original)
    command[0] = str(compiler)
    command[command.index("-o") + 1] = str(stage / "bin/tk86.dll")
    command[command.index("-Wl,--out-implib,libtk86.dll.a")] = (
        "-Wl,--out-implib," + (stage / "lib/libtk86.dll.a").as_posix())
    return original, command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "compiler-receipt", "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A new Tk CRT consumer stage is required")
    verify_tree(args.build / "stage", args.build / "result.json")
    verify_tree(args.prefix, args.compiler_receipt)
    compiler_record = json.loads(args.compiler_receipt.read_text())
    if (Path(compiler_record["prefix"]).resolve() != args.prefix.resolve() or
            compiler_record["source_status"] != "crt-cexp-recursion-fix-validated"):
        raise ContractError("Expected the explicitly repaired cexp producer input")
    before = inventory(args.build)
    lines = (args.build / "build.log").read_text().splitlines()
    stage = args.output / "stage"
    original, command = link_command(lines, args.prefix / "bin/gcc.exe", stage)
    args.output.mkdir(parents=True)
    shutil.copytree(args.build / "stage", stage)
    (args.output / "temp").mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": str(args.prefix / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp")})
    support = support_identities(args.prefix / "bin/gcc.exe", args.prefix, env)
    report = {"status": "failed", "original_receipt_sha256": digest(args.build / "result.json"),
              "compiler_receipt_sha256": digest(args.compiler_receipt), "original_link_command": original,
              "new_link_command": command, "support": support,
              "scope": "Only existing Tk objects relinked against repaired producer CRT; no consumer C/optimization flags changed"}
    try:
        with (args.output / "link.log").open("xb") as log:
            report["process"] = run(command, cwd=args.build / "build", env=env, log=log, timeout=120)
        if not report["process"]["passed"]:
            raise ContractError("Native Tk relink failed")
        if inventory(args.build) != before:
            raise ContractError("An original Tk build or stage changed during relink")
        verify_tree(args.prefix, args.compiler_receipt)
        verify_support(support, args.prefix / "bin/gcc.exe", args.prefix, env)
        report["files"] = inventory(stage)
        gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(stage), "-ReportPath", str(gate)], check=True)
        if json.loads(gate.read_text()).get("Passed") is not True:
            raise ContractError("Relinked Tk PE gate failed")
        report["status"] = "native-tk-relinked-crt-gui-acceptance-pending"
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
