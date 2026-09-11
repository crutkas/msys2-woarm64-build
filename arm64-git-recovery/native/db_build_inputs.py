"""Adopt the pinned Berkeley DB recipe and a frozen private build driver."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from sources import ContractError, digest, inventory, load_lock, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json
from ssh_build_inputs import contract


BOOTSTRAP_SOURCE_SEAL = "347a9b744efc7918d1ec69855d62c597d5e7d89e9787302ecd04625b84a6372e"
CPP_FRONTEND_SEAL = "f003aec1b083e8d54ab93b6d1d0d901cd659708f5fc95279dad4f0f24feb3c6c"
MUTEX_PATCH_SEAL = "a18e63a6b0c02957da27eba8e8a84d3884ab43860e1e41fce641d2d8015c09a5"
LIBTOOL_PATH_PATCH_SEAL = "11d27eb1f6b9a8a5143bd59717ce99825ea6ee2e5434c22d5f7cc93afc8b24de"


def mutex_customization(source, record):
    patch = Path(__file__).parent / "patches/db-6.2.32-aarch64-mutex-detection.patch"
    if digest(patch) != MUTEX_PATCH_SEAL:
        raise ContractError("The reviewed ARM64 mutex detection patch changed")
    path_patch = patch.with_name("db-6.2.32-native-libtool-paths.patch")
    if digest(path_patch) != LIBTOOL_PATH_PATCH_SEAL:
        raise ContractError("The reviewed native GCC libtool search-path patch changed")
    changes = {}
    old = b"#if defined(__arm64__) && defined(__GNUC__)"
    new = b"#if (defined(__arm64__) || defined(__aarch64__)) && defined(__GNUC__)"
    for name in ("dist/aclocal/mutex.m4", "dist/configure", "dist/aclocal/libtool.m4"):
        data = (Path(source) / name).read_bytes()
        before = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        if before != record["files"][name]:
            raise ContractError("Unexpected DB detector source")
        if name != "dist/aclocal/libtool.m4":
            if data.count(old) != 1:
                raise ContractError("Unexpected DB mutex detector")
            data = data.replace(old, new)
        if name != "dist/aclocal/mutex.m4":
            chars = b"[[A-Za-z]]" if name.endswith(".m4") else b"[A-Za-z]"
            anchor = b"    *) lt_sed_strip_eq='s|=/|/|g' ;;"
            inserted = b"    cygwin*) lt_sed_strip_eq='s|=\\(" + chars + b":\\)|\\1|g;s|=/|/|g' ;;\n"
            search = b"    mingw* | windows* | cegcc*) lt_search_path_spec="
            if data.count(anchor) != 1 or data.count(search) != 1:
                raise ContractError("Unexpected libtool native search-path detector")
            data = data.replace(anchor, inserted + anchor).replace(
                search, b"    cygwin* | mingw* | windows* | cegcc*) lt_search_path_spec=")
        changes[name] = {"before": before, "after": {
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}}
    return {"patch": str(patch.resolve()), "patch_sha256": MUTEX_PATCH_SEAL, "files": changes,
            "libtool_path_patch": str(path_patch.resolve()), "libtool_path_patch_sha256": LIBTOOL_PATH_PATCH_SEAL,
            "scope": "Recognize canonical GCC __aarch64__ and preserve native Windows GCC library paths in libtool; no feature/flag changes or dependency-check bypass"}


def verify_db_working_source(source, record, customization):
    expected = {**record["files"], **{name: row["after"] for name, row in customization["files"].items()}}
    if inventory(source) != expected:
        raise ContractError("DB working source changed beyond the reviewed ARM64 detection patch")


def validate_db_preparation(record):
    rules = contract()
    profile = rules["transitive_recipe_requirements"]["db"]
    pins = {row["id"]: row for row in load_lock(Path(__file__).with_name("sources.lock.json"))["sources"]}
    recipes = rules["recipe_collection"]
    if (record.get("source") != pins["db"]
            or record.get("recipe_sha256") != profile["recipe_sha256"]
            or record.get("recipe_manifest_sha256") != recipes["prepared_inventory_sha256"]
            or any(pins[recipes["id"]][key] != recipes[key] for key in ("version", "sha256"))
            or record.get("dependency_abi") != "MSYS runtime; MinGW/UCRT libraries are not substitutes"
            or record.get("scope") != "prepared MSYS-target sources, not built"
            or record.get("dependencies") != ["gcc-libs", "sh"]):
        raise ContractError("DB preparation differs from its pinned archive, recipe or MSYS ABI")
    steps = record.get("steps", [])
    if (not steps or any(step.get("exit") != 0 for step in steps)
            or not any(step.get("command") == ["./s_config"] for step in steps)
            or "dist/configure" not in record.get("files", {})
            or not record.get("libtool_dependency", {}).get("manifest_sha256")):
        raise ContractError("DB preparation lacks its complete MSYS-aware generation")
    return profile


def require_db_cpp_receipt(record):
    delta = record.get("source_cpp_frontend_delta", {})
    qualification = delta.get("qualification", {})
    expected = "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1plus.exe"
    if (record.get("full_cpp_qualified") is not False
            or delta.get("changed_files") != [expected]
            or record.get("files", {}).get(expected, {}).get("sha256") != CPP_FRONTEND_SEAL
            or qualification.get("normal_guard_raw_exit") != 0
            or qualification.get("matrix_runs") != 7
            or qualification.get("real_canary_failure_raw_exits") != [1536, 1536]):
        raise ContractError("DB requires the exact named protected C++ frontend qualification, not whole-SDK admission")


def copy_sealed_tree(source, manifest, destination):
    source, manifest, destination = map(Path, (source, manifest, destination))
    if destination.exists() or destination.is_symlink():
        raise ContractError("A fresh owned copy root is required")
    if source.resolve().is_relative_to(destination.resolve()) or destination.resolve().is_relative_to(source.resolve()):
        raise ContractError("Copy source and destination must be disjoint")
    if any(p.is_symlink() or p.is_junction() for p in destination.parents):
        raise ContractError("Copy output may not traverse links")
    seal = digest(manifest)
    record = json.loads(manifest.read_text())
    verify_tree(source, manifest)
    before = inventory(source)
    if any("symlink" in row for row in before.values()):
        raise ContractError("Only regular-file frozen inputs may be adopted")
    directories = directory_names(source)
    memory = [require_memory()]
    destination.mkdir(parents=True)
    for name in directories:
        (destination / name).mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(before):
        shutil.copy2(source / name, destination / name)
        if index % 256 == 0:
            memory.append(require_memory())
    copied = inventory(destination)
    after = inventory(source)
    if (before != copied or before != after or digest(manifest) != seal
            or directory_names(source) != directories or directory_names(destination) != directories):
        raise ContractError("Complete before/copy/after file and directory inventories differ")
    receipt = {**record, "source_prefix": str(source), "prefix": str(destination.resolve()),
               "source_receipt_sha256": seal, "files": copied, "directories": directories,
               "source_unchanged": True, "complete_inventory_equality": True,
               "minimum_observed_free_gib": min(memory), "copy_pid": os.getpid()}
    write_json(destination.with_name(destination.name + ".copy.json"), receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("old-git-root", "bootstrap", "bootstrap-receipt", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = args.old_git_root
    manifest = root / "prepared/db-native-01.prepare.json"
    record = json.loads(manifest.read_text())
    profile = validate_db_preparation(record)
    original = root / "sources/db.inventory.json"
    recipes = root / "sources/msys-upstream-recipes.inventory.json"
    recipe = root / "sources/msys-upstream-recipes/db/PKGBUILD"
    archive = root / "cache/db-6.2.32.tar.gz"
    identities = {str(path): digest(path) for path in (manifest, original, recipes, recipe, archive)}
    if (identities[str(original)] != record["original_manifest_sha256"]
            or identities[str(recipes)] != record["recipe_manifest_sha256"]
            or identities[str(recipe)] != profile["recipe_sha256"]
            or identities[str(archive)] != record["source"]["sha256"]
            or json.loads(original.read_text())["source"] != record["source"]):
        raise ContractError("Original pinned DB archive/recipe provenance differs")
    if digest(args.bootstrap_receipt) != BOOTSTRAP_SOURCE_SEAL:
        raise ContractError("Unapproved frozen private bootstrap receipt")
    bootstrap = json.loads(args.bootstrap_receipt.read_text())
    if (Path(bootstrap["prefix"]).resolve() != args.bootstrap.resolve()
            or bootstrap["status"] != "private-ssh-bootstrap-byte-identical-not-executed"
            or bootstrap["source_unchanged"] is not True
            or bootstrap["complete_inventory_equality"] is not True):
        raise ContractError("Bootstrap is not an approved quiescent private input")
    args.output.mkdir(parents=True, exist_ok=False)
    print(json.dumps({"pid": os.getpid(), "command": [sys.executable, *sys.argv],
                      "phase": "source-and-bootstrap-adoption"}), flush=True)
    source = args.output / "source"
    copied = copy_sealed_tree(root / "prepared/db-native-01", manifest, source)
    shutil.copyfile(manifest, args.output / "source.prepare.json")
    verify_tree(source, args.output / "source.prepare.json")
    for path in (original, recipes, recipe, archive):
        shutil.copyfile(path, args.output / path.name)
    boot = copy_sealed_tree(args.bootstrap, args.bootstrap_receipt, args.output / "msys64")
    if any(digest(path) != seal for path, seal in identities.items()):
        raise ContractError("Frozen source identity changed during adoption")
    report = {"status": "verified-private-db-inputs", "input_identities": identities,
              "source_files": len(copied["files"]), "bootstrap_files": len(boot["files"]),
              "source_copy": str(source.with_name("source.copy.json")),
              "bootstrap_copy": str(args.output / "msys64.copy.json"),
              "pid": os.getpid(), "target_or_bootstrap_processes_launched": 0}
    write_json(args.output / "adoption.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
