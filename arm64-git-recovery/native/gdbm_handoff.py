"""Seal the native GDBM successor with explicit qualification and admission scopes."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import write_json


def reference(path):
    return {"path": str(path), "sha256": digest(path), "size": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--drain", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if root != Path(r"C:\ag-gdbm-20260911-01"):
        raise ContractError("Only the explicitly owned GDBM unit may be sealed")
    output = root / "handoff02"
    output.mkdir()
    packages_path = root / "packages02/packages.json"
    packages = json.loads(packages_path.read_text())
    stripping = json.loads((root / "strip-stage02/result.json").read_text())
    archive_audit = json.loads((root / "static-archive-audit02/result.json").read_text())
    source_audit = json.loads((root / "source-audit02/result.json").read_text())
    dynamic = json.loads((root / "stripped-dynamic-api02/result.json").read_text())
    static = json.loads((root / "stripped-static-api02/result.json").read_text())
    stage = root / "stage-stripped02"
    if (inventory(stage) != stripping["files"] or stripping["remaining_private_paths"]
            or not stripping["non_debug_code_equal"] or not stripping["imports_exports_equal"]
            or not source_audit["passed"] or not archive_audit["passed"]):
        raise ContractError("Successor byte/source/audit evidence is incomplete")
    for proof in (dynamic, static):
        if not proof["passed"] or proof["stage_files"] != stripping["files"]:
            raise ContractError("Exact successor installed/moved-root proof is missing")
        for mode in ("installed", "moved"):
            if not proof[mode]["process"]["process"]["passed"] or proof[mode]["raw_exit"]["raw_exit"] != 0:
                raise ContractError("Successor API raw-exit evidence did not pass")
    if any("gdbm" in name.lower() for name in static["client"]["imports"]):
        raise ContractError("Static API did not consume the genuine static archives")
    for package in packages["packages"]:
        if (digest(package["path"]) != package["sha256"] or package["version"] != "1.26-2"
                or package["private_root_occurrences"] != 0
                or not package["archive_and_mtree_readback_complete"]):
            raise ContractError("Final package identity or readback differs")
    verify_tree(root / "compiler", root / "receipts/compiler.json")
    verify_tree(root / "observer", root / "observer.manifest.json")
    autotest_path = root / "autotest-native-final01/result.json"
    autotest = json.loads(autotest_path.read_text())
    autotest_log = root / "autotest-native-final01/original-autotest/command.log"
    if "All 38 tests were successful." not in autotest_log.read_text() or autotest["process"]["process"]["exit"] != 0:
        raise ContractError("The complete unchanged GDBM Autotest suite did not pass semantically")
    dejagnu_path = root / "dejagnu-native01/result.json"
    dejagnu = json.loads(dejagnu_path.read_text())
    if not dejagnu["upstream_semantics_passed"] or dejagnu["upstream_counts"].get("expected passes") != 2:
        raise ContractError("The actual original GDBM DejaGNU tests did not pass")
    images = json.loads((root / "autotest-native-final01/launch.json").read_text())["native_images"]
    if any(digest(root / name) != sha for name, sha in images.items()):
        raise ContractError("The upstream-tested original binaries changed after the final suite")
    signature = root / "logs/gdbm-signature02.log"
    if "[GNUPG:] VALIDSIG 4BE4E62655488EB92ABB468F79FFD94BFCE230B1" not in signature.read_text():
        raise ContractError("The exact pinned GDBM source signature was not verified")
    drain = json.loads(args.drain.read_text())
    if drain.get("remaining_owned_processes") != []:
        raise ContractError("Owned native work has not drained")
    here = Path(__file__).resolve().parent
    source_files = set(here.glob("gdbm_*.py"))
    source_files.update(here.glob("*gdbm*.sh"))
    source_files.add(here / "test_gdbm_package.py")
    for pattern in ("native-gdbm*", "native-expect*", "native-pty-lifetime.c", "native-termios-header.c"):
        source_files.update((here / "fixtures").glob(pattern))
    for pattern in ("gdbm-*.patch", "expect-*.patch"):
        source_files.update((here / "patches").glob(pattern))
    source_snapshot = {}
    for path in sorted(source_files):
        name = path.relative_to(here)
        target = output / "maintained-source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if digest(path) != digest(target):
            raise ContractError("Maintained recipe/driver snapshot changed")
        source_snapshot[name.as_posix()] = {"sha256": digest(target), "size": target.stat().st_size}
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip()
    refs = {
        "packages": packages_path, "stripping": root / "strip-stage02/result.json",
        "static_archive_audit": root / "static-archive-audit02/result.json",
        "source_replay": root / "source-audit02/result.json",
        "dynamic_api": root / "stripped-dynamic-api02/result.json",
        "static_api": root / "stripped-static-api02/result.json",
        "original_autotest": autotest_path, "original_dejagnu": dejagnu_path,
        "source_signature": signature, "compiler_copy": root / "receipts/compiler.json",
        "runtime_inputs": root / "receipts/build-inputs.json",
        "observer_manifest": root / "observer.manifest.json",
        "original_wrapper_negative": root / "reproduce02/result.json",
        "original_wrapper_first_fault": root / "wrapper-debug-original02/result.json",
        "rejected_packages01": root / "packages01/packages.json",
        "rejected_padding_guard": root / "strip-stage01/result.json",
        "pacman_readback": root / "logs/pacman-package-readback02.log",
        "generation_drain": args.drain,
    }
    record = {
        "schema": 1, "status": "native-GDBM-1.26-2-successor-ready-for-independent-intake",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "packages": [{"name": row["name"], "path": row["path"], "sha256": row["sha256"],
                      "size": row["size"], "version": row["version"]} for row in packages["packages"]],
        "stage": {"path": str(stage), "files": stripping["files"], "private_root_occurrences": 0},
        "native_abi": {"target": "aarch64-pc-cygwin", "model": "MSYS LP64", "machine": "0xAA64",
            "runtime_sha256": "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c",
            "paired_import_sha256": "6f19eb725d275d6e9f3564783cf5a18c9f13849b6c8033ca92291ecd3f5a735c",
            "paired_crt_sha256": "29b356f7105386a37bc8b16169e8beac1b0cbc2c1640946df02f85bbae5d3737",
            "compiler_driver_sha256": "0eb57ff0d26c4d7a8da0a028beedc2df4349209bb14ac8a9553d519d06fe679c",
            "full_cpp_qualified": False},
        "features": ["GDBM", "gdbm_compat/NDBM", "shared", "static", "GNU Readline", "NLS", "documentation"],
        "source": {"recipe_commit": "fc03a3300db9bcdd0ccc082749e006abf1a04414",
            "archive_sha256": "6a24504a14de4a744103dcb936be976df6fbe88ccff26065e54c1c47946f4a5e",
            "signer": "4BE4E62655488EB92ABB468F79FFD94BFCE230B1",
            "signature_verified": True, "functional_GDBM_source_files_replayed": 139,
            "preserved_extra_delta": "The adopted root08 source removes one redundant sys/types.h include introduced by the historical recipe patch; exact delta encoded and independently replayed"},
        "maintained_source": {"git_base_commit": base, "git_base_tree": tree,
            "uncommitted_changes": True, "snapshot_root": str(output / "maintained-source"), "files": source_snapshot},
        "qualification": {"autotest": {"successful": 38, "total": 38, "parent_exit": 0,
                "observer_passed": autotest["process"]["process"]["passed"]},
            "dejagnu": {"expected_passes": 2, "parent_exit": 0,
                "observer_passed": dejagnu["process"]["process"]["passed"]},
            "shared_and_static_installed_moved_api": True,
            "exact_successor_modules_and_raw_zero": True,
            "static_client_has_no_gdbm_dll_imports": True,
            "non_debug_PE_and_static_code_unchanged": True,
            "COFF_member_order_symbols_and_resolved_relocations_unchanged": True,
            "complete_package_and_MTREE_readback": True},
        "original_failure_cause": "Generated libtool PATH selected a different installation root for the same native907 runtime during exec; actual child AV at dtable::fixup_after_exec, RVA0x1c1bc. A coherent driver/generator boundary fixes the original commands without replacing wrappers.",
        "limitations": [
            "Generic native observer remains false for the original upstream harness high-exit domains; raw DWORDs, source and process generations are retained, with no broad exceptions or normalization.",
            "GDBM's original 38 Autotest and two DejaGNU assertions pass. The restored private Expect tool's broader self-suite is not fully qualified: ordinary PTY slave open/close causes a retained SIGHUP/read-EIO behavior; no blanket Expect, Tcl or runtime qualification.",
            "Packages are unsigned. Provider admission remains the independent intake owner's decision.",
        ],
        "references": {name: reference(path) for name, path in refs.items()},
        "resources": {"maximum_jobs": 2, "remaining_owned_processes": [], "slots_returned": 2},
        "provider_admitted": False, "berkeley_db_artifacts_changed": False,
        "runtime_Tcl_Perl_compiler_rebuilt": False, "commits_pushes_PRs_CI_settings_changes": False,
    }
    write_json(output / "handoff.json", record)
    print(json.dumps({"path": str(output / "handoff.json"), "sha256": digest(output / "handoff.json")}), flush=True)


if __name__ == "__main__":
    main()
