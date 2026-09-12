"""Compare link-visible COFF symbols and resolved relocations after debug stripping."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from gdbm_strip_stage import archive_members, object_sections
from sources import ContractError, digest
from ssh_bootstrap import write_json


def link_metadata(data):
    machine, count = struct.unpack_from("<HH", data)
    if machine != 0xAA64:
        raise ContractError("Expected ordinary ARM64 COFF")
    symbol_table, symbol_count = struct.unpack_from("<II", data, 8)
    strings = symbol_table + symbol_count * 18
    string_size = struct.unpack_from("<I", data, strings)[0]
    section_table = 20 + struct.unpack_from("<H", data, 16)[0]

    def string(offset):
        start = strings + offset
        end = data.find(b"\0", start, min(len(data), strings + string_size))
        if offset < 4 or end < start:
            raise ContractError("Invalid COFF long name")
        return data[start:end].decode("utf-8")

    sections = []
    for index in range(count):
        entry = section_table + index * 40
        name = data[entry:entry + 8].rstrip(b"\0").decode("ascii")
        if name.startswith("/"):
            name = string(int(name[1:]))
        sections.append({"name": name, "entry": entry})
    symbols, auxiliary = {}, {}
    index = 0
    while index < symbol_count:
        offset = symbol_table + index * 18
        record = data[offset:offset + 18]
        if len(record) != 18:
            raise ContractError("Truncated COFF symbol")
        name = (string(struct.unpack_from("<I", record, 4)[0]) if record[:4] == b"\0" * 4
                else record[:8].rstrip(b"\0").decode("utf-8"))
        value, section, kind, storage, aux = struct.unpack_from("<IhHBB", record, 8)
        section_name = sections[section - 1]["name"] if section > 0 else str(section)
        symbols[index] = {"name": name, "value": value, "section": section_name,
                          "type": kind, "storage": storage}
        if aux:
            auxiliary[index] = data[offset + 18:offset + 18 * (aux + 1)]
        index += 1 + aux
    globals_ = []
    for index, row in symbols.items():
        if row["storage"] in (2, 105):
            record = dict(row)
            if row["storage"] == 105:
                target, search = struct.unpack_from("<II", auxiliary[index])
                record["weak_fallback"] = symbols[target]
                record["weak_search"] = search
            globals_.append(record)
    relocations = {}
    for section in sections:
        if section["name"].startswith(".debug"):
            continue
        offset = struct.unpack_from("<I", data, section["entry"] + 24)[0]
        count = struct.unpack_from("<H", data, section["entry"] + 32)[0]
        if count == 0xFFFF:
            count = struct.unpack_from("<I", data, offset)[0] - 1
            offset += 10
        records = []
        for number in range(count):
            address, symbol, kind = struct.unpack_from("<IIH", data, offset + number * 10)
            if symbol not in symbols:
                raise ContractError("COFF relocation does not refer to a real symbol")
            records.append({"address": address, "type": kind, "target": symbols[symbol]})
        relocations[section["name"]] = records
    return {"machine": hex(machine), "global_weak_symbols": globals_, "non_debug_relocations": relocations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01"):
        raise ContractError("Explicit owned archive audit required")
    output = root / "static-archive-audit02"
    output.mkdir()
    result = {"schema": 1, "archives": {}}
    for name in ("libgdbm.a", "libgdbm_compat.a"):
        before_path = root / "stage/usr/lib" / name
        after_path = root / "stage-stripped02/usr/lib" / name
        before, after = archive_members(before_path), archive_members(after_path)
        if list(before) != list(after):
            raise ContractError("Static archive member set/order changed")
        comparisons = {}
        for member in before:
            old, new = link_metadata(before[member]), link_metadata(after[member])
            comparisons[member] = {
                "before_sha256": hashlib.sha256(before[member]).hexdigest(),
                "after_sha256": hashlib.sha256(after[member]).hexdigest(),
                "non_debug_bytes_equal": object_sections(before[member]) == object_sections(after[member]),
                "link_metadata_equal": old == new, "link_metadata": new,
            }
        result["archives"][name] = {
            "before_sha256": digest(before_path), "after_sha256": digest(after_path),
            "before_size": before_path.stat().st_size, "after_size": after_path.stat().st_size,
            "member_order_equal": list(before) == list(after), "members": comparisons}
    result["passed"] = all(row["member_order_equal"] and all(
        member["non_debug_bytes_equal"] and member["link_metadata_equal"] for member in row["members"].values())
        for row in result["archives"].values())
    write_json(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "archives": {
        name: {"members": len(row["members"]), "before_size": row["before_size"], "after_size": row["after_size"]}
        for name, row in result["archives"].items()}}), flush=True)
    if not result["passed"]:
        raise ContractError("Static archive code, symbol or relocation semantics changed")


if __name__ == "__main__":
    main()
