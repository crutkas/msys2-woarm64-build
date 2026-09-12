"""Snapshot, verify and assemble packages; never infer execution proof from files."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from sources import ContractError, digest, inventory, load_lock, relative_path


HOSTS = {"linux-aarch64-cross", "windows-arm64-native",
         "windows-x64-emulated-driver", "official-arm64-prebuilt", "data"}
TARGETS = {"aarch64-pc-cygwin", "aarch64-w64-mingw32", "data"}
PE_SUFFIXES = {".exe", ".dll", ".pyd", ".ocx", ".cpl", ".scr"}
STUB_MARKERS = (b"NON-FUNCTIONAL STUB", b"This build manages no credentials.",
                b"Placeholder license for", b"toolchain-proof PLACEHOLDER")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def payload_inventory(root, additional_pe_files=()):
    files = inventory(root)
    declared_pe = set(additional_pe_files)
    if declared_pe - files.keys():
        raise ContractError("Declared PE payload is missing")
    for rel, record in files.items():
        if "symlink" in record:
            raise ContractError(f"Resolve package links to files before snapshotting: {rel}")
        name = rel.casefold()
        if ("pipeline-stubs" in name.split("/") or name.endswith(".stub")
                or name.endswith("/stub-placeholder.txt")):
            raise ContractError(f"Non-deliverable package marker: {rel}")
        # Only inspect payload, never recovery notes describing old failures.
        data = (Path(root) / rel).read_bytes()
        if rel in declared_pe and not data.startswith(b"MZ"):
            raise ContractError(f"Declared PE payload does not have an MZ header: {rel}")
        if any(marker in data for marker in STUB_MARKERS):
            raise ContractError(f"Known placeholder payload: {rel}")
        if data.startswith(b"MZ") and Path(rel).suffix.lower() not in PE_SUFFIXES and rel not in declared_pe:
            raise ContractError(f"PE payload has an unrecognized extension: {rel}")
        record["pe_candidate"] = (Path(rel).suffix.lower() in PE_SUFFIXES
                                  or data.startswith(b"MZ"))
    return files


def validate_metadata(meta, lock_path):
    lock = load_lock(lock_path)
    if meta.get("schema") != 1:
        raise ContractError("Package metadata must use schema 1")
    if not re.fullmatch(r"[a-z0-9][a-z0-9+._-]*", meta.get("id", "")):
        raise ContractError("Invalid package ID")
    if not isinstance(meta.get("version"), str) or not meta["version"]:
        raise ContractError("Package version is required")
    if meta.get("target") not in TARGETS or meta.get("build_host") not in HOSTS:
        raise ContractError("Explicit supported target and build_host are required")
    if meta.get("classification") != "functional":
        raise ContractError("Bootstrap, stub and diagnostic packages cannot enter the distribution")
    ids = set(meta.get("source_ids", []))
    if not ids or ids - {s["id"] for s in lock["sources"]}:
        raise ContractError("Package source_ids must resolve in the source lock")
    if meta.get("source_lock_sha256") != digest(lock_path):
        raise ContractError("Package source lock identity differs")
    dependencies = meta.get("depends")
    if not isinstance(dependencies, dict):
        raise ContractError("depends must map exact package IDs to exact versions")
    if any(not isinstance(v, str) or not v for v in dependencies.values()):
        raise ContractError("Empty dependency version")
    if meta["id"] in dependencies:
        raise ContractError("Package depends on itself")
    if not meta.get("required_files") or not meta.get("license_files"):
        raise ContractError("Explicit required_files and actual license_files are required")
    for rel in meta["required_files"] + meta["license_files"]:
        relative_path(rel)
    additional_pe = meta.get("additional_pe_files", [])
    if not isinstance(additional_pe, list):
        raise ContractError("additional_pe_files must be an explicit path list")
    seen_pe = set()
    for rel in additional_pe:
        relative_path(rel)
        if rel.casefold() in seen_pe:
            raise ContractError("Duplicate declared PE path")
        seen_pe.add(rel.casefold())
    if meta["target"] != "data":
        if not re.fullmatch("[0-9a-f]{64}", meta.get("build_evidence_sha256", "")):
            raise ContractError("Non-data package requires the SHA-256 of its build evidence")
        evidence = Path(meta.get("build_evidence_path", ""))
        if not evidence.is_file() or digest(evidence) != meta["build_evidence_sha256"]:
            raise ContractError("Build evidence is missing or changed")
    return meta


def validate_payload(meta, files):
    missing = set(meta["required_files"] + meta["license_files"]) - files.keys()
    empty = [p for p in meta["required_files"] + meta["license_files"]
             if p in files and files[p]["size"] == 0]
    if missing or empty:
        raise ContractError(f"Missing/empty package requirements: {sorted(missing)} {empty}")
    pe_count = sum(f["pe_candidate"] for f in files.values())
    if meta["target"] == "data" and pe_count:
        raise ContractError("PE payload mislabeled as data")
    if meta["target"] != "data" and not pe_count:
        raise ContractError("Native package has no PE payload; classify script-only packages as data")


def snapshot(root, metadata_path, manifest_path, lock_path):
    meta = validate_metadata(read_json(metadata_path), lock_path)
    if Path(manifest_path).resolve().is_relative_to(Path(root).resolve()):
        raise ContractError("Manifest must be outside its payload")
    files = payload_inventory(root, meta.get("additional_pe_files", []))
    validate_payload(meta, files)
    write_json(manifest_path, {"package": meta, "files": files,
                              "proof": "contents-only; no execution or native-process claim"})


def verify_package(root, manifest, lock_path):
    saved = read_json(manifest)
    meta = validate_metadata(saved["package"], lock_path)
    actual = payload_inventory(root, meta.get("additional_pe_files", []))
    if saved["files"] != actual:
        changed = sorted(p for p in actual.keys() | saved["files"].keys()
                         if actual.get(p) != saved["files"].get(p))
        raise ContractError(f"Package {meta['id']} inventory differs: {changed[:20]}")
    validate_payload(meta, actual)
    return saved


def merge_packages(plan, contract, lock_path):
    if plan.get("schema") != 1 or not plan.get("packages"):
        raise ContractError("Expected a nonempty schema-1 package plan")
    if contract.get("schema") != 1 or not contract.get("required_files"):
        raise ContractError("Expected a nonempty schema-1 distribution contract")
    packages, files, folded = {}, {}, {}
    for entry in plan["packages"]:
        root = Path(entry["root"]).resolve()
        saved = verify_package(root, entry["manifest"], lock_path)
        meta = saved["package"]
        if meta["id"] in packages:
            raise ContractError(f"Duplicate package ID: {meta['id']}")
        packages[meta["id"]] = meta
        for rel, record in saved["files"].items():
            key = rel.casefold()
            if key in folded and folded[key] != rel:
                raise ContractError(f"Case-insensitive package collision: {rel}")
            folded[key] = rel
            if rel in files:
                if files[rel]["record"] != record:
                    raise ContractError(f"Conflicting package payload: {rel}")
                files[rel]["owners"].append(meta["id"])
            else:
                files[rel] = {"record": record, "source": root / rel, "owners": [meta["id"]]}
    missing = set(contract["required_packages"]) - packages.keys()
    if missing:
        raise ContractError(f"Missing required packages: {sorted(missing)}")
    for meta in packages.values():
        for dependency, version in meta["depends"].items():
            if dependency not in packages or packages[dependency]["version"] != version:
                raise ContractError(f"{meta['id']} requires {dependency}={version}")
    visiting, visited = set(), set()

    def visit(name):
        if name in visiting:
            raise ContractError(f"Dependency cycle at {name}")
        if name not in visited:
            visiting.add(name)
            for dependency in packages[name]["depends"]:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

    for name in packages:
        visit(name)
    for rel in contract["required_files"]:
        relative_path(rel)
        if rel not in files or files[rel]["record"]["size"] == 0:
            raise ContractError(f"Missing/empty distribution file: {rel}")
    if not any(f["record"]["pe_candidate"] for f in files.values()):
        raise ContractError("Distribution has no PE candidates")
    return packages, files


def trim_builtins(files, contract):
    path = contract["builtin_list"]
    if path not in files or contract["git_binary"] not in files:
        raise ContractError("Builtin list and Git binary are mandatory")
    names = files[path]["source"].read_text(encoding="utf-8").splitlines()
    if not names or len(names) != len(set(names)):
        raise ContractError("Empty or duplicate builtin names")
    if any(not re.fullmatch(r"git-[a-z0-9-]+\.exe", n) for n in names):
        raise ContractError("Invalid builtin list entry")
    git_hash = files[contract["git_binary"]]["record"]["sha256"]
    removed, already_absent = [], []
    preserve = set(contract["preserve_builtin_names"])
    for name in names:
        if name in preserve:
            continue
        for directory in contract["builtin_directories"]:
            rel = f"{directory}/{name}"
            relative_path(rel)
            if rel not in files:
                already_absent.append(rel)
                continue
            if rel in contract["required_files"]:
                raise ContractError(f"Builtin trim would remove required file: {rel}")
            if files[rel]["record"]["sha256"] != git_hash:
                raise ContractError(f"Builtin is not byte-identical to git.exe: {rel}")
            removed.append(rel)
            del files[rel]
    return {"removed": removed, "already_absent": already_absent,
            "list_sha256": files[path]["record"]["sha256"],
            "scope": "Declared builtins only; native harness must compare against this Git's builtin list"}


def assemble(plan_path, contract_path, lock_path, output):
    output = Path(output).resolve()
    report = output.with_name(output.name + ".assembly.json")
    if output.exists() or report.exists():
        raise ContractError("Assembly requires a new output directory and report path")
    contract = read_json(contract_path)
    packages, files = merge_packages(read_json(plan_path), contract, lock_path)
    trim = trim_builtins(files, contract)
    # Check path-prefix collisions (a file 'usr' would shadow 'usr/bin/...').
    names = {p.casefold() for p in files}
    for rel in files:
        if any(p.as_posix().casefold() in names for p in relative_path(rel).parents
               if p.as_posix() != "."):
            raise ContractError(f"File/directory collision: {rel}")
    required_directories = contract.get("required_directories", [])
    if not isinstance(required_directories, list):
        raise ContractError("required_directories must be an explicit path list")
    for rel in required_directories:
        path = relative_path(rel)
        if any(candidate.as_posix().casefold() in names for candidate in (path, *path.parents)
               if candidate.as_posix() != "."):
            raise ContractError(f"Required directory collides with payload file: {rel}")
    output.mkdir(parents=True)
    for rel in required_directories:
        (output / rel).mkdir(parents=True, exist_ok=True)
    for rel, entry in sorted(files.items()):
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry["source"], destination)
        if digest(destination) != entry["record"]["sha256"]:
            raise ContractError(f"Input changed during assembly: {rel}")
    additional_pe = sorted({rel for meta in packages.values() for rel in meta.get("additional_pe_files", [])
                            if rel in files})
    measured = payload_inventory(output, additional_pe)
    if measured != {p: e["record"] for p, e in files.items()}:
        raise ContractError("Final assembly inventory differs")
    write_json(report, {
        "schema": 1, "status": "assembled-unverified", "profile": contract["profile"],
        "source_lock_sha256": digest(lock_path), "contract_sha256": digest(contract_path),
        "packages": packages, "files": measured, "builtin_trim": trim,
        "additional_pe_files": additional_pe, "required_directories": required_directories,
        "pending_gates": ["raw-native-ARM64-PE", "live-native-processes", "loaded-module-closure",
                          "declared-loadable-native-PE-and-behavior",
                          "offline-git", "HTTPS", "credentials", "SSH", "native-build-tools"]
    })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("sources.lock.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--root", type=Path, required=True)
    snap.add_argument("--metadata", type=Path, required=True)
    snap.add_argument("--manifest", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    asm = sub.add_parser("assemble")
    asm.add_argument("--plan", type=Path, required=True)
    asm.add_argument("--contract", type=Path, default=Path(__file__).with_name("distribution.json"))
    asm.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot(args.root, args.metadata, args.manifest, args.lock)
    elif args.command == "verify":
        saved = verify_package(args.root, args.manifest, args.lock)
        print(f"Verified contents of {saved['package']['id']}: {len(saved['files'])} files")
    else:
        print(assemble(args.plan, args.contract, args.lock, args.output))


if __name__ == "__main__":
    main()
