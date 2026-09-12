"""Seal the actual seven-split unit and its separate failed/passing upstream scopes."""

import argparse
from contextlib import closing
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sqlite3
import struct

from sources import ContractError, digest, inventory, verify_tree
from sqlite_build_inputs import SPLITS, TOOLS, recipe
from sqlite_test_results import runner_summary
from ssh_bootstrap import require_memory


def raw_pe(path):
    with path.open("rb") as stream:
        dos = stream.read(64)
        if dos[:2] != b"MZ":
            raise ContractError(f"Missing payload PE header: {path}")
        offset = struct.unpack_from("<I", dos, 60)[0]
        stream.seek(offset)
        header = stream.read(26)
    if (header[:4] != b"PE\0\0" or struct.unpack_from("<H", header, 4)[0] != 0xAA64
            or struct.unpack_from("<H", header, 24)[0] != 0x20B):
        raise ContractError(f"Not ordinary ARM64 PE32+: {path}")
    return {"sha256": digest(path), "machine": "0xAA64", "optional_magic": "0x20B"}


def require_launcher_exit(row):
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.GetProcessTimes.argtypes = [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, row["pid"])
    if not handle:
        error = C.get_last_error()
        if error == 87:
            return {"pid": row["pid"], "creation_filetime": row["creation_filetime"], "state": "process-gone"}
        raise C.WinError(error)
    try:
        times = [W.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[C.byref(t) for t in times]):
            raise C.WinError(C.get_last_error())
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        if created != row["creation_filetime"]:
            state = "old-generation-exited-pid-reused"
        elif kernel.WaitForSingleObject(handle, 0) == 0:
            state = "exact-generation-exited"
        else:
            raise ContractError(f"Owned launcher still active: {row['pid']}")
        return {"pid": row["pid"], "creation_filetime": row["creation_filetime"], "state": state}
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quicktest", type=Path, required=True)
    parser.add_argument("--quicktest-build", type=Path, required=True)
    parser.add_argument("--per-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(r"C:\ag-sqlite-e138-01")
    if args.output.exists() or not args.output.resolve().is_relative_to(root):
        raise ContractError("Fresh owned handoff required")
    proof_path = root / "proof-04/result.json"
    proof = json.loads(proof_path.read_text())
    install_path = root / "install-run-01/result.json"
    install = json.loads(install_path.read_text())
    if (proof["status"] != "native-sqlite-unit-proofs-passed" or len(proof["steps"]) != 66
            or proof["errors"] or proof["input_integrity_errors"]
            or install["status"] != "native-sqlite-phase-passed" or install["input_integrity_errors"]):
        raise ContractError("The full original unit/installation proof is not accepted at its stated scope")
    for name in ("prepared", "bootstrap", "tcl", "readline", "ncurses", "zlib", "observer"):
        verify_tree(root / name, root / f"{name}.inventory.json")
    verify_tree(root / "compiler", root / "compiler-runtime.inventory.json")
    expected = install["split_files"]
    payloads, pe = {}, {}
    for split in SPLITS:
        stage = root / "build-06/splits" / split
        files = inventory(stage)
        if files != expected[split]:
            raise ContractError(f"Frozen installed split changed: {split}")
        payloads[split] = {"stage": str(stage), "file_count": len(files), "files": files}
        for name in files:
            if Path(name).suffix.lower() in (".exe", ".dll"):
                pe[f"{split}/{name}"] = raw_pe(stage / name)
    if any(f"usr/bin/{name}" not in payloads["sqlite"]["files"] for name in TOOLS):
        raise ContractError("Missing original SQLite CLI tool")
    if len(pe) != 64:
        raise ContractError("Expected every one of the 64 deliverable PE files")
    unicode_database = root / "proof-04" / "binding-\u03bb.sqlite"
    with closing(sqlite3.connect(unicode_database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        value = db.execute("SELECT value FROM t").fetchone()[0]
    if value != "native \u03bb \u96ea":
        raise ContractError("Actual Windows Unicode filename/Tcl SQLite UTF-8 roundtrip differs")
    q_report_path, p_report_path = args.quicktest / "result.json", args.per_file / "result.json"
    q_report, p_report = (json.loads(path.read_text()) for path in (q_report_path, p_report_path))
    q_summary, p_summary = runner_summary(args.quicktest_build), runner_summary(args.per_file)
    with closing(sqlite3.connect((args.quicktest_build / "testrunner.db").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        q_jobs = int(db.execute("SELECT value FROM config WHERE name='njob'").fetchone()[0])
    if not 1 <= q_jobs <= 2:
        raise ContractError("Final upstream concurrency exceeds this unit's allocation")
    drains = [require_launcher_exit(row["launcher"]) for row in (proof, install, q_report, p_report)]
    receipts = {str(path): digest(path) for path in (
        root / "adopt-result.json", root / "build-run-02/result.json", root / "extensions-run-01/result.json",
        install_path, proof_path, root / "configure-host-02/result.json", q_report_path, p_report_path,
        root / "environment-differential-01/result.json", root / "environment-differential-02/result.json",
        root / "fts5secure3-hang-01/result.json", root / "fts5secure3-hang-01/timeout-action.json")}
    attempt_prefixes = ("configure-", "build-run-", "extensions-run-", "install-run-", "proof-",
                        "quicktest-", "veryquick-", "host-jim-", "environment-differential-",
                        "foreign-environment-", "mksourceid-diagnostic-", "fts5secure3-", "round1-hang-",
                        "halt-")
    for directory in root.iterdir():
        if directory.is_dir() and directory.name.startswith(attempt_prefixes):
            for name in ("launch.json", "result.json", "timeout-action.json", "frames.json"):
                path = directory / name
                if path.is_file():
                    receipts[str(path)] = digest(path)
    export_files = inventory(Path(__file__).parent)
    report = {
        "schema": 1, "status": "native-msys-sqlite-seven-splits-unit-proved-upstream-gates-retained",
        "version": "3.53.4", "target": "aarch64-pc-cygwin", "data_model": "MSYS LP64",
        "full_cpp_qualified": False, "full_sdk_qualified": False, "full_git_complete": False,
        "provider_admission": False, "recipe": recipe(), "payloads": payloads, "raw_pe": pe,
        "unit_proof": {"sha256": digest(proof_path), "steps": 66, "passed": True,
                       "loadable_extensions": 50, "direct_helper_apis": 5, "win32_only_noop_dlls": 1,
                       "live_dll_proof": "Every step's capture/result binds actual module paths and hashes"},
        "unicode_cross_view": {"windows_filename": str(unicode_database), "value": value, "passed": True},
        "quicktest": {"process": q_report["process"], "summary": q_summary,
                      "passed": q_report["process"]["passed"] and q_summary["passed"]},
        "veryquick_per_file": {"process": p_report["process"], "summary": p_summary,
                               "passed": p_report["process"]["passed"] and p_summary["passed"]},
        "environment_qualification": {
            "same_runtime_and_native_windows_exports": "Observed correct for inherited, replacement and new variables",
            "cross_architecture_msys_exports": "FAILED: ordinary variables lost; special variables retained",
            "runtime_sha256": "1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16",
            "scope": "Separate real runtime gate; private shell hooks do not qualify the runtime"},
        "receipts": receipts, "launcher_drain": drains, "free_ram_gib_at_seal": require_memory(),
        "resource_policy": {"maximum_aggregate_build_test_jobs": 2, "quicktest_initial_jobs": q_report["jobs"],
                            "quicktest_final_jobs": q_jobs, "nested_make_jobs": 1,
                            "scope": "Existing two-slot suballocation only; any increase is bound by an upstream administrative control receipt"},
        "observer_drain_contract": "Immutable observer waits for zero job active processes and drains in finally; completed receipts retained even on failed scopes",
        "recipe_export": {"path": str(Path(__file__).parent), "files": export_files},
        "pending": ["Review full upstream failures/timeouts and missing native sanitizer libraries",
                    "Producer-qualified cross-architecture MSYS child-info/environment fix",
                    "Provider admission and independent Tcl/compiler/full Git qualification"],
    }
    args.output.mkdir()
    for split, data in payloads.items():
        (args.output / f"{split}.inventory.json").write_text(json.dumps({
            "schema": 1, "package": split, "version": "3.53.4", "admitted": False,
            "unit_proof_sha256": digest(proof_path), **data}, indent=2) + "\n")
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "result": str(args.output / "result.json"),
                      "sha256": digest(args.output / "result.json"), "pe_files": len(pe),
                      "payload_files": sum(p["file_count"] for p in payloads.values())}))


if __name__ == "__main__":
    main()
