#!/usr/bin/env python3
"""Verify full-width image-local PE reference cells from real GCC codegen."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--assembler", type=Path, required=True)
    parser.add_argument("--support", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent / "probes" / "pe-extern-data.c"
    assembly = args.output / "extern.s"
    obj = args.output / "extern.o"
    command = [str(args.compiler)]
    if args.support:
        command.append(f"-B{args.support}/")
    command += ["-O2", "-S", str(source), "-o", str(assembly)]
    subprocess.run(command, check=True)
    subprocess.run([str(args.assembler), str(assembly), "-o", str(obj)], check=True)
    data = obj.read_bytes()
    machine, count, _, symtab, symbols, optional, _ = struct.unpack_from("<HHIIIHH", data)
    if machine != 0xAA64:
        raise ValueError("Expected ARM64 COFF")
    strings = symtab + 18 * symbols

    def name_at(offset):
        end = data.index(0, offset)
        return data[offset:end].decode("ascii")

    records = []
    for index in range(count):
        offset = 20 + optional + 40 * index
        name = data[offset:offset + 8].rstrip(b"\0").decode("ascii")
        if name.startswith("/"):
            name = name_at(strings + int(name[1:]))
        if ".refptr." not in name:
            continue
        size, position, relocations = struct.unpack_from("<III", data, offset + 16)
        relocation_count = struct.unpack_from("<H", data, offset + 32)[0]
        flags = struct.unpack_from("<I", data, offset + 36)[0]
        encoded_alignment = (flags >> 20) & 15
        alignment = (1 << (encoded_alignment - 1)) if encoded_alignment else 1
        types = [struct.unpack_from("<H", data, relocations + 10 * i + 8)[0]
                 for i in range(relocation_count)]
        records.append({
            "section": name, "size": size, "alignment": alignment,
            "relocationTypes": types,
            "passed": size == 8 and alignment >= 8 and types == [0x000E]
                      and data[position:position + 8] == bytes(8),
        })
    expected = {".rdata$.refptr.external_value", ".rdata$.refptr.external_array",
                ".rdata$.refptr.weak_value"}
    passed = {item["section"] for item in records} == expected and all(item["passed"] for item in records)
    result = {
        "passed": passed, "records": records,
        "compilerSha256": hashlib.sha256(args.compiler.read_bytes()).hexdigest(),
        "assemblerSha256": hashlib.sha256(args.assembler.read_bytes()).hexdigest(),
        "sourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "objectSha256": hashlib.sha256(data).hexdigest(),
        "scope": "Compiler/COFF pointer-cell lowering; far-ASLR native read/write is a separate gate",
    }
    support_command = [str(args.compiler)]
    if args.support:
        support_command.append(f"-B{args.support}/")
    frontend = Path(subprocess.check_output(
        support_command + ["-print-prog-name=cc1"], text=True).strip())
    if not frontend.is_file():
        raise ValueError("Compiler did not resolve its actual cc1 frontend")
    result["frontend"] = str(frontend.resolve())
    result["frontendSha256"] = hashlib.sha256(frontend.read_bytes()).hexdigest()
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
