#!/usr/bin/env python3
"""Read raw PE exports to guard against re-exporting another module's CRT."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def exports(path):
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Not a PE image")
    machine, sections = struct.unpack_from("<HH", data, pe + 4)
    optional = pe + 24
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    if machine != 0xaa64 or struct.unpack_from("<H", data, optional)[0] != 0x20b:
        raise ValueError("Expected ARM64 PE32+")

    def offset(rva, size):
        for index in range(sections):
            header = optional + optional_size + index * 40
            virtual_size, address, raw_size, raw = struct.unpack_from("<IIII", data, header + 8)
            if address <= rva and rva + size <= address + min(virtual_size, raw_size):
                result = raw + rva - address
                if result + size <= len(data):
                    return result
        raise ValueError(f"Unmapped RVA {rva:x}")

    directory = offset(struct.unpack_from("<I", data, optional + 112)[0], 40)
    count = struct.unpack_from("<I", data, directory + 24)[0]
    table = offset(struct.unpack_from("<I", data, directory + 32)[0], count * 4)
    names = set()
    for index in range(count):
        start = offset(struct.unpack_from("<I", data, table + 4 * index)[0], 1)
        end = data.index(0, start)
        names.add(data[start:end].decode("ascii"))
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembler", required=True)
    parser.add_argument("--linker", required=True)
    parser.add_argument("--archiver", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-leaks", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    runs = []

    def run(name, command):
        result = subprocess.run(command, capture_output=True)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        runs.append({"command": command, "exit": result.returncode})
        result.check_returncode()

    reserved = ["_cygwin_dll_entry", "_msys_dll_entry", "cygwin_crt0", "msys_crt0",
                "_cygwin_crt0_common", "_msys_crt0_common", "cygwin_premain0",
                "__dso_handle", "_pei386_runtime_relocator"]
    assembly = ".text\n" + "".join(f".global {name}\n{name}:\n ret\n"
                                    for name in ["user_function"] + reserved)
    assembly += ".data\n.global user_data\nuser_data:\n .quad 73\n"
    (out / "application.s").write_text(assembly)
    (out / "runtime.s").write_text(
        ".text\n.global runtime_archive_function\nruntime_archive_function:\n ret\n")
    for name in ("application", "runtime"):
        run(name, [args.assembler, str(out / f"{name}.s"), "-o", str(out / f"{name}.o")])
    archive = out / "libmsys-2.0.a"
    run("archive", [args.archiver, "rcs", str(archive), str(out / "runtime.o")])
    common = [args.linker, "--shared", "--entry=user_function", "--export-all-symbols",
              str(out / "application.o"), "--whole-archive", str(archive), "--no-whole-archive"]
    run("default", common + ["-o", str(out / "default.dll")])
    default = exports(out / "default.dll")
    normal = {"user_function", "user_data"}
    if args.expect_leaks:
        if not {"_msys_dll_entry", "runtime_archive_function"}.issubset(default):
            raise AssertionError(f"Legacy exclusion failure not reproduced: {default}")
    else:
        if default != normal:
            raise AssertionError(f"Unexpected automatic exports: {default}")
        definition = out / "explicit.def"
        definition.write_text("EXPORTS\n _msys_dll_entry\n")
        run("explicit", common + [str(definition), "-o", str(out / "explicit.dll")])
        if exports(out / "explicit.dll") != normal | {"_msys_dll_entry"}:
            raise AssertionError("An explicitly requested export was suppressed")
    report = {
        "passed": True, "legacy": args.expect_leaks, "automatic_exports": sorted(default),
        "runs": runs, "tools": {tool: hashlib.sha256(Path(tool).read_bytes()).hexdigest()
                                for tool in (args.assembler, args.linker, args.archiver)},
    }
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
