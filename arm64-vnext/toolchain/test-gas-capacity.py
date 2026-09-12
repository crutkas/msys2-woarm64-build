#!/usr/bin/env python3
"""Exercise large shared epilogue tables and fail-closed malformed unwind data."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
sys.dont_write_bytecode = True
from coff_unwind import xdata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembler", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    cases = {
        "many": (".text\n.seh_proc many\nmany:\nsub sp,sp,16\n.seh_stackalloc 16\n"
                 ".seh_endprologue\n.rept 600\n.seh_startepilogue\nadd sp,sp,16\n"
                 ".seh_stackalloc 16\nret\n.seh_endepilogue\n.endr\n.seh_endproc\n"),
        "oversized": (".text\n.seh_proc bad\nbad:\n.rept 1021\nnop\n.seh_nop\n"
                      ".endr\n.seh_endprologue\nret\n.seh_endproc\n"),
        "unmatched": ".text\n.seh_proc bad\nbad:\n.seh_endepilogue\n.seh_endproc\n",
        "nested": (".text\n.seh_proc bad\nbad:\n.seh_endprologue\n.seh_startepilogue\n"
                   ".seh_startepilogue\nret\n.seh_endepilogue\n.seh_endproc\n"),
    }
    for name, text in cases.items():
        source = args.output / f"{name}.s"
        obj = source.with_suffix(".o")
        source.write_text(text, encoding="ascii")
        run = subprocess.run([str(args.assembler), str(source), "-o", str(obj)],
                             capture_output=True)
        source.with_suffix(".stderr").write_bytes(run.stderr)
        passed = run.returncode == 1
        if name == "many":
            passed = False
            if run.returncode == 0:
                raw = xdata(obj.read_bytes())
                header, extension = struct.unpack_from("<II", raw)
                scopes = struct.unpack_from("<600I", raw, 8)
                passed = ((header >> 21) == 0 and (extension & 65535) == 600
                          and ((extension >> 16) & 255) == 1
                          and all(scope >> 22 == 0 for scope in scopes)
                          and all((scope & 0x3FFFF) == 1 + 2 * i for i, scope in enumerate(scopes))
                          and len(raw) == 8 + 600 * 4 + 4
                          and raw[-4:-2] == bytes((1, 0xE4)))
        records.append({"name": name, "returncode": run.returncode, "passed": passed})
    result = {"passed": all(item["passed"] for item in records), "results": records}
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
