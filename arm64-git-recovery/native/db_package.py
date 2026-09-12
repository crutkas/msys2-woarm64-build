"""Create and read back genuine pacman DB split archives from a receipt-bound stage."""

import gzip
import hashlib
import io
from pathlib import Path
import re
import struct
import tarfile

from sources import ContractError, digest, relative_path


VERSION = "6.2.32-6"
SPLITS = {
    "db": {"description": "The Berkeley DB embedded database system", "depends": ["libdb=6.2.32"]},
    "libdb": {"description": "Berkeley DB C and C++ runtime libraries", "depends": ["gcc-libs"]},
    "libdb-devel": {"description": "Berkeley DB headers and static/import libraries", "depends": ["libdb=6.2.32"]},
    "db-docs": {"description": "Berkeley DB documentation", "depends": []},
}


def pe_metadata(data):
    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ContractError("PE structure outside file")
        return struct.unpack_from(fmt, data, offset)

    if data[:2] != b"MZ":
        raise ContractError("Expected native PE image")
    pe = unpack("<I", 60)[0]
    if pe < 64 or data[pe:pe + 4] != b"PE\0\0":
        raise ContractError("Invalid PE signature")
    machine, count = unpack("<HH", pe + 4)
    optional_size, characteristics = unpack("<HH", pe + 20)
    optional = pe + 24
    if machine != 0xAA64 or unpack("<H", optional)[0] != 0x20B or optional_size < 128:
        raise ContractError("Every delivered PE must be ordinary ARM64 AA64 PE32+")
    sections = []
    for index in range(count):
        virtual_size, rva, raw_size, raw = unpack("<IIII", optional + optional_size + index * 40 + 8)
        if raw + raw_size > len(data):
            raise ContractError("PE section outside file")
        sections.append((rva, raw_size, raw))

    def offset(rva, size=1):
        matches = [raw + rva - start for start, length, raw in sections if start <= rva and rva + size <= start + length]
        if len(matches) != 1:
            raise ContractError("Missing or ambiguous PE RVA")
        return matches[0]

    imports = []
    if unpack("<I", optional + 108)[0] >= 2:
        rva, size = unpack("<II", optional + 120)
        if rva:
            for relative in range(0, size, 20):
                row = unpack("<IIIII", offset(rva + relative, 20))
                if row == (0, 0, 0, 0, 0):
                    break
                start = offset(row[3])
                end = data.find(b"\0", start, min(len(data), start + 256))
                if end < 0:
                    raise ContractError("Unterminated imported DLL")
                imports.append(data[start:end].decode("ascii"))
            else:
                raise ContractError("Unterminated PE import table")
    return {"machine": "0xAA64", "pe32_plus": True, "is_dll": bool(characteristics & 0x2000),
            "imports": sorted(set(imports), key=str.lower)}


def split_for(path):
    if path.startswith("usr/bin/"):
        if path.endswith(".exe"):
            return "db"
        if path.endswith(".dll"):
            return "libdb"
    if path.startswith(("usr/include/", "usr/lib/")):
        return "libdb-devel"
    if path.startswith("usr/share/doc/"):
        return "db-docs"
    if path == "usr/share/licenses/db/LICENSE":
        return "libdb"
    raise ContractError(f"Unassigned DB package file: {path}")


def split_inventory(files):
    result = {name: {} for name in SPLITS}
    for name, row in files.items():
        relative_path(name)
        if set(row) != {"sha256", "size"}:
            raise ContractError("DB package files must be regular, size/hash-bound entries")
        result[split_for(name)][name] = row
    if any(not payload for payload in result.values()):
        raise ContractError("A required DB package split is empty")
    return result


def escape_mtree(value):
    return "".join(f"\\{ord(char):03o}" if char in " \t\n\\#" else char for char in value)


def create_package(stage, output, name, files, epoch, recipe_sha, builddir):
    if name not in SPLITS or output.exists():
        raise ContractError("Package output must be new and recipe-named")
    metadata = [
        f"pkgname = {name}", "pkgbase = db", f"pkgver = {VERSION}",
        f"pkgdesc = {SPLITS[name]['description']}", "url = https://www.oracle.com/database/berkeley-db/",
        f"builddate = {epoch}", "packager = Native ARM64 recovery (unsigned local artifact)",
        f"size = {sum(row['size'] for row in files.values())}", "arch = aarch64", "license = AGPL-3.0-or-later",
        *[f"depend = {dep}" for dep in SPLITS[name]["depends"]],
    ]
    pkginfo = ("\n".join(metadata) + "\n").encode()
    buildinfo = ("\n".join([
        "format = 2", f"pkgname = {name}", "pkgbase = db", f"pkgver = {VERSION}", "pkgarch = aarch64",
        f"pkgbuild_sha256 = {recipe_sha}", "packager = Native ARM64 recovery (unsigned local artifact)",
        f"builddate = {epoch}", f"builddir = {builddir}", "startdir = /usr/src/db",
        "buildtool = db_package.py", "buildtoolver = 1", "buildenv = !distcc",
        "buildenv = !ccache", "buildenv = !sign", "options = staticlibs", "options = !strip",
    ]) + "\n").encode()
    entries = {".PKGINFO": pkginfo, ".BUILDINFO": buildinfo}
    modes = {path: 0o755 if path.endswith((".exe", ".dll")) else 0o644 for path in files}
    lines = ["#mtree", "/set type=file uid=0 gid=0 mode=644"]
    for path, data in entries.items():
        lines.append(f"./{path} time={epoch}.0 size={len(data)} sha256digest={hashlib.sha256(data).hexdigest()}")
    for path, row in sorted(files.items()):
        lines.append(f"./{escape_mtree(path)} mode={modes[path]:o} time={epoch}.0 size={row['size']} sha256digest={row['sha256']}")
    entries[".MTREE"] = gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0)
    # Python 3.14's standard-library zstd writer avoids invoking an emulated package tool.
    with tarfile.open(output, "x:zst", level=10, format=tarfile.PAX_FORMAT) as archive:
        for path, data in entries.items():
            info = tarfile.TarInfo(path)
            info.size, info.mode, info.mtime = len(data), 0o644, epoch
            archive.addfile(info, io.BytesIO(data))
        for path, row in sorted(files.items()):
            source = stage / path
            if source.stat().st_size != row["size"] or digest(source) != row["sha256"]:
                raise ContractError(f"Package source changed: {path}")
            info = tarfile.TarInfo(path)
            info.size, info.mode, info.mtime = row["size"], modes[path], epoch
            with source.open("rb") as stream:
                archive.addfile(info, stream)
    return readback_package(output, name, files, recipe_sha)


def parse_metadata(data):
    result = {}
    for line in data.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([a-z][a-z0-9_]*) = (.+)", line)
        if not match:
            raise ContractError("Malformed ALPM metadata field")
        result.setdefault(match[1], []).append(match[2])
    return result


def validate_metadata(metadata, name, files, recipe_sha):
    pkg = parse_metadata(metadata[".PKGINFO"])
    build = parse_metadata(metadata[".BUILDINFO"])
    for key, value in {"pkgname": name, "pkgbase": "db", "pkgver": VERSION, "arch": "aarch64",
                       "size": str(sum(row["size"] for row in files.values())),
                       "license": "AGPL-3.0-or-later"}.items():
        if pkg.get(key) != [value]:
            raise ContractError(f"Package metadata differs: {key}")
    if pkg.get("depend", []) != SPLITS[name]["depends"] or any(key in pkg for key in ("provides", "conflict", "replaces")):
        raise ContractError("Package dependency/provider metadata differs")
    for key in ("packager", "builddate"):
        if len(pkg.get(key, [])) != 1 or not pkg[key][0]:
            raise ContractError(f"Missing package metadata: {key}")
    if not pkg["builddate"][0].isdecimal():
        raise ContractError("Invalid package build date")
    for key, value in {"format": "2", "pkgname": name, "pkgbase": "db", "pkgver": VERSION,
                       "pkgarch": "aarch64", "buildtool": "db_package.py", "buildtoolver": "1",
                       "builddate": pkg["builddate"][0], "packager": pkg["packager"][0]}.items():
        if build.get(key) != [value]:
            raise ContractError(f"Build metadata differs: {key}")
    checksum = build.get("pkgbuild_sha256", [])
    if (len(checksum) != 1 or not re.fullmatch("[0-9a-f]{64}", checksum[0])
            or (recipe_sha is not None and checksum[0] != recipe_sha)):
        raise ContractError("Build recipe checksum differs")
    if build.get("buildenv") != ["!distcc", "!ccache", "!sign"] or build.get("options") != ["staticlibs", "!strip"]:
        raise ContractError("Build environment/options metadata differs")
    for key in ("builddir", "startdir"):
        if len(build.get(key, [])) != 1 or not build[key][0]:
            raise ContractError(f"Missing build metadata: {key}")
    return pkg, build


def validate_mtree(data, files, metadata, epoch):
    expected = {**files, **{name: {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
                           for name, value in metadata.items() if name != ".MTREE"}}
    actual = {}
    lines = gzip.decompress(data).decode("utf-8").splitlines()
    if lines[:2] != ["#mtree", "/set type=file uid=0 gid=0 mode=644"]:
        raise ContractError("Unexpected package mtree defaults")
    for line in lines[2:]:
        parts = line.split()
        if not parts or not parts[0].startswith("./"):
            raise ContractError("Malformed package mtree entry")
        path = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), parts[0][2:])
        relative_path(path)
        if path in actual or any("=" not in field for field in parts[1:]):
            raise ContractError("Duplicate or malformed package mtree entry")
        fields = dict(field.split("=", 1) for field in parts[1:])
        if len(fields) != len(parts) - 1:
            raise ContractError("Duplicate package mtree field")
        mode = "755" if path.endswith((".exe", ".dll")) else "644"
        if fields.get("mode", "644") != mode or fields.get("time") != epoch + ".0":
            raise ContractError("Package mtree mode/time differs")
        if not fields.get("size", "").isdecimal():
            raise ContractError("Invalid package mtree size")
        actual[path] = {"size": int(fields["size"]), "sha256": fields.get("sha256digest")}
    if actual != expected:
        raise ContractError("Package mtree path/size/hash tuples differ from the complete payload")


def readback_package(path, name, expected, recipe_sha=None):
    actual, metadata, seen, pe = {}, {}, set(), []
    with tarfile.open(path, "r:zst") as archive:
        for entry in archive:
            relative_path(entry.name)
            if not entry.isfile() or entry.name in seen:
                raise ContractError("Unexpected non-file or duplicate package entry")
            mode = 0o755 if entry.name.endswith((".exe", ".dll")) else 0o644
            if entry.mode != mode or entry.uid != 0 or entry.gid != 0:
                raise ContractError("Package archive ownership or permissions differ")
            seen.add(entry.name)
            stream = archive.extractfile(entry)
            if stream is None:
                raise ContractError("Missing package entry data")
            data = stream.read()
            if entry.name in (".PKGINFO", ".BUILDINFO", ".MTREE"):
                metadata[entry.name] = data
                continue
            actual[entry.name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if data.startswith(b"MZ") or entry.name.endswith((".exe", ".dll", ".pyd")):
                pe.append({"path": entry.name, **actual[entry.name], **pe_metadata(data)})
    if actual != expected or set(metadata) != {".PKGINFO", ".BUILDINFO", ".MTREE"}:
        raise ContractError("Full package readback does not match the source stage")
    pkg, build = validate_metadata(metadata, name, actual, recipe_sha)
    validate_mtree(metadata[".MTREE"], actual, metadata, pkg["builddate"][0])
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest(path), "pkgname": pkg["pkgname"][0],
            "pkgver": pkg["pkgver"][0], "arch": pkg["arch"][0], "files": actual, "pe_images": pe,
            "depends": pkg.get("depend", []), "signed": False, "metadata": {
                key: hashlib.sha256(value).hexdigest() for key, value in metadata.items()},
            "validated_build_metadata": build,
            "archive_readback_complete": True, "provider_admitted": False}
