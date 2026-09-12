"""Seal a real installed GDBM stage with relocatable development metadata."""

import argparse
import json
from pathlib import Path
import re
import shutil
import struct

from db_package import pe_metadata
from sources import ContractError, digest, inventory
from ssh_bootstrap import write_json


def image_sections(data):
    pe = struct.unpack_from("<I", data, 60)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    symbols, symbol_count = struct.unpack_from("<II", data, pe + 12)
    strings = symbols + symbol_count * 18
    table = pe + 24 + optional_size
    for index in range(count):
        entry = table + index * 40
        name = data[entry:entry + 8].rstrip(b"\0").decode("ascii")
        if name.startswith("/"):
            if not name[1:].isdigit() or strings + 4 > len(data):
                raise ContractError("Invalid COFF long section name")
            table_size = struct.unpack_from("<I", data, strings)[0]
            start = strings + int(name[1:])
            end = data.find(b"\0", start, min(strings + table_size, len(data)))
            if not strings + 4 <= start < end:
                raise ContractError("Unresolved COFF long section name")
            name = data[start:end].decode("ascii")
        size, offset = struct.unpack_from("<II", data, entry + 16)
        yield name, data[offset:offset + size]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01"):
        raise ContractError("Only the explicitly owned GDBM stage is permitted")
    stage = root / "stage"
    before = inventory(stage)
    if not before:
        raise ContractError("A real completed make install is required")
    license_path = stage / "usr/share/licenses/gdbm/COPYING"
    license_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "source/COPYING", license_path)
    substitutions = {}
    for path in (stage / "usr/lib").glob("*.la"):
        text = path.read_text()
        corrected = text
        for prefix in ("/c/" + root.relative_to(root.anchor).as_posix(), root.as_posix()):
            corrected = corrected.replace("-L" + prefix + "/dependencies/usr/lib", "-L/usr/lib")
        if corrected != text:
            before_sha = digest(path)
            path.write_text(corrected, newline="\n")
            substitutions[str(path.relative_to(stage))] = {
                "before": before_sha, "after": digest(path),
                "scope": "Only explicit private dependency staging search directory -> canonical /usr/lib"}
        if re.search(r"(?i)(?:C:|/c/)(?:[\\/])?ag-", corrected):
            raise ContractError("Unrelocated private path remains in installed libtool metadata")
    images = []
    for path in sorted((stage / "usr/bin").iterdir()):
        if path.suffix not in (".exe", ".dll"):
            raise ContractError("Unexpected GDBM runtime payload")
        data = path.read_bytes()
        metadata = pe_metadata(data)
        private_sections = []
        for name, payload in image_sections(data):
            if any(word.encode(encoding) in payload
                   for word in ("ag-gdbm-", "ap06-78", "ag-db-e138")
                   for encoding in ("ascii", "utf-16le")):
                private_sections.append(name)
                if not name.startswith(".debug"):
                    raise ContractError(f"Private build path in non-debug PE section: {path.name} {name}")
        images.append({"path": str(path.relative_to(stage)), "sha256": digest(path),
                       "size": len(data), **metadata, "private_path_sections": private_sections})
    if len(images) != 5 or sum(row["is_dll"] for row in images) != 2:
        raise ContractError("Expected all three GDBM tools and both native shared libraries")
    for name in ("gdbm.h", "gdbm/ndbm.h", "gdbm/dbm.h"):
        if not (stage / "usr/include" / name).is_file():
            raise ContractError(f"Required installed compatibility header missing: {name}")
    for name in ("libgdbm.a", "libgdbm.dll.a", "libgdbm_compat.a", "libgdbm_compat.dll.a"):
        if not (stage / "usr/lib" / name).is_file():
            raise ContractError(f"Required native static/import library missing: {name}")
    if not list((stage / "usr/share/locale").glob("*/LC_MESSAGES/gdbm.mo")):
        raise ContractError("The full-NLS GDBM stage has no genuine message catalogs")
    after = inventory(stage)
    for name, row in before.items():
        if name.endswith((".exe", ".dll", ".a")) and after[name] != row:
            raise ContractError("Native code changed during metadata relocation")
    write_json(root / "stage.json", {
        "schema": 1, "status": "native-full-NLS-GDBM-stage-sealed-not-provider-admitted",
        "files": after, "files_before_metadata_relocation": before,
        "metadata_substitutions": substitutions, "pe_images": images,
        "license_source_sha256": digest(root / "source/COPYING"),
        "provider_admitted": False})
    print(json.dumps({"files": len(after), "PE": len(images), "stage_sha256": digest(root / "stage.json")}), flush=True)


if __name__ == "__main__":
    main()
