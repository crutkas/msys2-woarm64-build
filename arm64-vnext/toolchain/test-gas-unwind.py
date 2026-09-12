#!/usr/bin/env python3
"""Check ARM64 .xdata bytes without trusting binutils' own unwind decoder."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent / "probes" / "gas-epilogues.s"
    obj = args.output / "epilogues.o"
    subprocess.run([str(args.assembler), str(source), "-o", str(obj)], check=True)
    data = obj.read_bytes()
    machine, sections = struct.unpack_from("<HH", data)
    if machine != 0xAA64:
        parser.error(f"Unexpected object machine: {machine:#x}")
    optional_size = struct.unpack_from("<H", data, 16)[0]
    xdata = None
    for index in range(sections):
        offset = 20 + optional_size + index * 40
        name = data[offset:offset + 8].rstrip(b"\0")
        size, position = struct.unpack_from("<II", data, offset + 16)
        if name == b".xdata":
            if position + size > len(data):
                parser.error("Truncated .xdata section")
            xdata = data[position:position + size]
    if not xdata:
        parser.error("Missing .xdata section")
    expected = [
        ("compact", 1, 5, []),
        ("large-index", 0, 1, [(36, 37)]),
        ("multiple", 0, 2, [(4, 5), (7, 5)]),
        ("nonterminal", 0, 1, [(4, 5)]),
    ]
    position = 0
    results = []
    for name, expected_e, expected_count, expected_scopes in expected:
        header = struct.unpack_from("<I", xdata, position)[0]
        position += 4
        e = (header >> 21) & 1
        count = (header >> 22) & 31
        words = header >> 27
        if count == 0 and words == 0:
            extension = struct.unpack_from("<I", xdata, position)[0]
            position += 4
            count, words = extension & 65535, (extension >> 16) & 255
        scopes = []
        if not e:
            for _ in range(count):
                scope = struct.unpack_from("<I", xdata, position)[0]
                position += 4
                scopes.append((scope & 0x3FFFF, scope >> 22))
        position += words * 4 + (4 if (header >> 20) & 1 else 0)
        results.append({
            "name": name, "e": e, "countOrIndex": count, "scopes": scopes,
            "passed": e == expected_e and count == expected_count and scopes == expected_scopes,
        })
    passed = position == len(xdata) and all(result["passed"] for result in results)
    report = {
        "assembler": str(args.assembler),
        "assemblerSha256": hashlib.sha256(args.assembler.read_bytes()).hexdigest(),
        "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "objectSha256": hashlib.sha256(data).hexdigest(),
        "scope": "Raw COFF ARM64 .xdata encoding; native RtlVirtualUnwind is separate",
        "passed": passed, "results": results,
    }
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
