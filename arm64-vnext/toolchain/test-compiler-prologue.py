#!/usr/bin/env python3
"""Check instruction coverage and contiguity in controlled GCC ARM64 SEH prologues."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--support", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent / "probes" / "compiler-prologue.c"
    assembly = args.output / "compiler.s"
    command = [str(args.compiler)]
    if args.support:
        command.append(f"-B{args.support}/")
    command += ["-O2", "-fstack-check", "-S", str(source), "-o", str(assembly)]
    subprocess.run(command, check=True)
    results = []
    function = None
    instructions = descriptions = nops = 0
    branches = []
    frame_ops = []
    for raw in assembly.read_text().splitlines():
        line = raw.strip()
        if line.startswith(".seh_proc"):
            function = line.split()[1]
            instructions = descriptions = nops = 0
            branches = []
            frame_ops = []
        elif function and line == ".seh_endprologue":
            results.append({
                "function": function, "instructions": instructions,
                "descriptions": descriptions, "nops": nops,
                "branches": branches,
                "frameOperations": frame_ops,
                "passed": (instructions == descriptions and instructions > 0 and nops >= 2
                           and not branches and (function != "unwind_large_dynamic"
                           or (bool(frame_ops) and frame_ops[-1].split() == [".seh_add_fp", "16"]))),
            })
            function = None
        elif function and line.startswith(".seh_"):
            descriptions += 1
            nops += line == ".seh_nop"
            if line != ".seh_nop":
                frame_ops.append(line)
        elif function and line and not line.startswith((".", "//", "#")) and not line.endswith(":"):
            instructions += 1
            if line.split()[0].startswith(("b", "cb", "tb")):
                branches.append(line)
    passed = len(results) == 4 and all(result["passed"] for result in results)
    report = {
        "compiler": str(args.compiler),
        "compilerSha256": hashlib.sha256(args.compiler.read_bytes()).hexdigest(),
        "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "assemblySha256": hashlib.sha256(assembly.read_bytes()).hexdigest(),
        "command": command, "passed": passed, "results": results,
        "scope": "Controlled assembly instruction coverage; native RtlVirtualUnwind is separate",
    }
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
