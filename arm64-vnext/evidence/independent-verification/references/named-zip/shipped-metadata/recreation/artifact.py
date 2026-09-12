"""Receipt-bound native Git Bash assembly and deterministic archive support."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import tarfile
import zipfile


class ArtifactError(ValueError):
    pass


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, record):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write("\n")


def safe_path(name):
    name = name.removeprefix("./").rstrip("/")
    if not name or "\\" in name or ":" in name or any(part in ("", ".", "..") for part in name.split("/")):
        raise ArtifactError(f"Unsafe package path: {name}")
    return name


def pe_identity(path):
    data = Path(path).read_bytes()
    if not data.startswith(b"MZ"):
        if Path(path).suffix.lower() in (".exe", ".dll", ".pyd", ".ocx", ".cpl", ".scr"):
            raise ArtifactError(f"Expected executable image has no DOS header: {path}")
        return {"format": "non-PE", "machine": None, "imports": [], "delay_imports": []}

    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ArtifactError("Truncated PE structure")
        return struct.unpack_from(fmt, data, offset)

    pe = unpack("<I", 60)[0]
    if pe < 64 or data[pe:pe + 4] != b"PE\0\0":
        raise ArtifactError("Invalid PE signature")
    machine, count = unpack("<HH", pe + 4)
    optional = pe + 24
    optional_size = unpack("<H", pe + 20)[0]
    magic = unpack("<H", optional)[0]
    if magic not in (0x10b, 0x20b) or count == 0 or count > 96:
        raise ArtifactError("Unsupported PE headers")
    directories = optional + (112 if magic == 0x20b else 96)
    directory_count = unpack("<I", directories - 4)[0]
    if optional_size < directories - optional or optional + optional_size > len(data):
        raise ArtifactError("Invalid PE optional-header length")
    sections = []
    for index in range(count):
        start = optional + optional_size + index * 40
        _, virtual, size, raw = unpack("<IIII", start + 8)
        if raw + size > len(data):
            raise ArtifactError("PE section outside file")
        sections.append((virtual, size, raw))

    def rva_offset(rva, length):
        matches = [raw + rva - virtual for virtual, size, raw in sections
                   if virtual <= rva and rva + length <= virtual + size]
        if len(matches) != 1:
            raise ArtifactError("Unmapped or ambiguous PE directory RVA")
        return matches[0]

    def directory(index):
        if directory_count <= index:
            return 0, 0
        offset = directories + index * 8
        if offset + 8 > optional + optional_size:
            raise ArtifactError("PE directory count exceeds header")
        return unpack("<II", offset)

    def cstring(rva):
        offset = rva_offset(rva, 1)
        end = data.find(b"\0", offset, min(len(data), offset + 512))
        if end <= offset:
            raise ArtifactError("Invalid PE DLL name")
        value = data[offset:end].decode("ascii")
        if not re.fullmatch(r"[-+a-zA-Z0-9_.]+", value):
            raise ArtifactError("PE import contains a path")
        return value.lower()

    def imported(index, stride, name_index):
        rva, size = directory(index)
        if not rva:
            return []
        offset = rva_offset(rva, size)
        names = []
        for relative in range(0, size, stride):
            if relative + stride > size:
                break
            words = unpack("<" + "I" * (stride // 4), offset + relative)
            if not any(words):
                return sorted(set(names))
            if index == 13 and not words[0] & 1:
                raise ArtifactError("Legacy VA-based delay imports need explicit support")
            names.append(cstring(words[name_index]))
        raise ArtifactError("Unterminated PE import descriptors")

    managed = directory(14)[0] != 0
    return {"format": "PE32+" if magic == 0x20b else "PE32", "machine": f"0x{machine:04X}",
            "managed": managed, "imports": imported(1, 20, 3), "delay_imports": imported(13, 32, 1)}


def inventory(root):
    root = Path(root)
    result, seen = {}, set()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ArtifactError(f"Unresolved artifact link: {path}")
        if path.is_dir():
            continue
        name = safe_path(path.relative_to(root).as_posix())
        if name.casefold() in seen:
            raise ArtifactError(f"Case-colliding artifact path: {name}")
        seen.add(name.casefold())
        result[name] = {"size": path.stat().st_size, "sha256": sha256(path), **pe_identity(path)}
    if not result:
        raise ArtifactError("Empty artifact input")
    return result


def bound_json(item):
    path = Path(item["path"])
    if sha256(path) != item["sha256"]:
        raise ArtifactError(f"Changed admission/provenance receipt: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def selected(name, component):
    if "include_files" in component:
        return name in component["include_files"]
    includes = component.get("include", [""])
    excludes = component.get("exclude", [])
    return any(name.startswith(prefix) for prefix in includes) and not any(name.startswith(prefix) for prefix in excludes)


def package_entries(component):
    path = Path(component["path"])
    if sha256(path) != component["sha256"]:
        raise ArtifactError(f"Package archive changed: {path}")
    with tarfile.open(path, "r:*") as archive:
        members = {}
        for item in archive.getmembers():
            name = item.name.removeprefix("./").rstrip("/")
            if name in ("", ".", ".PKGINFO", ".BUILDINFO", ".MTREE", ".INSTALL"):
                continue
            name = safe_path(name)
            if name in members:
                raise ArtifactError(f"Duplicate package member: {name}")
            members[name] = item

        def resolve(name, visiting):
            if name in visiting or name not in members:
                raise ArtifactError(f"Broken/cyclic package link: {name}")
            item = members[name]
            if item.isfile():
                with archive.extractfile(item) as stream:
                    return stream.read(), None
            if item.islnk():
                target = safe_path(item.linkname)
            elif item.issym():
                target_parts = list(PurePosixPath(name).parent.parts)
                for part in PurePosixPath(item.linkname).parts:
                    if part == "..":
                        if not target_parts:
                            raise ArtifactError("Package link escapes root")
                        target_parts.pop()
                    elif part not in ("", "."):
                        if part == "/":
                            raise ArtifactError("Absolute package symlink")
                        target_parts.append(part)
                target = safe_path("/".join(target_parts))
            else:
                raise ArtifactError(f"Unsupported package member: {name}")
            data, _ = resolve(target, visiting | {name})
            return data, {"type": "hardlink" if item.islnk() else "symlink", "target": item.linkname,
                          "output": "byte-identical materialized alias"}

        for name, item in members.items():
            if item.isdir() or not selected(name, component):
                continue
            if item.issym() and name not in component.get("materialize_symlinks", []):
                raise ArtifactError(f"Undeclared symlink materialization: {name}")
            data, alias = resolve(name, set())
            yield name, data, alias


def zip_entries(component):
    path = Path(component["path"])
    if sha256(path) != component["sha256"]:
        raise ArtifactError("ZIP package identity changed")
    with zipfile.ZipFile(path) as archive:
        seen = set()
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = safe_path(item.filename)
            if name.casefold() in seen or item.flag_bits & 1 or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ArtifactError("Unsupported ZIP package entry")
            seen.add(name.casefold())
            if selected(name, component):
                yield name, archive.read(item), None


def assemble(plan, output):
    output = Path(output).resolve()
    if output.exists():
        raise ArtifactError("Assembly requires a fresh root")
    for component in plan["components"]:
        source = Path(component["path"]).resolve()
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ArtifactError("Assembly output must not overlap an input")
    records, seen = {}, {}
    output.mkdir(parents=True)
    for component in plan["components"]:
        if not component.get("provenance") or not component["provenance"].get("source"):
            raise ArtifactError("Every component needs explicit source provenance")
        for receipt in component.get("receipts", []):
            bound_json(receipt)
        if component["kind"] == "package":
            entries = package_entries(component)
        elif component["kind"] == "zip":
            entries = zip_entries(component)
        elif component["kind"] == "file":
            source = Path(component["path"])
            if sha256(source) != component["sha256"]:
                raise ArtifactError("Selected input file changed")
            entries = [(component["destination"], source.read_bytes(), None)]
        elif component["kind"] == "tree":
            before = bound_json(component["manifest"])["files"]
            source = Path(component["path"])
            actual_names = {item.relative_to(source).as_posix() for item in source.rglob("*") if item.is_file()}
            if actual_names != set(before):
                raise ArtifactError("Provider tree file set differs from its complete manifest")
            for name, row in before.items():
                if "sha256" not in row or not (source / name).is_file() or sha256(source / name) != row["sha256"]:
                    raise ArtifactError(f"Provider file differs: {name}")
            entries = ((name, (source / name).read_bytes(), None) for name in before if selected(name, component))
        else:
            raise ArtifactError("Unsupported assembly input kind")
        for name, data, alias in entries:
            if name in component.get("map", {}):
                name = component["map"][name]
            elif component.get("strip_prefix"):
                if not name.startswith(component["strip_prefix"]):
                    raise ArtifactError("Selected entry does not match the explicit strip prefix")
                name = name.removeprefix(component["strip_prefix"])
            name = safe_path(component.get("destination_prefix", "") + name)
            if any(marker in data for marker in (b"NON-FUNCTIONAL STUB", b"toolchain-proof PLACEHOLDER")):
                raise ArtifactError(f"Rejected stub payload: {name}")
            if name.casefold() in seen and seen[name.casefold()] != name:
                raise ArtifactError(f"Case-colliding component: {name}")
            seen[name.casefold()] = name
            identity = hashlib.sha256(data).hexdigest()
            if name in records:
                if records[name]["sha256"] == identity:
                    records[name]["components"].append(component["id"])
                    continue
                if name not in component.get("replace", []):
                    raise ArtifactError(f"Undeclared component conflict: {name}")
                replaced = records[name]
            else:
                replaced = None
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            pe = pe_identity(target)
            if pe["machine"] not in (None, "0xAA64") or pe.get("managed"):
                raise ArtifactError(f"Non-native payload: {name}: {pe['machine']}")
            records[name] = {"entry_type": "file", "mode": "0755" if data.startswith((b"MZ", b"#!")) else "0644",
                             "size": len(data), "sha256": identity, **pe,
                             "components": [component["id"]], "provenance": component["provenance"],
                             "alias": alias, "replaced": replaced}
        if component["kind"] in ("package", "zip", "file") and sha256(component["path"]) != component["sha256"]:
            raise ArtifactError("Input changed during assembly")
    for name in ("tmp", "var/tmp", "etc", "home"):
        (output / name).mkdir(parents=True, exist_ok=True)
    for name, row in records.items():
        if sha256(output / name) != row["sha256"]:
            raise ArtifactError("Assembly changed before sealing")
    manifest = {"schema": 1, "status": plan.get("classification", "assembled-not-behavior-qualified"),
                "top_source": plan["top_source"], "limitations": plan.get("limitations", []), "files": records}
    write_json(output.with_name(output.name + ".manifest.json"), manifest)
    return manifest


def deterministic_zip(root, archive):
    root, archive = Path(root), Path(archive)
    if archive.exists():
        raise ArtifactError("Archive output must be fresh")
    if archive.resolve().is_relative_to(root.resolve()):
        raise ArtifactError("ZIP output must be outside the input tree")
    rows = inventory(root)
    directories = {safe_path(path.relative_to(root).as_posix()) + "/" for path in root.rglob("*") if path.is_dir()}
    names = sorted(set(rows) | directories)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as dest:
        for name in names:
            info = zipfile.ZipInfo(name, (2026, 8, 31, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o40755 << 16) | 0x10 if name in directories else 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            dest.writestr(info, b"" if name in directories else (root / name).read_bytes(), compresslevel=9)
    with zipfile.ZipFile(archive) as verify:
        if verify.namelist() != names:
            raise ArtifactError("Archive order or file set changed")
        for item in verify.infolist():
            if item.is_dir():
                if item.filename not in directories:
                    raise ArtifactError("Unexpected archive directory")
                continue
            if hashlib.sha256(verify.read(item)).hexdigest() != rows[item.filename]["sha256"]:
                raise ArtifactError("Archive readback differs")
    return {"sha256": sha256(archive), "size": archive.stat().st_size, "files": len(rows), "directories": len(directories)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    assembly = commands.add_parser("assemble")
    assembly.add_argument("--plan", type=Path, required=True)
    assembly.add_argument("--output", type=Path, required=True)
    scan = commands.add_parser("audit")
    scan.add_argument("--root", type=Path, required=True)
    scan.add_argument("--output", type=Path, required=True)
    archive = commands.add_parser("zip")
    archive.add_argument("--root", type=Path, required=True)
    archive.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "assemble":
        result = assemble(json.loads(args.plan.read_text(encoding="utf-8")), args.output)
        print(f"Assembled {len(result['files'])} files; behavior not yet qualified")
    elif args.operation == "audit":
        rows = inventory(args.root)
        write_json(args.output, {"schema": 1, "files": rows})
        print(f"Inventoried {len(rows)} files")
    else:
        print(json.dumps(deterministic_zip(args.root, args.output)))


if __name__ == "__main__":
    main()
