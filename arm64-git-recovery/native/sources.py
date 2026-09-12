"""Recover pinned upstream sources without executing package recipes."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import urllib.request
import zipfile


class ContractError(ValueError):
    pass


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ContractError(f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ContractError(f"Unsafe relative path: {value!r}")
    return path


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_lock(path):
    lock = json.loads(Path(path).read_text(encoding="utf-8"))
    if lock.get("schema") != 1 or not lock.get("sources"):
        raise ContractError("Expected nonempty schema-1 source lock")
    ids, names = set(), set()
    for item in lock["sources"]:
        if item["id"] in ids or item["file"].casefold() in names:
            raise ContractError("Duplicate source ID or download filename")
        ids.add(item["id"])
        names.add(item["file"].casefold())
        for field in ("id", "file", "prefix"):
            if len(relative_path(item[field]).parts) != 1:
                raise ContractError(f"{field} must be one path component")
        if not re.fullmatch("[0-9a-f]{64}", item["sha256"]):
            raise ContractError(f"Missing SHA-256 for {item['id']}")
        if not item["url"].startswith("https://") or not item["version"]:
            raise ContractError("Every source needs an HTTPS URL and version")
        if item.get("format", "tar") not in ("tar", "zip", "file"):
            raise ContractError("Unsupported pinned source format")
    return lock


def inventory(root):
    root = Path(root)
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ContractError(f"Not a source directory: {root}")
    files = {}
    folded = set()
    for entry in sorted(root.rglob("*")):
        rel = entry.relative_to(root).as_posix()
        relative_path(rel)
        if entry.is_junction():
            raise ContractError(f"Unsupported source junction: {rel}")
        if entry.is_symlink():
            target = os.readlink(entry)
            resolved = entry.resolve()
            if not resolved.is_relative_to(root.resolve()):
                raise ContractError(f"External symlink: {rel}")
            record = {"symlink": target}
        elif entry.is_file():
            record = {"sha256": digest(entry), "size": entry.stat().st_size}
        elif entry.is_dir():
            continue
        else:
            raise ContractError(f"Unsupported file: {rel}")
        if rel.casefold() in folded:
            raise ContractError(f"Case-insensitive file collision: {rel}")
        folded.add(rel.casefold())
        files[rel] = record
    if not files:
        raise ContractError(f"Empty source tree: {root}")
    return files


def verify_tree(root, manifest):
    expected = json.loads(Path(manifest).read_text(encoding="utf-8"))["files"]
    actual = inventory(root)
    if actual != expected:
        changed = sorted(p for p in actual.keys() | expected.keys()
                         if actual.get(p) != expected.get(p))
        raise ContractError(f"Source inventory differs: {changed[:20]}")
    return len(actual)


def extract_zip(archive, root, prefix):
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        seen = set()
        for member in members:
            name = member.filename.rstrip("/")
            parts = relative_path(name).parts
            if parts[0] != prefix or name.casefold() in seen:
                raise ContractError(f"Unexpected prefix or duplicate ZIP member: {name}")
            seen.add(name.casefold())
            mode = (member.external_attr >> 16) if member.create_system == 3 else 0
            kind = stat.S_IFMT(mode)
            if kind not in (0, stat.S_IFDIR if member.is_dir() else stat.S_IFREG):
                raise ContractError(f"Unsupported ZIP member type: {name}")
            if member.flag_bits & 1:
                raise ContractError("Encrypted source ZIP members are not supported")
        for member in members:
            destination = root / member.filename.rstrip("/")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as stream, destination.open("xb") as output:
                    shutil.copyfileobj(stream, output)
                mode = member.external_attr >> 16
                if member.create_system == 3 and stat.S_IMODE(mode):
                    destination.chmod(stat.S_IMODE(mode) & 0o777)


def recover(item, cache, output=None):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / item["file"]
    if archive.is_symlink():
        raise ContractError(f"Refusing symlink download: {archive}")
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix + ".partial")
        # Exclusive creation: do not overwrite another recovery's partial download.
        with partial.open("xb") as dest:
            with urllib.request.urlopen(item["url"], timeout=120) as response:
                if not response.url.startswith("https://"):
                    raise ContractError("Download redirected away from HTTPS")
                shutil.copyfileobj(response, dest)
        if digest(partial) != item["sha256"]:
            raise ContractError(f"Downloaded SHA-256 mismatch: {partial}")
        partial.rename(archive)
    if digest(archive) != item["sha256"]:
        raise ContractError(f"Cached SHA-256 mismatch: {archive}")
    if output is None:
        return {"id": item["id"], "archive_sha256": item["sha256"]}
    root = Path(output) / item["id"]
    manifest = Path(output) / f"{item['id']}.inventory.json"
    if root.exists():
        if not manifest.is_file():
            raise ContractError(f"Incomplete extraction; use a fresh output directory: {root}")
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if saved["source"] != item:
            raise ContractError(f"Source identity differs: {manifest}")
        return {"id": item["id"], "files": verify_tree(root, manifest)}
    if manifest.exists():
        raise ContractError(f"Inventory exists without its tree: {manifest}")
    root.mkdir(parents=True)
    archive_format = item.get("format", "tar")
    if archive_format == "file":
        shutil.copyfile(archive, root / item["file"])
    else:
        if archive_format == "zip":
            extract_zip(archive, root, item["prefix"])
        elif archive_format == "tar":
            with tarfile.open(archive, "r:*") as tar:
                members = tar.getmembers()
                seen = set()
                for member in members:
                    name = member.name.rstrip("/")
                    parts = relative_path(name).parts
                    if parts[0] != item["prefix"]:
                        raise ContractError(f"Unexpected archive prefix: {name}")
                    if name in seen:
                        raise ContractError(f"Duplicate archive member: {name}")
                    seen.add(name)
                    if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                        raise ContractError(f"Unsupported archive member: {name}")
                # Python's data filter also checks link destinations before writing.
                tar.extractall(root, filter="data")
        else:
            raise ContractError("Unsupported pinned source format")
        extracted = root / item["prefix"]
        for child in extracted.iterdir():
            child.rename(root / child.name)
        extracted.rmdir()
    files = inventory(root)
    with manifest.open("x", encoding="utf-8", newline="\n") as dest:
        json.dump({"source": item, "files": files}, dest, indent=2, sort_keys=True)
        dest.write("\n")
    return {"id": item["id"], "files": len(files), "archive_sha256": item["sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("sources.lock.json"))
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Extract into new per-source directories")
    parser.add_argument("--only", nargs="+", help="Source IDs; default: all")
    args = parser.parse_args()
    lock = load_lock(args.lock)
    selected = set(args.only or [s["id"] for s in lock["sources"]])
    unknown = selected - {s["id"] for s in lock["sources"]}
    if unknown:
        raise ContractError(f"Unknown sources: {sorted(unknown)}")
    for item in lock["sources"]:
        if item["id"] in selected:
            print(json.dumps(recover(item, args.cache, args.output)), flush=True)


if __name__ == "__main__":
    main()
