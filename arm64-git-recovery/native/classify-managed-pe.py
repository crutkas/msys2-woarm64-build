"""Describe CLR containers without changing the distribution's strict ARM64 gate."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from sources import ContractError


def classify(path):
    data = Path(path).read_bytes()
    def u16(at):
        return struct.unpack_from("<H", data, at)[0]
    def u32(at):
        return struct.unpack_from("<I", data, at)[0]
    if len(data) < 64 or data[:2] != b"MZ":
        raise ContractError("Missing PE DOS header")
    pe = u32(60)
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ContractError("Invalid PE signature")
    machine, sections, optional_size = u16(pe + 4), u16(pe + 6), u16(pe + 20)
    optional, magic = pe + 24, u16(pe + 24)
    if magic not in (0x10b, 0x20b):
        raise ContractError("Unsupported optional header")
    directory = optional + (96 if magic == 0x10b else 112)
    count = u32(optional + (92 if magic == 0x10b else 108))
    table = optional + optional_size
    def rva(address, size=1):
        for n in range(sections):
            section = table + 40 * n
            va, raw_size, raw = u32(section + 12), u32(section + 16), u32(section + 20)
            if va <= address and address + size <= va + raw_size:
                offset = raw + address - va
                if offset + size <= len(data):
                    return offset
        raise ContractError(f"RVA outside mapped raw data: {address:x}")
    result = {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(data).hexdigest(),
              "machine": f"0x{machine:04X}", "optional_magic": f"0x{magic:04X}"}
    imports = []
    if count > 1 and u32(directory + 8):
        imp = rva(u32(directory + 8), 20)
        while data[imp:imp + 20] != b"\0" * 20:
            name = rva(u32(imp + 12))
            end = data.index(0, name)
            imports.append(data[name:end].decode("ascii"))
            imp += 20
    result["native_imports"] = imports
    if count <= 14 or not u32(directory + 14 * 8):
        result["classification"] = "native-PE"
        return result
    cli = rva(u32(directory + 14 * 8), 72)
    flags = u32(cli + 16)
    native_rva, native_size = u32(cli + 64), u32(cli + 68)
    result.update({
        "clr_header_size": u32(cli), "clr_flags": f"0x{flags:08X}",
        "il_only": bool(flags & 1), "bit32_required": bool(flags & 2),
        "native_entrypoint": bool(flags & 0x10), "bit32_preferred": bool(flags & 0x20000),
        "managed_native_header_rva": native_rva, "managed_native_header_size": native_size,
        "clr_metadata_version": [u16(cli + 4), u16(cli + 6)]
    })
    if native_rva:
        at = rva(native_rva, min(native_size, 4))
        result["managed_native_signature"] = data[at:at + 4].hex()
    if flags & 1 and not flags & (2 | 0x10 | 0x20000) and not native_rva and not native_size:
        result["classification"] = ("architecture-neutral-IL-container"
                                    if machine == 0x14c else "architecture-specific-IL-container")
    else:
        result["classification"] = "managed-requires-further-native-or-bitness-review"
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    records = [classify(path) for path in sorted(a.root.rglob("*"))
               if path.is_file() and path.suffix.lower() in (".exe", ".dll")]
    if not records:
        raise ContractError("No PE payload")
    with a.report.open("x", encoding="utf-8") as dest:
        json.dump({"schema": 1, "scope": "Read-only PE/CLR classification; not admission, native execution, or source provenance",
                   "records": records}, dest, indent=2)
        dest.write("\n")
    counts = {}
    for record in records:
        key = record["classification"]
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
