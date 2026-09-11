"""Independent archive intake, PE import reading and embedded-path search. No producer verdict is reused."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import zipfile

from observe import save, sha


def inspect_pe(path):
    data = path.read_bytes()

    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ValueError(f"PE offset out of bounds: {path}/{offset}")
        return struct.unpack_from(fmt, data, offset)

    if data[:2] != b"MZ":
        raise ValueError(f"Not a PE image: {path}")
    pe = unpack("<I", 60)[0]
    if pe < 64 or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"Invalid PE header: {path}")
    machine, section_count = unpack("<HH", pe + 4)
    symbol_table, symbol_count = unpack("<II", pe + 12)
    string_table = symbol_table + symbol_count * 18 if symbol_table else 0
    optional_size, flags = unpack("<HH", pe + 20)
    optional = pe + 24
    magic = unpack("<H", optional)[0]
    if magic not in (0x20B, 0x10B):
        raise ValueError(f"Unsupported PE optional header: {path}")
    directory = optional + (112 if magic == 0x20B else 96)
    word = 8 if magic == 0x20B else 4
    sections = []
    for index in range(section_count):
        offset = optional + optional_size + 40 * index
        name = data[offset:offset + 8].rstrip(b"\0").decode("ascii", errors="backslashreplace")
        if name.startswith("/") and name[1:].isdecimal() and string_table:
            string_offset = string_table + int(name[1:])
            string_size = unpack("<I", string_table)[0]
            if not string_table + 4 <= string_offset < string_table + string_size <= len(data):
                raise ValueError("COFF long section name outside string table")
            end = data.find(b"\0", string_offset, string_table + string_size)
            if end == -1:
                raise ValueError("Unterminated COFF section name")
            name = data[string_offset:end].decode("ascii")
        virtual_size, virtual, raw_size, raw = unpack("<IIII", offset + 8)
        if raw + raw_size > len(data):
            raise ValueError(f"PE raw section outside file: {path}")
        sections.append({"name": name, "virtual": virtual, "virtual_size": virtual_size,
                         "raw": raw, "raw_size": raw_size})

    def section_for(rva, size=1):
        hits = [s for s in sections if s["virtual"] <= rva and rva + size <= s["virtual"] + s["raw_size"]]
        if len(hits) != 1:
            raise ValueError(f"Unmapped or ambiguous PE RVA: {path}/{rva}")
        s = hits[0]
        return s["raw"] + rva - s["virtual"], s["raw"] + s["raw_size"]

    def string(rva):
        start, end = section_for(rva)
        stop = data.find(b"\0", start, end)
        if stop <= start:
            raise ValueError("Empty or unterminated import string")
        return data[start:stop].decode("ascii")

    imports = []
    count = unpack("<I", directory - 4)[0]
    for entry, size in ((1, 20), (13, 32)):
        if count <= entry:
            continue
        if directory + (entry + 1) * 8 > optional + optional_size:
            raise ValueError("PE directory outside optional header")
        rva, length = unpack("<II", directory + 8 * entry)
        if not rva:
            continue
        start, end = section_for(rva, size)
        while True:
            if start + size > end:
                raise ValueError("Unterminated import descriptors")
            values = unpack("<" + "I" * (size // 4), start)
            if not any(values):
                break
            if entry == 1:
                original, _, _, name, first = values
                thunk = original or first
            else:
                attributes, name, _, first, thunk, _, _, _ = values
                if attributes != 1:
                    raise ValueError("VA-form delay imports are not covered by this reader")
                thunk = thunk or first
            ptr, limit = section_for(thunk, word)
            symbols = []
            while True:
                if ptr + word > limit:
                    raise ValueError("Unterminated import thunk")
                value = unpack("<Q" if word == 8 else "<I", ptr)[0]
                if value == 0:
                    break
                symbols.append({"ordinal": value & 0xFFFF} if value & (1 << (word * 8 - 1))
                               else {"name": string(value + 2)})
                ptr += word
            imports.append({"dll": string(name), "kind": "normal" if entry == 1 else "delay",
                            "symbols": symbols})
            start += size
    return {"machine": f"0x{machine:04X}", "pe32_plus": magic == 0x20B,
            "dll": bool(flags & 0x2000), "imports": imports, "sections": sections}


def inventory(root):
    rows = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Extracted reparse point: {path}")
        if path.is_file():
            rows[path.relative_to(root).as_posix()] = {"sha256": sha(path), "size": path.stat().st_size}
    return rows


def intake(archive, receipt, output, claimed_archive_sha, claimed_receipt_sha):
    archive, receipt, output = Path(archive), Path(receipt), Path(output)
    actual_archive, actual_receipt = sha(archive), sha(receipt)
    if (actual_archive, actual_receipt) != (claimed_archive_sha, claimed_receipt_sha):
        raise ValueError(f"Candidate/receipt hash mismatch: {actual_archive}/{actual_receipt}")
    output.mkdir()
    extraction = output / "relocated at a different depth" / "candidate with spaces"
    extraction.mkdir(parents=True)
    members, seen = [], set()
    with zipfile.ZipFile(archive) as zip:
        for entry in zip.infolist():
            name = entry.filename
            canonical = name.rstrip("/")
            parts = canonical.split("/")
            if not canonical or "\\" in canonical or ":" in canonical or any(p in ("", ".", "..") for p in parts):
                raise ValueError(f"Unsafe ZIP member: {name}")
            if canonical.casefold() in seen or PurePosixPath(canonical).is_absolute():
                raise ValueError(f"Duplicate/colliding ZIP member: {name}")
            seen.add(canonical.casefold())
            mode = entry.external_attr >> 16
            if (entry.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or entry.external_attr & 0x400):
                raise ValueError(f"Unsupported encrypted/link/reparse ZIP member: {name}")
            target = extraction.joinpath(*parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip.open(entry) as source, target.open("xb") as dest:
                    while data := source.read(1024 * 1024):
                        dest.write(data)
            members.append({"name": name, "size": entry.file_size, "compressed": entry.compress_size,
                            "time": entry.date_time, "create_system": entry.create_system,
                            "attributes": entry.external_attr, "compression": entry.compress_type})
    files = inventory(extraction)
    result = {"archive": {"path": str(archive), "sha256": actual_archive, "size": archive.stat().st_size},
              "producer_receipt": {"path": str(receipt), "sha256": actual_receipt},
              "extraction": str(extraction), "members": members, "files": files,
              "environment_changes": [], "artifact_repairs": []}
    save(output / "intake.json", result)
    return result


def tree_intake(source, manifest, output, claimed_manifest_sha):
    source, manifest, output = Path(source), Path(manifest), Path(output)
    actual_manifest_sha = sha(manifest)
    if actual_manifest_sha != claimed_manifest_sha:
        raise ValueError(f"Claimed tree manifest hash differs: {actual_manifest_sha}")
    stated = json.loads(manifest.read_text(encoding="utf-8"))
    before = inventory(source)
    expected = {name: {k: row[k] for k in ("sha256", "size")} for name, row in stated["files"].items()}
    mismatches = [{"path": name, "actual": before.get(name), "claimed": expected.get(name)}
                  for name in sorted(before.keys() | expected.keys()) if before.get(name) != expected.get(name)]
    output.mkdir()
    extraction = output / "relocated at a different depth" / "candidate with spaces"
    extraction.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            (extraction / path.relative_to(source)).mkdir(parents=True, exist_ok=True)
    for name in before:
        destination = extraction / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    copied, after = inventory(extraction), inventory(source)
    if copied != before or after != before or sha(manifest) != actual_manifest_sha:
        raise ValueError("Tree or manifest changed across independent copying")
    excluded = [name for name, row in stated["files"].items()
                if any(re.search(r"(?i)(?:^|-)(?:tcl|tk|itcl)(?:$|-)", c)
                       for c in row.get("components", []))]
    result = {"classification": "NON-ADMITTED experimental candidate-01, not final MVP acceptance",
              "source": str(source), "producer_manifest": {"path": str(manifest), "sha256": actual_manifest_sha},
              "extraction": str(extraction), "files": before, "manifest_mismatches": mismatches,
              "source_unchanged": True, "copy_byte_identical": True,
              "tcl_conflict_scope_excluded_from_functional_judgment": excluded,
              "producer_limitations": stated.get("limitations", []),
              "artifact_repairs": [], "environment_changes": []}
    save(output / "intake.json", result)
    return result


def static_audit(root, output):
    root, output = Path(root), Path(output)
    files = inventory(root)
    pe, parse_errors, strings = {}, [], []
    patterns = [
        re.compile(rb"(?i)(?:[a-z]:[/\\](?:ag[-\\/]|users[/\\]|build[/\\]|agent[/\\])"
                   rb"|/(?:root|home|c/ag-|clangarm64|mingwarm64|usr/local)/)[^\x00\r\n]{0,220}"),
        re.compile(rb"(?i)(?:\.copilot[/\\]|copilot-worktrees|session-state|resume-2026)[^\x00\r\n]{0,220}"),
    ]
    for name in files:
        path = root / name
        data = path.read_bytes()
        is_pe = data[:2] == b"MZ"
        if is_pe or path.suffix.lower() in (".exe", ".dll", ".pyd", ".ocx", ".cpl", ".scr"):
            try:
                pe[name] = {**files[name], **inspect_pe(path)}
            except (ValueError, UnicodeError, struct.error) as error:
                parse_errors.append({"path": name, "error": str(error)})
        hits = []
        for pattern in patterns:
            for match in pattern.finditer(data):
                offset = match.start()
                section = next((s["name"] for s in pe.get(name, {}).get("sections", [])
                                if s["raw"] <= offset < s["raw"] + s["raw_size"]), None)
                hits.append({"offset": offset, "section": section,
                             "value": match.group().decode("utf-8", errors="backslashreplace")})
        # UTF-16LE paths are checked independently, without rewriting the binary.
        for match in re.finditer(rb"(?:[ -~]\x00){12,}", data):
            text = match.group().decode("utf-16le")
            if re.search(r"(?i)([a-z]:[/\\](ag[-\\/]|users[/\\])|/root/|\.copilot|session-state)", text):
                hits.append({"offset": match.start(), "encoding": "utf-16le", "value": text[:240]})
        if hits:
            strings.append({"file": name, "is_pe": is_pe, "matches": hits})
    dlls = {}
    for name in pe:
        dlls.setdefault(Path(name).name.lower(), []).append(name)
    closure = []
    for name, image in pe.items():
        for imported in image["imports"]:
            dll = imported["dll"].lower()
            local = dlls.get(dll, [])
            system = Path(os.environ["SystemRoot"]) / "System32" / imported["dll"]
            record = {"consumer": name, "dll": imported["dll"], "kind": imported["kind"],
                      "bundled_candidates": local}
            if local:
                record["classification"] = "bundled-file-candidates-not-live-resolution"
            elif dll.startswith(("api-ms-win-", "ext-ms-win-")):
                record["classification"] = "Windows-api-set-contract-not-shipped-file"
            elif system.is_file():
                record.update(classification="existing-System32-file", system_path=str(system),
                              system_sha256=sha(system), system_machine=inspect_pe(system)["machine"])
            else:
                record["classification"] = "unresolved-static-import"
            closure.append(record)
    result = {"files": len(files), "pe": pe, "non_aa64": [name for name, p in pe.items() if p["machine"] != "0xAA64"],
              "pe_parse_errors": parse_errors, "static_import_closure": closure,
              "embedded_paths": strings,
              "scope": "No execution; embedded paths are candidates, not proof of runtime dependence. "
                       "DWARF/debug paths remain labelled separately from operational strings."}
    save(output / "static-audit.json", result)
    return result
