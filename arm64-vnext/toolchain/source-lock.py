#!/usr/bin/env python3
"""Validate and query the portable, ordered bootstrap source lock."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def checked_hash(value, digits):
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{digits}}}", value):
        raise ValueError(f"Invalid {digits}-digit identity: {value!r}")


def load_lock(directory):
    lock = json.loads((directory / "source-lock.json").read_text(encoding="utf-8"))
    if lock["schema"] != 1:
        raise ValueError("Unsupported source lock schema")
    if set(lock["sources"]) != {"gcc", "binutils", "mingw-w64", "mingw-woarm64"}:
        raise ValueError("Unexpected bootstrap source set")
    patch_files = set()
    for name, source in lock["sources"].items():
        checked_hash(source["revision"], 40)
        if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+\.git", source["repository"]):
            raise ValueError(f"Nonportable repository URL: {name}")
        blob = PurePosixPath(source["blob"])
        if blob.is_absolute() or ".." in blob.parts or str(blob) == ".":
            raise ValueError(f"Invalid source blob path: {name}")
        for patch in source["patches"] + source.get("overlay_patches", []):
            file = patch["file"]
            if not re.fullmatch(r"[\w-]+\.patch", file) or file in patch_files:
                raise ValueError(f"Invalid or duplicate patch: {file}")
            patch_files.add(file)
            checked_hash(patch["sha256"], 64)
            if hashlib.sha256((directory / file).read_bytes()).hexdigest() != patch["sha256"]:
                raise ValueError(f"Patch identity differs from source lock: {file}")
    if not lock["sources"]["gcc"]["patches"] or not lock["sources"]["binutils"]["patches"]:
        raise ValueError("Compiler and binutils patch series must not be empty")
    archive_files = set()
    for archive in lock["archives"]:
        file = archive["file"]
        if not re.fullmatch(r"[\w.-]+\.tar\.(bz2|gz)", file) or file in archive_files:
            raise ValueError(f"Invalid or duplicate archive: {file}")
        archive_files.add(file)
        checked_hash(archive["sha512"], 128)
        if archive["url"] != f"https://gcc.gnu.org/pub/gcc/infrastructure/{file}":
            raise ValueError(f"Unexpected native prerequisite URL: {file}")
    if archive_files != {"gmp-6.2.1.tar.bz2", "mpfr-4.1.0.tar.bz2", "mpc-1.2.1.tar.gz"}:
        raise ValueError("Unexpected native prerequisite archive set")
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--gcc-source", type=Path)
    source = commands.add_parser("source")
    source.add_argument("name")
    source.add_argument("field", choices=("repository", "revision", "blob"))
    patches = commands.add_parser("patches")
    patches.add_argument("name", choices=("gcc", "binutils"))
    args = parser.parse_args()
    try:
        lock = load_lock(args.directory)
        if args.command == "source":
            print(lock["sources"][args.name][args.field])
        elif args.command == "patches":
            for patch in lock["sources"][args.name]["patches"]:
                print(args.directory / patch["file"])
        else:
            if args.gcc_source:
                records = (args.gcc_source / "contrib" / "prerequisites.sha512").read_text().splitlines()
                upstream = {fields[1]: fields[0] for line in records if (fields := line.split())}
                for archive in lock["archives"]:
                    if upstream.get(archive["file"]) != archive["sha512"]:
                        raise ValueError(f"GCC prerequisite identity differs: {archive['file']}")
            canonical = json.dumps(lock, sort_keys=True, separators=(",", ":")).encode("utf-8")
            print(json.dumps({
                "schema": 1,
                "source_lock_sha256": hashlib.sha256(canonical).hexdigest(),
                "source_count": len(lock["sources"]),
                "patch_count": sum(len(source["patches"]) + len(source.get("overlay_patches", []))
                                   for source in lock["sources"].values()),
            }, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
