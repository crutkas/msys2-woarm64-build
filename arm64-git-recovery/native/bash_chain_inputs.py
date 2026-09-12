"""Adopt only the pinned full Bash and MSYS NLS closure into a new private root."""

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlparse

from readline_chain_inputs import GIT, HERE, ROOT as TERMINAL_ROOT, WSL, sealed
from sources import ContractError, digest, inventory, load_lock, recover, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json

build = importlib.import_module("build-readline-chain")
ROOT = Path(r"C:\ag-bash-e138-01")
PREPARED = {
    "libiconv": ("libiconv-msys-03", "ea7fe95778e8cbedab64c082f07e99ed0c82678503e903fac3fb4cc7fbdd3ef4"),
    "gettext-msys": ("gettext-msys-05", "a62b5565f39f4ec9f6fc8ac84e69cc57829cee979f897e34d7e8b33af2194c80"),
    "bash": ("bash-06", "787e999c08fc28db3c00cd38e34bde9210883039cec18719364b9670d2242946"),
}
BOOTSTRAP_SHA = "fef4e2390fcc37334e07dc693f24639a87f64531a11139f5b176f10567ec91b3"
OLD_HELPERS = Path(r"C:\Users\crutkasLocal\.copilot\repos\copilot-worktrees\msys2-woarm64-build\crutkas-shiny-meme\arm64-git-recovery\native")


def initialize():
    if ROOT.exists():
        receipt = ROOT / "ownership.json"
        if not receipt.is_file() or json.loads(receipt.read_text()).get("unit") != "full-bash-e138-01":
            raise ContractError("Bash root already exists without this unit's ownership receipt")
    else:
        ROOT.mkdir()
        write_json(ROOT / "ownership.json", {"unit": "full-bash-e138-01", "worktree": str(HERE),
                                             "grant": 2, "scope": "Inside Git6, no additional global quota"})


def fresh(path):
    if path.exists() or path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ContractError(f"Fresh Bash-owned output required: {path}")
    if any(p.is_junction() or p.is_symlink() for p in path.parents):
        raise ContractError("Bash output traverses a link")


def foreign_path(path):
    if path.startswith("/mnt/c/"):
        return Path("C:\\") / path[len("/mnt/c/"):]
    if path.startswith("/root/"):
        return WSL / path.lstrip("/")
    return Path(path)


def copy_pinned(source, target, expected):
    sealed(source, expected)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        sealed(target, expected)
    else:
        shutil.copyfile(source, target)
    sealed(target, expected)
    sealed(source, expected)
    return {"source": str(source), "copy": str(target), "sha256": expected}


def sources():
    pins = {row["id"]: row for row in load_lock(HERE / "sources.lock.json")["sources"]}
    for package, (name, expected_sha) in PREPARED.items():
        source = GIT / "prepared" / name
        manifest = source.with_name(name + ".prepare.json")
        sealed(manifest, expected_sha)
        record = json.loads(manifest.read_text())
        recipe_id = "msys-recipes" if package == "bash" else "msys-upstream-recipes"
        recipe_dir = "gettext" if package == "gettext-msys" else package
        origin_manifest = GIT / "sources" / (package + ".inventory.json")
        origin_sha = record["source_manifest_sha256" if package == "bash" else "original_manifest_sha256"]
        sealed(origin_manifest, origin_sha)
        if json.loads(origin_manifest.read_text())["source"] != pins[package]:
            raise ContractError("Original Bash/NLS source pin differs")
        recipe_manifest = GIT / "sources" / (recipe_id + ".inventory.json")
        sealed(recipe_manifest, record["recipe_manifest_sha256"])
        recipe_inventory = json.loads(recipe_manifest.read_text())
        if recipe_inventory["source"] != pins[recipe_id]:
            raise ContractError("Recipe collection pin differs")
        recipe = GIT / "sources" / recipe_id / recipe_dir / "PKGBUILD"
        recipe_sha = recipe_inventory["files"][recipe_dir + "/PKGBUILD"]["sha256"]
        sealed(recipe, recipe_sha)
        if package != "bash" and (record["source"] != pins[package] or record["recipe_sha256"] != recipe_sha
                or record["dependency_abi"] != "MSYS runtime; MinGW/UCRT libraries are not substitutes"):
            raise ContractError("Prepared native NLS recipe/ABI differs")
        if package == "bash" and (record["status"] != "source-prepared-not-built"
                or record["source_id"] != "bash" or record["recipe_id"] != recipe_id
                or len(record["patches"]) != 22):
            raise ContractError("Expected full Bash5.3+015/GFW22-patch preparation")
        output = ROOT / "sources" / package
        fresh(output)
        output.mkdir(parents=True)
        evidence = []
        for identity in (package, recipe_id):
            archive = GIT / "cache" / pins[identity]["file"]
            if not archive.is_file():
                archive = GIT / "downloads" / pins[identity]["file"]
            evidence.append(copy_pinned(archive, ROOT / "cache" / pins[identity]["file"], pins[identity]["sha256"]))
        evidence.append(copy_pinned(recipe, output / "PKGBUILD", recipe_sha))
        if package == "bash":
            checksums = re.findall(r"'([0-9a-f]{64}|SKIP)'",
                                   re.search(r"(?ms)^sha256sums=\((.*?)\)", recipe.read_text())[1])
            if "_patchlevel=015" not in recipe.read_text() or len(checksums) != 37:
                raise ContractError("Bash release patch checksum layout differs")
            for index, row in enumerate(record["patches"]):
                if index < 15:
                    filename = Path(urlparse(row["url"]).path).name
                    if filename != f"bash53-{index + 1:03d}" or row["sha256"] != checksums[7 + index * 2]:
                        raise ContractError("GNU Bash patch order/pin differs")
                    path = GIT / "cache" / filename
                    if not path.is_file():
                        pin = {"id": filename, "file": filename, "prefix": filename,
                               "version": f"5.3.{index + 1:03d}", "sha256": row["sha256"],
                               "url": row["url"], "format": "file"}
                        recover(pin, ROOT / "cache")
                        path = ROOT / "cache" / filename
                elif row["recipe"] == recipe_id:
                    path = GIT / "sources" / recipe_id / row["path"]
                else:
                    path = OLD_HELPERS / "patches" / row["path"]
                evidence.append(copy_pinned(path, output / "patches" / path.name, row["sha256"]))
        else:
            if not record.get("libtool_dependency", {}).get("manifest_sha256"):
                raise ContractError("NLS preparation lacks its MSYS-aware libtool generator seal")
            for row in record["steps"]:
                if "exit" in row and row["exit"] != 0:
                    raise ContractError("Failed prepared NLS generation")
                if row.get("patch_sha256"):
                    path = foreign_path(row["command"][-1])
                    expected = row.get("adapted_patch_sha256", row["patch_sha256"])
                    evidence.append(copy_pinned(path, output / "patches" / path.name, expected))
        count = verify_tree(source, manifest)
        if any("symlink" in row for row in record["files"].values()):
            raise ContractError("Bash source adoption does not silently materialize symbolic links")
        require_memory()
        shutil.copytree(source, output / "source", symlinks=True)
        shutil.copyfile(manifest, output / "source.prepare.json")
        verify_tree(output / "source", output / "source.prepare.json")
        verify_tree(source, manifest)
        sealed(manifest, expected_sha)
        receipt = {"schema": 1, "package": package, "source": str(source),
                   "source_manifest_sha256": expected_sha, "source_unchanged": True,
                   "files": count, "recipe_sha256": recipe_sha, "evidence": evidence,
                   "status": "sealed-Bash-NLS-source-copy-not-built"}
        write_json(output / "adoption.json", receipt)
        print(json.dumps({key: receipt[key] for key in ("package", "files", "status", "source_manifest_sha256")}), flush=True)


def bootstrap():
    source = TERMINAL_ROOT / "bootstrap/msys64"
    manifest = TERMINAL_ROOT / "bootstrap/msys64.copy.json"
    sealed(manifest, BOOTSTRAP_SHA)
    record = json.loads(manifest.read_text())
    if len(record["files"]) != 19265 or not record["complete_inventory_equality"]:
        raise ContractError("Wrong previously quiescent approved bootstrap copy")
    verify_tree(source, manifest)
    before, directories = inventory(source), directory_names(source)
    if directories != record["directories"]:
        raise ContractError("Source bootstrap directories changed")
    output = ROOT / "bootstrap"
    fresh(output)
    output.mkdir()
    write_json(output / "before.json", {"files": before, "directories": directories})
    target = output / "msys64"
    memory = [require_memory()]
    target.mkdir()
    for directory in directories:
        (target / directory).mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(before):
        shutil.copy2(source / name, target / name)
        if index % 256 == 0:
            memory.append(require_memory())
    copied, after = inventory(target), inventory(source)
    write_json(output / "copied.json", {"files": copied, "directories": directory_names(target)})
    write_json(output / "source-after.json", {"files": after, "directories": directory_names(source)})
    if copied != before or after != before or directory_names(target) != directories or directory_names(source) != directories:
        raise ContractError("Bash bootstrap before/copy/after equality failed")
    sealed(manifest, BOOTSTRAP_SHA)
    receipt = {"schema": 1, "prefix": str(target), "source": str(source), "source_receipt_sha256": BOOTSTRAP_SHA,
               "files": copied, "directories": directories, "complete_inventory_equality": True,
               "source_unchanged": True, "minimum_free_gib": min(memory),
               "status": "private-byte-identical-Bash-bootstrap-not-executed",
               "scope": "Explicit x64/emulated BUILD/TEST driver only, never native target payload"}
    write_json(output / "msys64.copy.json", receipt)
    print(json.dumps({"phase": "bootstrap-closed", "files": len(copied),
                      "sha256": digest(output / "msys64.copy.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("sources", "bootstrap"))
    args = parser.parse_args()
    initialize()
    print(json.dumps({"pid": os.getpid(), "creation_filetime": build.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    {"sources": sources, "bootstrap": bootstrap}[args.operation]()
