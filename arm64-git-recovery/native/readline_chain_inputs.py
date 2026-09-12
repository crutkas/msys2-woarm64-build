"""Adopt the sealed native terminal-library chain into one private root."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

from sources import ContractError, digest, inventory, load_lock, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json
from ssh_build_inputs import validate_preparation

ROOT = Path(r"C:\ag-readline-e138-01")
PARENT = Path(r"C:\ag-e138920f")
WSL = Path(r"\\wsl.localhost\Ubuntu")
GIT = WSL / "root/arm64-vnext-20260905/git"
HERE = Path(__file__).resolve().parent
SEALS = {
    "ncurses": "7f403dd11bc8a9e8c5bf54eb13c2373dfc6171cd063087f78ab19e11c261a7cc",
    "readline": "a590449d26a2ba1fbcd50221bd36a5517a7ab1ad45e93a74d8d006a9ebe11ba6",
    "libedit": "fe6508b5bcedbbe3212d34beea59869e6cba14779f9eef64a6917eefd15b2bcd",
    "bootstrap": "347a9b744efc7918d1ec69855d62c597d5e7d89e9787302ecd04625b84a6372e",
    "compiler": "ed4fa0a4844ee05deca009dc9346320d701ae93cd9f299dc0185a5358001d41c",
    "observer": "1f5384459cc239e0b373b05f42e60ef06ec580d45046e1484a4ba4d46de5b3fa",
}


def sealed(path, expected):
    if digest(path) != expected:
        raise ContractError(f"Input seal differs: {path}")


def emit(value):
    print(json.dumps(value), flush=True)


def fresh(path):
    if path.exists() or path.is_symlink():
        raise ContractError(f"Fresh owned output required: {path}")
    if not path.resolve().is_relative_to(ROOT):
        raise ContractError("Output outside the assigned root")
    if any(p.is_symlink() or p.is_junction() for p in path.parents):
        raise ContractError("Linked output parent")


def copy_bootstrap():
    source = PARENT / "ssh-bootstrap-01/msys64"
    manifest = PARENT / "ssh-bootstrap-01/msys64.copy.json"
    sealed(manifest, SEALS["bootstrap"])
    record = json.loads(manifest.read_text())
    if (record["status"] != "private-ssh-bootstrap-byte-identical-not-executed"
            or record["complete_inventory_equality"] is not True
            or record["source_unchanged"] is not True
            or len(record["files"]) != 19265):
        raise ContractError("Wrong authorized quiescent bootstrap")
    output = ROOT / "bootstrap"
    fresh(output)
    memory = [require_memory()]
    verify_tree(source, manifest)
    before = inventory(source)
    directories = directory_names(source)
    if directories != record["directories"]:
        raise ContractError("Bootstrap directory drift")
    output.mkdir()
    write_json(output / "before.json", {"files": before, "directories": directories})
    shutil.copyfile(manifest, output / "source.copy.json")
    payload = output / "msys64"
    payload.mkdir()
    emit({"phase": "bootstrap-copy", "pid": os.getpid(), "files": len(before)})
    for name in directories:
        (payload / name).mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(before):
        if "symlink" in before[name]:
            raise ContractError("Bootstrap links not authorized")
        shutil.copy2(source / name, payload / name)
        if index % 256 == 0:
            memory.append(require_memory())
    copied = inventory(payload)
    after = inventory(source)
    write_json(output / "copied-inventory.json", {"files": copied, "directories": directory_names(payload)})
    write_json(output / "source-after.json", {"files": after, "directories": directory_names(source)})
    if (copied != before or after != before or directory_names(payload) != directories
            or directory_names(source) != directories):
        raise ContractError("Bootstrap complete before/copy/after equality failed")
    sealed(manifest, SEALS["bootstrap"])
    receipt = {
        "schema": 1, "status": "private-ssh-bootstrap-byte-identical-not-executed",
        "prefix": str(payload), "source": str(source),
        "source_manifest_sha256": SEALS["bootstrap"], "source_unchanged": True,
        "complete_inventory_equality": True, "target_or_bootstrap_processes_launched": 0,
        "minimum_free_gib": min(memory), "files": copied, "directories": directories,
        "scope": "Private x64/emulated build and test driver only; never target payload",
    }
    write_json(output / "msys64.copy.json", receipt)
    emit({"phase": "bootstrap-closed", "files": len(copied), "sha256": digest(output / "msys64.copy.json")})


def adopt_sources():
    pins = {r["id"]: r for r in load_lock(HERE / "sources.lock.json")["sources"]}
    rules = json.loads((HERE / "ssh-recipes.json").read_text())
    inputs = {
        "ncurses": (GIT / "prepared/ncurses-native-01", GIT / "prepared/ncurses-native-01.prepare.json"),
        "readline": (GIT / "prepared/readline-native-06", GIT / "prepared/readline-native-06.prepare.json"),
        "libedit": (PARENT / "ssh-source-adoption-01/libedit/source",
                    PARENT / "ssh-source-adoption-01/libedit/source.prepare.json"),
    }
    for package, (source, manifest) in inputs.items():
        sealed(manifest, SEALS[package])
        record = json.loads(manifest.read_text())
        profile = rules["profiles"].get(package, rules["transitive_recipe_requirements"].get(package))
        if (record["source"] != pins[package] or record["recipe_sha256"] != profile["recipe_sha256"]
                or record["recipe_manifest_sha256"] != rules["recipe_collection"]["prepared_inventory_sha256"]):
            raise ContractError(f"Source/recipe pin mismatch: {package}")
        if package == "libedit":
            validate_preparation(package, record, load_lock(HERE / "sources.lock.json"))
        if package == "readline" and record.get("package_version") != "8.3.003":
            raise ContractError("Readline must include all three GNU patchlevels")
        origins = {}
        for identity, expected in ((package, record["original_manifest_sha256"]),
                                   ("msys-upstream-recipes", record["recipe_manifest_sha256"])):
            original = GIT / "sources" / (identity + ".inventory.json")
            sealed(original, expected)
            original_record = json.loads(original.read_text())
            if original_record["source"] != pins[identity]:
                raise ContractError(f"Original source pin mismatch: {identity}")
            origins[str(original)] = expected
        archive = GIT / "cache" / pins[package]["file"]
        if not archive.is_file():
            archive = GIT / "downloads" / pins[package]["file"]
        sealed(archive, pins[package]["sha256"])
        for step in record["steps"]:
            if step.get("exit", 0) != 0:
                raise ContractError("Failed prepared source step")
            if "patch_sha256" in step:
                patch = WSL / step["command"][-1].lstrip("/")
                sealed(patch, step["patch_sha256"])
                origins[str(patch)] = step["patch_sha256"]
        verify_tree(source, manifest)
        output = ROOT / "sources" / package
        fresh(output)
        output.mkdir(parents=True)
        shutil.copytree(source, output / "source", symlinks=True)
        shutil.copyfile(manifest, output / "source.prepare.json")
        verify_tree(output / "source", output / "source.prepare.json")
        verify_tree(source, manifest)
        sealed(manifest, SEALS[package])
        receipt = {
            "schema": 1, "package": package, "status": "sealed-source-private-copy",
            "source": str(source), "source_manifest_sha256": SEALS[package],
            "source_unchanged": True, "files": len(record["files"]),
            "verified_origins": origins, "archive": str(archive),
            "archive_sha256": pins[package]["sha256"],
            "target_processes_launched": 0,
        }
        write_json(output / "adoption.json", receipt)
        emit(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("bootstrap", "sources"))
    args = parser.parse_args()
    emit({"pid": os.getpid(), "utc": datetime.now(timezone.utc).isoformat(),
          "command": [sys.executable, *sys.argv], "operation": args.operation})
    {"bootstrap": copy_bootstrap, "sources": adopt_sources}[args.operation]()


if __name__ == "__main__":
    main()
