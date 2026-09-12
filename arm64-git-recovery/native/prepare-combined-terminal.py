"""Bind admitted terminal packages to a private combined-runtime validation input."""

import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import tarfile

from sources import ContractError, digest, inventory, relative_path, verify_tree
from ssh_bootstrap import require_memory, write_json

HERE = Path(__file__).resolve().parent
ROOT = Path(r"C:\ag-readline-e138-01\combined-20260911-01")
HANDOFF = Path(r"C:\Users\crutkasLocal\.copilot\session-state\67ba2e76-32e2-4f0d-a2fe-844ee8fe1d8a\files\combined-runtime-20260911\handoff\combined-runtime-handoff.json")
HANDOFF_SHA = "f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b"
RUNTIME_SHA = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
OBSERVER = Path(r"C:\ag-native-e138-01\native-test-driver-06")
OBSERVER_SHA = "8cbbb4e35af9421fc7ebf23337b92ed35b2e9f923d29db854049c9f5164d1885"
COMPILER = Path(r"C:\ag-e138920f\tc-cpp-guard-01")
COMPILER_SHA = "ed4fa0a4844ee05deca009dc9346320d701ae93cd9f299dc0185a5358001d41c"
PROVIDERS = {
    "ncurses-v2": ("6857ba52e2004b0c7592baa2e2a517c824f54bbfbb7fe2c41b1f93b3415caafd",
                   "616f54ff68966530a9727e91352dcddd546862357db8cfe79e1f8329cda7375e"),
    "terminal-libraries-v2": ("87f290f0bfc7a2dca0c9fe613f8a9e966b3c167be38712ac7fcc4c440b774af7",
                              "710b189876ff0dcb4121b5e037ea2c844c6edfad6b7e9af9c68a12b9eb764656"),
}


def sealed(path, sha):
    if digest(path) != sha:
        raise ContractError(f"Seal differs: {path}")


def windows(path):
    return Path(r"\\wsl.localhost\Ubuntu") / path.lstrip("/") if path.startswith("/root/") else Path(path)


def pe(data):
    if len(data) < 64 or data[:2] != b"MZ":
        raise ContractError("Not an ordinary PE image")
    offset = struct.unpack_from("<I", data, 60)[0]
    if offset < 64 or offset + 26 > len(data) or data[offset:offset + 4] != b"PE\0\0":
        raise ContractError("Invalid PE header")
    machine = struct.unpack_from("<H", data, offset + 4)[0]
    if machine != 0xAA64 or struct.unpack_from("<H", data, offset + 24)[0] != 0x20B:
        raise ContractError(f"Non-AA64 package image: {machine:#x}")
    return {"machine": "0xAA64", "format": "PE32+", "dll": bool(struct.unpack_from("<H", data, offset + 22)[0] & 0x2000)}


def manifest_rows(path):
    rows = {}
    for line in path.read_text().splitlines():
        sha, name = line.split("  ", 1)
        relative_path(name)
        if name in rows or len(sha) != 64:
            raise ContractError("Malformed source component manifest")
        rows[name] = sha
    return rows


def main():
    if ROOT.exists():
        raise ContractError("Fresh combined-runtime input root required")
    sealed(HANDOFF, HANDOFF_SHA)
    runtime = json.loads(HANDOFF.read_text())
    if runtime["runtime"]["sha256"] != RUNTIME_SHA:
        raise ContractError("Unexpected combined runtime")
    memory = require_memory()
    ROOT.mkdir()
    (ROOT / "packages").mkdir()
    (ROOT / "receipts").mkdir()
    shutil.copyfile(HANDOFF, ROOT / "receipts/combined-runtime-handoff.json")
    report = {"schema": 1, "status": "preparing", "minimum_free_gib": memory,
              "runtime_handoff_sha256": HANDOFF_SHA, "runtime_sha256": RUNTIME_SHA,
              "runtime_source_commit": runtime["publication"]["commit"],
              "runtime_source_tree_manifest": runtime["source_manifest"],
              "libraries_rebuilt": False, "packages_rebuilt": False, "runtime_rebuilt": False,
              "packages": [], "links": [], "all_package_pe": {}}
    compiler_manifest = COMPILER.with_name(COMPILER.name + ".copy.json")
    sealed(compiler_manifest, COMPILER_SHA)
    verify_tree(COMPILER, compiler_manifest)
    shutil.copytree(COMPILER, ROOT / "compiler", symlinks=True)
    verify_tree(ROOT / "compiler", compiler_manifest)
    verify_tree(COMPILER, compiler_manifest)
    report["compiler_base_receipt_sha256"] = COMPILER_SHA
    report["compiler_components_replaced"] = {}
    prefix = windows(runtime["prefix"])
    for key in ("public_headers", "runtime_libraries"):
        origin = windows(runtime[key]["path"])
        sealed(origin, runtime[key]["sha256"])
        shutil.copyfile(origin, ROOT / "receipts" / origin.name)
        for name, expected in manifest_rows(origin).items():
            source = prefix / name
            sealed(source, expected)
            target = ROOT / "compiler" / name
            old_sha = digest(target) if target.is_file() else None
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            sealed(target, expected)
            sealed(source, expected)
            report["compiler_components_replaced"][name] = {"before": old_sha, "after": expected}
    for field, name in (("runtime", "bin/msys-2.0.dll"), ("startup", "aarch64-pc-cygwin/lib/crt0.o"),
                        ("import_library", "aarch64-pc-cygwin/lib/libmsys-2.0.a")):
        sealed(ROOT / "compiler" / name, runtime[field]["sha256"])
    observer_manifest = OBSERVER.with_name(OBSERVER.name + ".manifest.json")
    sealed(observer_manifest, OBSERVER_SHA)
    verify_tree(OBSERVER, observer_manifest)
    shutil.copytree(OBSERVER, ROOT / "observer")
    shutil.copyfile(observer_manifest, ROOT / "observer.manifest.json")
    verify_tree(ROOT / "observer", ROOT / "observer.manifest.json")
    report["observer_manifest_sha256"] = OBSERVER_SHA
    export_module = importlib.import_module("export-readline-chain")
    installed = {}
    for provider, (export_sha, handoff_sha) in PROVIDERS.items():
        provider_root = Path(r"C:\ap11-native-provider-intake") / provider
        sealed(provider_root / "export.json", export_sha)
        sealed(provider_root / "handoff.json", handoff_sha)
        for name in ("export.json", "handoff.json"):
            shutil.copyfile(provider_root / name, ROOT / "receipts" / (provider + "-" + name))
        for row in json.loads((provider_root / "export.json").read_text())["packages"]:
            source = Path(row["path"])
            if not source.is_absolute():
                source = provider_root / source
            sealed(source, row["sha256"])
            package = ROOT / "packages" / source.name
            shutil.copyfile(source, package)
            sealed(package, row["sha256"])
            info = {"path": str(package), "size": package.stat().st_size, "sha256": row["sha256"],
                    "provider": provider, "provider_export_sha256": export_sha, "files": {}}
            with tarfile.open(package) as archive:
                members = archive.getmembers()
                names = set()
                for member in members:
                    name = member.name.removeprefix("./").rstrip("/")
                    relative_path(name)
                    if name.casefold() in names:
                        raise ContractError(f"Case-colliding package path: {name}")
                    names.add(name.casefold())
                    if member.isdir():
                        continue
                    if member.issym() or member.islnk():
                        report["links"].append({"package": package.name, "path": name,
                                                "target": member.linkname, "type": "symlink" if member.issym() else "hardlink",
                                                "validation_projection": "canonical regular-file paths used; archive link retained unchanged"})
                        continue
                    if not member.isfile():
                        raise ContractError(f"Unexpected package member: {name}")
                    data = archive.extractfile(member).read()
                    identity = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                    info["files"][name] = identity
                    if name == ".PKGINFO":
                        info["pkginfo"] = data.decode()
                        if "arch = aarch64\n" not in info["pkginfo"]:
                            raise ContractError("Wrong package architecture")
                    if name.lower().endswith((".exe", ".dll")) or data[:2] == b"MZ":
                        report["all_package_pe"][package.name + ":" + name] = {**identity, **pe(data)}
                    if name.endswith(".a"):
                        info.setdefault("coff_archives", {})[name] = {"members": len(export_module.coff_archive(data)),
                                                                     "all_machine": "0xAA64"}
                    if name.startswith("."):
                        continue
                    if name in installed and installed[name] != identity:
                        raise ContractError(f"Conflicting package data: {name}")
                    installed[name] = identity
                    target = ROOT / "sdk" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            report["packages"].append(info)
            sealed(source, row["sha256"])
    payload = ROOT / "runtime-payload"
    for name, row in installed.items():
        if (name.startswith("usr/bin/") and name.lower().endswith(".dll")) or name.startswith(
                ("usr/share/terminfo/", "usr/share/licenses/", "usr/share/locale/")) or name == "etc/inputrc":
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "sdk" / name, target)
            sealed(target, row["sha256"])
    source = ROOT / "compiler/bin/msys-2.0.dll"
    shutil.copyfile(source, payload / "usr/bin/msys-2.0.dll")
    pe(source.read_bytes())
    report["runtime_payload_files"] = inventory(payload)
    report["sdk_files"] = inventory(ROOT / "sdk")
    report["compiler_files"] = inventory(ROOT / "compiler")
    origins = {}
    for name, directory in (("ncurses", "ncurses-static-cxx-01"), ("readline", "readline-01"), ("libedit", "libedit-static-01")):
        root = Path(r"C:\ag-readline-e138-01")
        source_manifest = root / "sources" / name / "source.prepare.json"
        prepared = json.loads(source_manifest.read_text())
        handoff = root / (name + "-handoff-01") / "handoff.json"
        origins[name] = {"handoff": str(handoff), "handoff_sha256": digest(handoff),
                         "source_archive": prepared["source"], "source_tree_manifest": str(source_manifest),
                         "source_tree_manifest_sha256": digest(source_manifest),
                         "recipe_collection_commit": json.loads((HERE / "ssh-recipes.json").read_text())["recipe_collection"]["version"],
                         "recipe_sha256": prepared["recipe_sha256"],
                         "source_git_commit": None, "source_identity_kind": "pinned upstream release archive plus exact patched tree",
                         "binary_stage_manifest": str(root / directory / "stage.inventory.json"),
                         "binary_stage_manifest_sha256": digest(root / directory / "stage.inventory.json")}
    report["source_provenance"] = origins
    sealed(HANDOFF, HANDOFF_SHA)
    verify_tree(COMPILER, compiler_manifest)
    verify_tree(OBSERVER, observer_manifest)
    report["status"] = "real-AA64-packages-and-combined-runtime-inputs-ready-not-yet-compatible"
    write_json(ROOT / "inputs.json", report)
    print(json.dumps({"status": report["status"], "root": str(ROOT), "packages": len(report["packages"]),
                      "pe_images": len(report["all_package_pe"]), "inputs_sha256": digest(ROOT / "inputs.json")}), flush=True)


if __name__ == "__main__":
    main()
