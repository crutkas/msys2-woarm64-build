"""Read signed package members and PE import/export tables without executing payload."""
import argparse
from compression import zstd
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pe(data):
    def u16(offset):
        return struct.unpack_from("<H", data, offset)[0]

    def u32(offset):
        return struct.unpack_from("<I", data, offset)[0]

    def u64(offset):
        return struct.unpack_from("<Q", data, offset)[0]

    offset = u32(60)
    if data[offset:offset + 4] != b"PE\0\0":
        raise ValueError("MZ image has no valid PE signature")
    machine = u16(offset + 4)
    optional = offset + 24
    if u16(optional) != 0x20B:
        raise ValueError("PE32+ required")
    sections = []
    table = optional + u16(offset + 20)
    for index in range(u16(offset + 6)):
        entry = table + index * 40
        sections.append((u32(entry + 12), u32(entry + 8), u32(entry + 20), u32(entry + 16)))

    def position(rva):
        for start, virtual_size, raw, raw_size in sections:
            if start <= rva < start + max(virtual_size, raw_size):
                delta = rva - start
                if delta >= raw_size or raw + delta >= len(data):
                    raise ValueError("RVA does not identify file-backed bytes")
                return raw + delta
        if rva < u32(optional + 60) and rva < len(data):
            return rva
        raise ValueError(f"Invalid RVA {rva:x}")

    def text(rva):
        begin = position(rva)
        end = data.index(b"\0", begin)
        return data[begin:end].decode("ascii")

    def directory(index):
        if u32(optional + 108) <= index:
            return 0, 0
        return struct.unpack_from("<II", data, optional + 112 + index * 8)

    def thunks(rva):
        values = []
        for index in range(100000):
            value = u64(position(rva + index * 8))
            if not value:
                return values
            values.append({"ordinal": value & 0xFFFF} if value & (1 << 63)
                          else {"name": text(value + 2)})
        raise ValueError("Unterminated import thunk table")

    imports = []
    rva, size = directory(1)
    if rva:
        for index in range(size // 20):
            entry = struct.unpack_from("<IIIII", data, position(rva + index * 20))
            if not any(entry):
                break
            imports.append({"dll": text(entry[3]), "symbols": thunks(entry[0] or entry[4])})
        else:
            raise ValueError("Unterminated import directory")
    delayed = []
    rva, size = directory(13)
    if rva:
        image_base = u64(optional + 24)
        for index in range(size // 32):
            entry = struct.unpack_from("<8I", data, position(rva + index * 32))
            if not any(entry):
                break
            adjust = 0 if entry[0] & 1 else image_base
            delayed.append({"dll": text(entry[1] - adjust), "symbols": thunks(entry[4] - adjust)})
        else:
            raise ValueError("Unterminated delay import directory")
    exports = []
    export_rva, export_size = directory(0)
    if export_rva:
        entry = position(export_rva)
        base, count, named = u32(entry + 16), u32(entry + 20), u32(entry + 24)
        functions, names, ordinals = u32(entry + 28), u32(entry + 32), u32(entry + 36)
        name_map = {u16(position(ordinals + i * 2)): text(u32(position(names + i * 4)))
                    for i in range(named)}
        for index in range(count):
            address = u32(position(functions + index * 4))
            if address:
                exports.append({"ordinal": base + index, "name": name_map.get(index),
                                "forwarder": text(address) if export_rva <= address < export_rva + export_size else None})
    return {"machine": f"0x{machine:04X}", "ordinary_arm64": machine == 0xAA64,
            "pe32_plus": True, "imports": imports, "delay_imports": delayed, "exports": exports}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("extracted", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError("Report output must be new")
    root = args.extracted.resolve(strict=True)
    result = {"status": "failed", "archive": str(args.archive), "archive_sha256": sha(args.archive.read_bytes()),
              "extracted": str(root), "members": [], "pe": [], "private_path_hits": []}
    seen = set()
    patterns = [
        r"(?i)[a-z]:[\\/](?:users[\\/]|ap[0-9][^\\/\x00\s]*[\\/]|ag-[^\\/\x00\s]*[\\/]|_[\\/])",
        r"(?i)(?:[\\/]session-state[\\/]|[\\/]copilot-worktrees[\\/]|/home/[^/\s\x00]+/)",
    ]
    try:
        with zstd.open(args.archive, "rb") as compressed, tarfile.open(fileobj=compressed, mode="r|") as package:
            for member in package:
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or ".." in relative.parts or ":" in member.name or "\\" in member.name:
                    raise ValueError("Unsafe archive path")
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError(f"Non-regular member requires explicit handling: {member.name}")
                name = str(relative)
                if name.casefold() in seen:
                    raise ValueError("Duplicate archive member")
                seen.add(name.casefold())
                data = package.extractfile(member).read()
                path = root.joinpath(*relative.parts)
                if not path.is_file() or path.is_symlink() or sha(path.read_bytes()) != sha(data):
                    raise ValueError(f"Extracted bytes differ from signed archive: {name}")
                result["members"].append({"path": name, "size": len(data), "sha256": sha(data)})
                if data.startswith(b"MZ"):
                    result["pe"].append({"path": name, "sha256": sha(data), **pe(data)})
                for encoding in ("latin1", "utf-16-le"):
                    decoded = data.decode(encoding, errors="replace")
                    for pattern in patterns:
                        for match in re.finditer(pattern, decoded):
                            result["private_path_hits"].append({
                                "path": name, "encoding": encoding, "offset": match.start(),
                                "context": decoded[max(0, match.start() - 24):match.end() + 160].split("\0")[0]})
        files = {str(path.relative_to(root)).replace("\\", "/").casefold()
                 for path in root.rglob("*") if path.is_file()}
        if files != seen:
            raise ValueError("Extracted file set differs from signed package")
        if not result["pe"] or not all(image["ordinary_arm64"] for image in result["pe"]):
            raise ValueError("Package does not contain exclusively ordinary ARM64 PE images")
        result["status"] = "all-archive-members-and-aa64-images-verified-not-runtime-admission"
    finally:
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "members": len(result["members"]),
                      "pe": len(result["pe"]), "private_path_hits": len(result["private_path_hits"])}))


if __name__ == "__main__":
    main()
