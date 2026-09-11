#!/usr/bin/env python3
"""Shared identity and inventory checks for the pinned Cygwin w32api cohort."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re

RECIPE = Path(__file__).resolve().parent
LOCK_NAME = "cygwin-w32api-source-lock.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_patch_sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def ref(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}


def inventory(root):
    root = Path(root).resolve(strict=True)
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"Regular files are required, not links: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {
                "sha256": sha(path),
                "bytes": path.stat().st_size,
            }
    if not files:
        raise ValueError(f"Empty inventory: {root}")
    return files


def load_lock(directory=RECIPE):
    directory = Path(directory)
    lock = json.loads((directory / LOCK_NAME).read_text(encoding="utf-8"))
    if lock.get("schema") != 1:
        raise ValueError("Unsupported Cygwin w32api source-lock schema")
    if lock.get("repository") != "https://github.com/mingw-w64/mingw-w64.git":
        raise ValueError("Unexpected Cygwin w32api repository")
    if not re.fullmatch(r"[0-9a-f]{40}", lock.get("revision", "")):
        raise ValueError("Invalid pinned Cygwin w32api revision")
    public_probe = lock.get("public_probe", {})
    if (
        public_probe.get("file") != "cygwin-public-interlocked-codegen.c"
        or not re.fullmatch(r"[0-9a-f]{64}", public_probe.get("sha256", ""))
        or sha(directory / public_probe["file"]) != public_probe["sha256"]
        or public_probe.get("provenance", {}).get("normalization") != "CRLF-to-LF only"
        or not re.fullmatch(
            r"[0-9a-f]{64}",
            public_probe.get("provenance", {}).get("source_sha256", ""),
        )
    ):
        raise ValueError("Public codegen probe identity differs")
    sdk = lock.get("sdk_contract", {})
    for field in (
        "provenance_sha256",
        "inventory_sha256",
        "tool_receipt_sha256",
        "runtime_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", sdk.get(field, "")):
            raise ValueError(f"Invalid pinned SDK identity: {field}")
    if sdk.get("file_count") != 3043:
        raise ValueError("Unexpected pinned SDK file count")
    required_files = sdk.get("required_files", {})
    if len(required_files) != 8:
        raise ValueError("Unexpected pinned SDK tool set")
    for name, digest in required_files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid pinned SDK file: {name}")
    names = []
    for patch in lock.get("patches", []):
        name = patch.get("file", "")
        if not re.fullmatch(r"cygwin-w32api-[\w-]+\.patch", name) or name in names:
            raise ValueError(f"Invalid or duplicate patch: {name}")
        names.append(name)
        if not re.fullmatch(r"[0-9a-f]{64}", patch.get("sha256", "")):
            raise ValueError(f"Invalid patch identity: {name}")
        if canonical_patch_sha(directory / name) != patch["sha256"]:
            raise ValueError(f"Patch identity differs: {name}")
        identity = patch.get("source_identity")
        if identity:
            source_path = PurePosixPath(identity["file"])
            if source_path.is_absolute() or ".." in source_path.parts:
                raise ValueError("Invalid source identity path")
            for field in ("before_sha256", "after_sha256"):
                if not re.fullmatch(r"[0-9a-f]{64}", identity.get(field, "")):
                    raise ValueError(f"Invalid source identity {field}")
    if names != [
        "cygwin-w32api-arm64-abi.patch",
        "cygwin-w32api-arm64-interlocked-exchange-ordering.patch",
    ]:
        raise ValueError("Unexpected Cygwin w32api patch series")
    return lock


def source_identity(lock):
    return lock["patches"][-1]["source_identity"]


def verify_patched_source(lock, root):
    identity = source_identity(lock)
    path = Path(root) / identity["file"]
    if sha(path) != identity["after_sha256"]:
        raise ValueError("Patched intrinsic source identity differs")


def verify_sdk_inventory(lock, sdk, provenance_path):
    sdk = Path(sdk).resolve(strict=True)
    provenance_path = Path(provenance_path).resolve(strict=True)
    contract = lock["sdk_contract"]
    if sha(provenance_path) != contract["provenance_sha256"]:
        raise ValueError("Selected SDK provenance receipt differs")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8-sig"))
    if Path(provenance["root06Toolchain"]).resolve() != sdk:
        raise ValueError("SDK provenance binds another root")
    manifest = Path(provenance["fullInventory"]["path"]).resolve(strict=True)
    if (
        provenance["fullInventory"]["sha256"] != contract["inventory_sha256"]
        or provenance["fullInventory"]["fileCount"] != contract["file_count"]
        or sha(manifest) != contract["inventory_sha256"]
    ):
        raise ValueError("SDK full-inventory receipt differs")
    entries = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if len(entries) != contract["file_count"]:
        raise ValueError("SDK full-inventory count differs")
    expected = {}
    for entry in entries:
        relative = Path(entry["rel"])
        name = relative.as_posix()
        if relative.is_absolute() or ".." in relative.parts or name in expected:
            raise ValueError(f"Invalid SDK inventory path: {entry['rel']}")
        path = sdk / relative
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise ValueError(f"SDK inventory path is not a regular file: {entry['rel']}")
        if sha(path) != entry["sha256"]:
            raise ValueError(f"SDK inventory file changed: {entry['rel']}")
        expected[name] = entry["sha256"]
    actual = {}
    for path in sdk.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"SDK contains an uninventoried link: {path}")
        if path.is_file():
            actual[path.relative_to(sdk).as_posix()] = sha(path)
    if actual != expected:
        raise ValueError("SDK has missing or uninventoried files")
    for name, digest in contract["required_files"].items():
        if sha(sdk / Path(name)) != digest:
            raise ValueError(f"Pinned SDK file changed: {name}")
    if sha(sdk / "bin/msys-2.0.dll") != contract["runtime_sha256"]:
        raise ValueError("Pinned runtime907 changed")
    return provenance
