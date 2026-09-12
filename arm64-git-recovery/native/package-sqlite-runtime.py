"""Package byte-identical MSYS SQLite runtime after actual combined-runtime proof."""

import argparse
from compression import zstd
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile

from sources import ContractError, digest, inventory
from sqlite_consumer_inputs import sealed_json, verify_files
from sqlite_pe import inspect_pe
from ssh_bootstrap import require_memory

spec = importlib.util.spec_from_file_location("sqlite_sealer", Path(__file__).with_name("seal-native-sqlite.py"))
sealer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sealer)

HANDOFF_SHA = "9bfa0f82b6456b546e654e53da68661555fee0d8a9656b592258a052c2edf718"
COMBINED_SHA = "f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b"


def package_info(size, epoch):
    return (
        "pkgname = libsqlite\n"
        "pkgbase = sqlite\n"
        "pkgver = 3.53.4-1\n"
        "pkgdesc = Native MSYS LP64 SQLite runtime library\n"
        "url = https://www.sqlite.org/\n"
        f"builddate = {epoch}\n"
        "packager = Native SQLite integration\n"
        f"size = {size}\n"
        "arch = aarch64\n"
        "license = LicenseRef-Sqlite\n"
        "depend = msys2-runtime\n"
    ).encode("utf-8")


def verify_archive(path, expected, pkginfo):
    with path.open("rb") as compressed, zstd.ZstdFile(compressed, "rb") as stream:
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            actual = {}
            for member in archive:
                if member.isdir():
                    continue
                if not member.isfile() or member.name in actual:
                    raise ContractError("Unexpected archive member type or duplicate")
                handle = archive.extractfile(member)
                if handle is None:
                    raise ContractError("Missing archive member contents")
                with handle:
                    data = handle.read()
                actual[member.name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    wanted = {".PKGINFO": {"size": len(pkginfo), "sha256": hashlib.sha256(pkginfo).hexdigest()}, **expected}
    if actual != wanted:
        raise ContractError("Compressed package contents differ from the exact input payload")
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--prepared-sha256", required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--proof-sha256", required=True)
    parser.add_argument("--ordinary", type=Path, required=True)
    parser.add_argument("--ordinary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = Path(r"C:\ag-sqlite-combined-01")
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(project):
        raise ContractError("Fresh private package output required")
    prepared = sealed_json(args.prepared / "prepare.json", args.prepared_sha256)
    proof = sealed_json(args.proof / "result.json", args.proof_sha256)
    ordinary = sealed_json(args.ordinary / "result.json", args.ordinary_sha256)
    if (prepared["combined_receipt_sha256"] != COMBINED_SHA
            or proof.get("combined_receipt_sha256") != COMBINED_SHA
            or proof["status"] != "native-sqlite-unit-proofs-passed" or proof["errors"]
            or proof["input_integrity_errors"] or len(proof["steps"]) != 63
            or len(proof["native_consumer_reuse"]) != 3):
        raise ContractError("Complete native combined-runtime compatibility proof required")
    if (ordinary["status"] != "ordinary-native-sqlite-combined-runtime-apis-passed"
            or ordinary["combined_receipt_sha256"] != COMBINED_SHA or not ordinary["inputs_unchanged"]
            or len(ordinary["steps"]) != 3 or any(not s["process"]["passed"] for s in ordinary["steps"])):
        raise ContractError("Ordinary non-debugger native combined-runtime API proof required")
    for step in proof["steps"]:
        module = step.get("loaded_modules", {}).get("msys-2.0.dll")
        if (not step["process"]["passed"] or step["raw_exit"] != 0 or not module
                or module["sha256"] != prepared["runtime_sha256"]):
            raise ContractError(f"A consumer did not prove the exact combined runtime: {step['name']}")
    drain = sealer.require_launcher_exit(proof["launcher"])
    ordinary_drain = sealer.require_launcher_exit(ordinary["launcher"])
    old = Path(r"C:\ag-sqlite-e138-01")
    handoff = sealed_json(old / "handoff-01/result.json", HANDOFF_SHA)
    split = handoff["payloads"]["libsqlite"]
    source = Path(split["stage"])
    verify_files(source, split["files"])
    expected_names = {"usr/bin/msys-sqlite3-0.dll", "usr/share/licenses/libsqlite/LICENSE"}
    if set(split["files"]) != expected_names:
        raise ContractError("MVP package must contain exactly the runtime DLL and its license")
    verify_files(prepared["runtime_path"], prepared["runtime_files"])
    pe = inspect_pe(source / "usr/bin/msys-sqlite3-0.dll")
    validated = Path(prepared["runtime_path"]) / "usr/bin/msys-sqlite3-0.dll"
    if digest(validated) != pe["sha256"]:
        raise ContractError("Package is not the exact validated SQLite DLL")
    sqlite_imports = {row["name"].lower() for row in pe["imports"]}
    if "msys-2.0.dll" not in sqlite_imports:
        raise ContractError("SQLite payload is not a genuine MSYS runtime consumer")
    unsupported = sqlite_imports - {"msys-2.0.dll", "kernel32.dll", "advapi32.dll"}
    if unsupported:
        raise ContractError(f"Unaccounted SQLite package dependencies: {sorted(unsupported)}")
    # The archive packages the prior native build unchanged. Record that build's
    # date, not the time of this compatibility test, in package metadata.
    build = json.loads((old / "build-run-02/result.json").read_text())
    epoch = int(build["launcher"]["creation_filetime"] // 10_000_000 - 11_644_473_600)
    pkginfo = package_info(sum(row["size"] for row in split["files"].values()), epoch)
    source_root = old / "prepared/source"
    source_receipt = old / "prepared.upstream.json"
    original_source = sealed_json(source_receipt, "e9bedb318fd6e6051d8d16c5bd026fcd2274f023eeb1df10f7d0b0f5d51a16ba")
    source_files = original_source["files"]
    verify_files(source_root, source_files)
    fossil_commit = (source_root / "manifest.uuid").read_text().strip()
    if len(fossil_commit) != 64 or any(c not in "0123456789abcdef" for c in fossil_commit):
        raise ContractError("Exact upstream Fossil source identity required")
    devel = handoff["payloads"]["libsqlite-devel"]
    header = Path(devel["stage"]) / "usr/include/sqlite3.h"
    if digest(header) != devel["files"]["usr/include/sqlite3.h"]["sha256"]:
        raise ContractError("Native build source-id header changed")
    source_ids = re.findall(r'^#define SQLITE_SOURCE_ID\s+"([^"]+)"', header.read_text(), flags=re.M)
    if len(source_ids) != 1:
        raise ContractError("Missing or ambiguous compiled SQLite source-id")
    source_tree_sha = hashlib.sha256(json.dumps(source_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output.mkdir()
    payload = output / "payload"
    payload.mkdir()
    for name, row in split["files"].items():
        destination = payload / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with (source / name).open("rb") as incoming, destination.open("xb") as outgoing:
            while chunk := incoming.read(1024 * 1024):
                outgoing.write(chunk)
        if digest(destination) != row["sha256"]:
            raise ContractError("Package staging copy differs")
    archive_path = output / "libsqlite-3.53.4-1-aarch64.pkg.tar.zst"
    with archive_path.open("xb") as compressed, zstd.ZstdFile(compressed, "w") as stream:
        with tarfile.open(fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT) as archive:
            for name in [".PKGINFO", *sorted(split["files"])]:
                entry = tarfile.TarInfo(name)
                entry.mtime = epoch
                entry.uid = entry.gid = 0
                entry.uname = entry.gname = "root"
                entry.mode = 0o755 if name.endswith(".dll") else 0o644
                if name == ".PKGINFO":
                    entry.size = len(pkginfo)
                    archive.addfile(entry, io.BytesIO(pkginfo))
                else:
                    entry.size = split["files"][name]["size"]
                    with (payload / name).open("rb") as content:
                        archive.addfile(entry, content)
    members = verify_archive(archive_path, split["files"], pkginfo)
    verify_files(source, split["files"])
    native_files = {name: {**row, "path": str(payload / name),
                           "pe": inspect_pe(payload / name) if name.endswith(".dll") else None}
                    for name, row in split["files"].items()}
    result = {
        "schema": 1, "status": "native-msys-libsqlite-package-combined-runtime-compatibility-proved",
        "package": {"name": "libsqlite", "version": "3.53.4-1", "arch": "aarch64", "target": "aarch64-pc-cygwin",
                    "data_model": "MSYS LP64", "role": "Heimdal/SSH runtime dependency only",
                    "path": str(archive_path), "size": archive_path.stat().st_size, "sha256": digest(archive_path)},
        "files": native_files, "archive_members": members, "payload_root": str(payload),
        "runtime_bundled": False, "depends": ["msys2-runtime"], "runtime_sha256": prepared["runtime_sha256"],
        "combined_runtime_receipt_sha256": COMBINED_SHA,
        "runtime_import_library_sha256": prepared["combined_binaries"]["import_library"]["sha256"],
        "runtime_crt0_sha256": prepared["combined_binaries"]["startup"]["sha256"],
        "runtime_source_commit": prepared["combined_receipt"]["publication"]["commit"],
        "sqlite_source": {
            "repository": "https://www.sqlite.org/src", "vcs": "Fossil", "commit": fossil_commit,
            "prepared_tree_sha256": source_tree_sha,
            "tree_digest_format": "SHA256 UTF-8 JSON of exact prepared files, sorted keys, compact separators",
            "source_archive": original_source["source"], "recipe_inputs": original_source["recipe_inputs"],
            "recipe_collection_commit": "9154e8a73cf7813e3e4b87df14e6aea5776dc571",
            "patched_source": True, "compiled_source_id": source_ids[0],
            "source_receipt_sha256": digest(source_receipt),
        },
        "provenance": {"sqlite_rebuilt": False, "runtime_rebuilt": False,
                       "original_build": str(old / "build-run-02/result.json"),
                       "original_build_sha256": digest(old / "build-run-02/result.json"),
                       "original_seven_split_handoff": str(old / "handoff-01/result.json"),
                       "original_seven_split_handoff_sha256": HANDOFF_SHA,
                       "compiled_with_original_runtime_crt": True,
                       "compatibility_not_rebuild": "Existing native SQLite and consumers validated against907afa09; no claim of relinking old binaries with new CRT",
                       "all_seven_split_pe": prepared["all_seven_split_pe"]},
        "validation": {"proof": str(args.proof / "result.json"), "sha256": args.proof_sha256,
                       "executed_positive_steps": 63, "reused_native_consumers": 3,
                       "every_step_exact_combined_runtime": True, "foreign_bootstrap_in_execution_path": False,
                       "launcher_drain": drain, "ordinary": str(args.ordinary / "result.json"),
                       "ordinary_sha256": args.ordinary_sha256, "ordinary_steps": 3,
                       "ordinary_launcher_drain": ordinary_drain},
        "scope": {"mvp_runtime_only": True, "cli_devel_docs_extensions_packaged": False,
                  "full_upstream_qualified": False, "provider_admitted": False,
                  "historical_failures_waived": False,
                  "remaining": handoff["pending"]},
        "free_ram_gib_at_package": require_memory(),
    }
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"package": str(archive_path), "package_sha256": result["package"]["sha256"],
                      "receipt": str(output / "receipt.json"), "receipt_sha256": digest(output / "receipt.json")}))


if __name__ == "__main__":
    main()
