"""Read actual ARM64 PE32+ identity and import tables without trusting filenames."""

from pathlib import Path
import struct

from sources import ContractError, digest


def inspect_pe(path):
    path = Path(path)
    data = path.read_bytes()

    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ContractError(f"Truncated PE structure: {path}")
        return struct.unpack_from(fmt, data, offset)

    if data[:2] != b"MZ":
        raise ContractError(f"Missing MZ header: {path}")
    pe = unpack("<I", 60)[0]
    if pe < 64 or data[pe:pe + 4] != b"PE\0\0":
        raise ContractError(f"Missing PE signature: {path}")
    machine, count = unpack("<HH", pe + 4)
    optional_size, characteristics = unpack("<HH", pe + 20)
    optional = pe + 24
    if machine != 0xAA64 or optional_size < 240 or unpack("<H", optional)[0] != 0x20B:
        raise ContractError(f"Expected ordinary AA64 PE32+, not x64/ARM64EC: {path}")
    directories = unpack("<I", optional + 108)[0]
    if directories < 14 or not count:
        raise ContractError(f"Incomplete PE data directories/sections: {path}")
    sections = []
    for index in range(count):
        row = optional + optional_size + index * 40
        _, virtual, size, raw = unpack("<IIII", row + 8)
        if raw + size > len(data):
            raise ContractError(f"PE section exceeds file: {path}")
        sections.append((virtual, size, raw))

    def offset(rva, size):
        matches = [raw + rva - virtual for virtual, raw_size, raw in sections
                   if virtual <= rva and rva + size <= virtual + raw_size]
        if len(matches) != 1:
            raise ContractError(f"Unmapped or ambiguous PE RVA: {path}")
        return matches[0]

    def name_at(rva):
        start = offset(rva, 1)
        end = data.find(b"\0", start, min(start + 1024, len(data)))
        if end < 0:
            raise ContractError(f"Unterminated PE import name: {path}")
        name = data[start:end].decode("ascii")
        if not name or any(c in name for c in "/\\:"):
            raise ContractError(f"Unsafe PE dependency name: {path}")
        return name

    imports = []
    for index, descriptor_size, delayed in ((1, 20, False), (13, 32, True)):
        rva, size = unpack("<II", optional + 112 + index * 8)
        if not rva and not size:
            continue
        if not rva or size < descriptor_size:
            raise ContractError(f"Malformed PE import directory: {path}")
        start = offset(rva, size)
        terminated = False
        for position in range(start, start + size - descriptor_size + 1, descriptor_size):
            descriptor = unpack("<" + "I" * (descriptor_size // 4), position)
            if not any(descriptor):
                terminated = True
                break
            if delayed and descriptor[0] != 1:
                raise ContractError(f"Unsupported non-RVA delayed imports: {path}")
            imports.append({"name": name_at(descriptor[1] if delayed else descriptor[3]),
                            "delayed": delayed})
        if not terminated:
            raise ContractError(f"Unterminated PE import descriptors: {path}")
    return {"path": str(path), "size": len(data), "sha256": digest(path),
            "machine": "0xAA64", "optional_magic": "0x20B",
            "kind": "dll" if characteristics & 0x2000 else "executable", "imports": imports}
