"""Shared reader of actual ordinary ARM64 PE32+ exports; no expected-symbol input is accepted."""

import argparse
from pathlib import Path
import struct

from sources import ContractError


def export_names(data):
    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ContractError("PE structure is outside the file")
        return struct.unpack_from(fmt, data, offset)

    if data[:2] != b"MZ":
        raise ContractError("Missing DOS header")
    pe = unpack("<I", 60)[0]
    if pe < 64 or data[pe:pe + 4] != b"PE\0\0":
        raise ContractError("Missing PE signature")
    machine, section_count = unpack("<HH", pe + 4)
    optional_size = unpack("<H", pe + 20)[0]
    optional = pe + 24
    if machine != 0xAA64 or optional_size < 120 or unpack("<H", optional)[0] != 0x20B:
        raise ContractError("Export reader requires ordinary ARM64 PE32+")
    if unpack("<I", optional + 108)[0] < 1 or section_count == 0:
        raise ContractError("PE export directory or sections are absent")
    export_rva, export_size = unpack("<II", optional + 112)
    if not export_rva or export_size < 40:
        raise ContractError("PE has no complete export directory")
    sections = []
    for index in range(section_count):
        entry = optional + optional_size + index * 40
        _, virtual, raw_size, raw = unpack("<IIII", entry + 8)
        if raw + raw_size > len(data):
            raise ContractError("PE section raw data is out of bounds")
        sections.append((virtual, raw_size, raw))

    def offset_for(rva, size):
        matches = [(raw + rva - virtual, raw + raw_size)
                   for virtual, raw_size, raw in sections
                   if virtual <= rva and rva + size <= virtual + raw_size]
        if len(matches) != 1:
            raise ContractError("Export RVA is absent or ambiguously mapped")
        return matches[0]

    directory, _ = offset_for(export_rva, 40)
    functions, count, function_rva, name_rva, ordinal_rva = unpack("<IIIII", directory + 20)
    if not count or count > len(data) // 4 or not functions or functions > len(data) // 4:
        raise ContractError("Invalid PE export table count")
    names_offset, _ = offset_for(name_rva, count * 4)
    ordinals_offset, _ = offset_for(ordinal_rva, count * 2)
    functions_offset, _ = offset_for(function_rva, functions * 4)
    result = set()
    for index in range(count):
        rva = unpack("<I", names_offset + index * 4)[0]
        ordinal = unpack("<H", ordinals_offset + index * 2)[0]
        if ordinal >= functions or not unpack("<I", functions_offset + ordinal * 4)[0]:
            raise ContractError("Named PE export has an invalid ordinal/address")
        start, end = offset_for(rva, 1)
        terminator = data.find(b"\0", start, end)
        if terminator <= start:
            raise ContractError("Unterminated or empty PE export name")
        name = data[start:terminator].decode("ascii")
        if name in result:
            raise ContractError("Duplicate PE export name")
        result.add(name)
    return sorted(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print("\n".join(export_names(args.path.read_bytes())))


if __name__ == "__main__":
    main()
