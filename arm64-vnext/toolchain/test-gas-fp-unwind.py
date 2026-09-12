#!/usr/bin/env python3
"""Check documented ARM64 FP unwind bytes, independently of objdump."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from coff_unwind import xdata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembler", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-legacy", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    assembler = args.assembler.resolve(strict=True)
    cases = [
        ("freg-v8-8", "str d8, [sp, 8]", "ldr d8, [sp, 8]", "save_freg v8, 8", "dc0104e4"),
        ("freg-d8-8", "str d8, [sp, 8]", "ldr d8, [sp, 8]", "save_freg d8, 8", "dc0104e4"),
        ("freg-v8-0", "str d8, [sp]", "ldr d8, [sp]", "save_freg v8, 0", "dc0004e4"),
        ("freg-v10-16", "str d10, [sp, 16]", "ldr d10, [sp, 16]", "save_freg v10, 16", "dc8204e4"),
        ("fregp-v8-16", "stp d8, d9, [sp, 16]", "ldp d8, d9, [sp, 16]", "save_fregp v8, 16", "d80204e4"),
        ("fregx-v8-16", "str d8, [sp, -16]!", "ldr d8, [sp], 16", "save_freg_x v8, 16", "de0104e4"),
        ("reg-x30-0", "str x30, [sp]", "ldr x30, [sp]", "save_reg x30, 0", "d2c004e4"),
    ]
    report = {"passed": False, "legacy": args.expect_legacy, "assembler": str(assembler),
              "assembler_sha256": hashlib.sha256(assembler.read_bytes()).hexdigest(), "cases": []}
    try:
        for name, save, restore, directive, expected in cases:
            symbol = name.replace("-", "_")
            source = args.output / f"{name}.s"
            obj = args.output / f"{name}.o"
            source.write_text(
                f".text\n.global {symbol}\n.seh_proc {symbol}\n{symbol}:\n"
                f"sub sp, sp, #64\n.seh_stackalloc 64\n{save}\n.seh_{directive}\n"
                f".seh_endprologue\n.seh_startepilogue\n{restore}\n.seh_{directive}\n"
                "add sp, sp, #64\n.seh_stackalloc 64\nret\n.seh_endepilogue\n.seh_endproc\n",
                encoding="ascii")
            command = [str(assembler), str(source), "-o", str(obj)]
            result = subprocess.run(command, capture_output=True, timeout=60)
            (args.output / f"{name}.stdout.bin").write_bytes(result.stdout)
            (args.output / f"{name}.stderr.bin").write_bytes(result.stderr)
            result.check_returncode()
            raw = xdata(obj.read_bytes())
            if len(raw) != 8:
                raise ValueError(f"Unexpected xdata size in {name}: {raw.hex()}")
            report["cases"].append({"name": name, "command": command, "exit": result.returncode,
                                    "xdata": raw.hex(), "codes": raw[4:].hex(), "expected": expected,
                                    "matches": raw[4:].hex() == expected,
                                    "object_sha256": hashlib.sha256(obj.read_bytes()).hexdigest()})
        indexed = {case["name"]: case for case in report["cases"]}
        if args.expect_legacy:
            if (indexed["freg-v8-8"]["codes"] != "da0004e4"
                    or indexed["fregp-v8-16"]["codes"] != "d64204e4"
                    or not indexed["reg-x30-0"]["matches"]):
                raise ValueError("The known broken FP encoding/control was not reproduced")
        elif not all(case["matches"] for case in report["cases"]):
            raise ValueError("FP unwind directive bytes do not match the documented opcodes")
        if hashlib.sha256(assembler.read_bytes()).hexdigest() != report["assembler_sha256"]:
            raise ValueError("Assembler changed during the encoding proof")
        report["passed"] = True
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"FP unwind encoding control passed (legacy={args.expect_legacy}): {args.output}")


if __name__ == "__main__":
    main()
