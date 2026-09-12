#!/usr/bin/env python3
"""Check .seh_add_fp byte units and rejected operands in raw COFF output."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
from coff_unwind import xdata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for offset in (0, 8, 16, 2040, 1, 7, 2048):
        source = args.output / f"offset-{offset}.s"
        obj = source.with_suffix(".o")
        # This is an encoding-only fixture, not a callable ABI implementation.
        source.write_text(
            f".text\n.seh_proc probe\nprobe:\nadd x29,sp,{offset}\n"
            f".seh_add_fp {offset}\n.seh_endprologue\nret\n.seh_endproc\n",
            encoding="ascii",
        )
        run = subprocess.run([str(args.assembler), str(source), "-o", str(obj)],
                             capture_output=True)
        source.with_suffix(".stderr").write_bytes(run.stderr)
        valid = offset <= 2040 and offset % 8 == 0
        code = xdata(obj.read_bytes())[4:7] if run.returncode == 0 else b""
        expected = bytes((0xE2, offset // 8, 0xE4)) if valid else b""
        results.append({
            "offset": offset, "returncode": run.returncode, "code": code.hex(),
            "passed": (run.returncode == 0 and code == expected) if valid else run.returncode == 1,
        })
    passed = all(result["passed"] for result in results)
    report = {
        "assembler": str(args.assembler),
        "assemblerSha256": hashlib.sha256(args.assembler.read_bytes()).hexdigest(),
        "passed": passed, "results": results,
    }
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
