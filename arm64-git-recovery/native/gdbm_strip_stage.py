"""Create a private-path-free successor without rebuilding GDBM code."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

from db_native_checks import environment
from db_package import pe_metadata
from gdbm_recovery import isolated_observe
from gdbm_stage import image_sections
from sources import ContractError, digest, inventory
from ssh_bootstrap import write_json


def object_sections(data):
    if len(data) < 20 or struct.unpack_from("<H", data)[0] != 0xAA64:
        raise ContractError("Static archive member is not ordinary AA64 COFF")
    count = struct.unpack_from("<H", data, 2)[0]
    symbols, symbol_count = struct.unpack_from("<II", data, 8)
    table = 20 + struct.unpack_from("<H", data, 16)[0]
    strings = symbols + symbol_count * 18
    result = {}
    for number in range(count):
        entry = table + number * 40
        name = data[entry:entry + 8].rstrip(b"\0").decode("ascii")
        if name.startswith("/"):
            start = strings + int(name[1:])
            end = data.find(b"\0", start)
            if end < start:
                raise ContractError("Invalid COFF string table")
            name = data[start:end].decode("ascii")
        size, offset = struct.unpack_from("<II", data, entry + 16)
        characteristics = struct.unpack_from("<I", data, entry + 36)[0]
        if offset and offset + size > len(data):
            raise ContractError("Truncated static archive member")
        if not name.startswith(".debug"):
            if name in result:
                raise ContractError("Ambiguous duplicate static-object section")
            result[name] = (f"uninitialized:{size}" if characteristics & 0x80
                            else hashlib.sha256(data[offset:offset + size]).hexdigest())
    return result


def archive_members(path):
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ContractError("Expected a genuine static archive")
    offset, names, members = 8, b"", {}
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:] != b"`\n":
            raise ContractError("Malformed static archive header")
        name = header[:16].decode("ascii").strip()
        size = int(header[48:58].strip())
        body = data[offset + 60:offset + 60 + size]
        if len(body) != size:
            raise ContractError("Truncated static archive")
        offset += 60 + size + size % 2
        if name == "//":
            names = body
        elif name not in ("/", "/SYM64/"):
            if name.startswith("/"):
                start = int(name[1:])
                end = names.find(b"/\n", start)
                if end < start:
                    raise ContractError("Malformed archive member name")
                name = names[start:end].decode("utf-8")
            else:
                name = name.rstrip("/")
            if name in members:
                raise ContractError("Duplicate static archive member")
            members[name] = body
    return members


def archive_code(path):
    return {name: object_sections(data) for name, data in archive_members(path).items()}


def code_identity(path):
    if path.suffix in (".exe", ".dll"):
        pe_metadata(path.read_bytes())
        return {name: hashlib.sha256(data).hexdigest()
                for name, data in image_sections(path.read_bytes()) if not name.startswith(".debug")}
    return archive_code(path)


def pe_tables(path):
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 60)[0]
    export_rva, export_size = struct.unpack_from("<II", data, pe + 24 + 112)
    return {**pe_metadata(data), "export_directory_rva": export_rva,
            "export_directory_size": export_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-name", default="strip-stage02")
    parser.add_argument("--stage-name", default="stage-stripped02")
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01"):
        raise ContractError("Only the owned GDBM successor root is authorized")
    original = root / "stage"
    if any(Path(name).name != name or name in (".", "..") for name in (args.run_name, args.stage_name)):
        raise ContractError("Explicit owned successor stage/run names required")
    stage = root / args.stage_name
    output = root / args.run_name
    output.mkdir()
    before = inventory(original)
    shutil.copytree(original, stage)
    if inventory(stage) != before or inventory(original) != before:
        raise ContractError("Successor before/copy/after differs")
    targets = [path for path in (stage / "usr/bin").iterdir() if path.suffix in (".exe", ".dll")]
    targets += [stage / "usr/lib/libgdbm.a", stage / "usr/lib/libgdbm_compat.a"]
    before_code = {str(path.relative_to(stage)): code_identity(path) for path in targets}
    tables_before = {str(path.relative_to(stage)): pe_tables(path) for path in targets if path.suffix in (".exe", ".dll")}
    write_json(output / "before.json", {"files": before, "non_debug_code": before_code, "pe_tables": tables_before})
    env = environment(root / "compiler", output)
    env["WOARM64_NATIVE_TEST_ROOT"] = str(root)
    tool = root / "compiler/bin/strip.exe"
    row = isolated_observe(root, output, "real-native-strip",
                           [tool, "--strip-debug", *[path for path in targets if path.suffix in (".exe", ".dll")]],
                           stage, env, 180)
    static_rows = {}
    objcopy = root / "compiler/bin/objcopy.exe"
    for path in targets:
        if path.suffix == ".a":
            static_rows[path.name] = isolated_observe(root, output, "coff-" + path.stem,
                [objcopy, "--strip-debug", "--file-alignment=4", "--section-alignment=4",
                 "-I", "pe-aarch64-little", "-O", "pe-aarch64-little", path], stage, env, 180)
    after_code = {str(path.relative_to(stage)): code_identity(path) for path in targets}
    tables_after = {str(path.relative_to(stage)): pe_tables(path) for path in targets if path.suffix in (".exe", ".dll")}
    remaining = []
    for path in stage.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            if any(word.encode(encoding) in data for word in ("ag-gdbm-20260911-01", "ap06-78")
                   for encoding in ("ascii", "utf-16le")):
                remaining.append(str(path.relative_to(stage)))
    after = inventory(stage)
    report = {"schema": 1, "process": row, "static_processes": static_rows,
              "strip_tool_sha256": digest(tool), "objcopy_tool_sha256": digest(objcopy),
              "method": "Genuine ARM64 strip --strip-debug for PEs; objcopy --strip-debug with explicit pe-aarch64-little COFF alignment4 for archives; no recompilation",
              "original_files": before, "files": after, "stage": str(stage),
              "non_debug_code_before": before_code, "non_debug_code_after": after_code,
              "non_debug_code_equal": before_code == after_code,
              "pe_tables_before": tables_before, "pe_tables_after": tables_after,
              "imports_exports_equal": tables_before == tables_after,
              "remaining_private_paths": remaining, "original_unchanged": inventory(original) == before,
              "provider_admitted": False}
    write_json(output / "result.json", report)
    if (not row["process"]["passed"] or any(not item["process"]["passed"] for item in static_rows.values())
            or before_code != after_code or tables_before != tables_after or remaining or not report["original_unchanged"]):
        raise ContractError("Stripped successor failed byte-sensitive verification")
    print(json.dumps({"stage": str(stage), "files": len(after),
                      "non_debug_code_equal": True, "remaining_private_paths": remaining,
                      "result_sha256": digest(output / "result.json")}), flush=True)


if __name__ == "__main__":
    main()
