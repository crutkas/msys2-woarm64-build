"""Seal scoped Tcl evidence and verify that the owned execution generations have drained."""

from collections import Counter
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import tarfile

from qualify import ROOT, PROFILE, digest, import_tools, read_json, require, require_memory, verify_inputs, write_json
from package_provider import validate_archive


def reference(path):
    return {"path": str(path), "sha256": digest(path)}


def generation_state(pid, born):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4]
    api.GetProcessTimes.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    handle = api.OpenProcess(0x100000 | 0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        require(error == 87, f"Cannot inspect recorded PID {pid}: Win32 {error}")
        return {"pid": pid, "creation_filetime": born, "state": "process-no-longer-exists"}
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not api.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            raise ctypes.WinError(ctypes.get_last_error())
        actual = times[0].dwHighDateTime << 32 | times[0].dwLowDateTime
        if actual != born:
            return {"pid": pid, "creation_filetime": born, "state": "pid-reused-not-owned-generation"}
        state = api.WaitForSingleObject(handle, 0)
        require(state == 0, f"Recorded owned process generation is still active: {pid}/{born}")
        return {"pid": pid, "creation_filetime": born, "state": "owned-generation-exited"}
    finally:
        api.CloseHandle(handle)


def main():
    sources = import_tools()
    verify_inputs()
    output = ROOT / "handoff-02"
    output.mkdir()
    inputs = read_json(ROOT / "inputs.json")
    selected = PROFILE + ["unload"]
    rows, skips, total = [], Counter(), Counter()
    for name in selected:
        root = ROOT / ("isolated-01-" + name)
        record = read_json(root / "result.json")
        summary = record["summaries"][0]
        require(record["semantic_passed"] and summary["failed"] == 0 and record["inputs_unchanged"],
                "A selected unchanged file has an unresolved semantic failure")
        require(name == "basic" or record["process"]["passed"], "A positive file failed observation")
        total.update({k: summary[k] for k in ("total", "passed", "skipped", "failed")})
        skips.update(constraint for _, constraint in record["skipped_tests"])
        rows.append({"file": name + ".test", "source_sha256": digest(ROOT / "source/tests" / (name + ".test")),
                     "summary": summary, "skips": record["skipped_tests"],
                     "result": reference(root / "result.json"), "launch": read_json(root / "launch.json"),
                     "observer": reference(root / "native-job.json"),
                     "observer_passed": record["process"]["passed"],
                     "modules": reference(root / "modules.json")})
    require(dict(total) == {"total": 2922, "passed": 2863, "skipped": 59, "failed": 0},
            "The final selected-scope totals differ")
    require(sum(skips.values()) == total["skipped"], "Constraint-level skip accounting differs")
    not_selected = sorted(path.name for path in (ROOT / "source/tests").glob("*.test")
                          if path.stem not in selected)
    coverage = {"selected": rows, "totals": dict(total), "skip_constraints": dict(skips),
                "unselected_core_files": not_selected,
                "original_tests": "Selected test files exactly equal the pinned upstream 8.6.12 archive",
                "preexisting_msys_test_patch_differences": inputs["preexisting_patched_test_files_not_in_profile"],
                "isolation": "One fresh native tcltest interpreter per selected file, sequentially",
                "full_suite": False, "ci_skip_inherited": False}
    write_json(output / "coverage.json", coverage)

    observations, generations, high_exits = [], set(), []
    jobs = sorted(ROOT.glob("*/native-job.json")) + sorted(ROOT.glob("provider-*/*.native-job.json"))
    for path in jobs:
        observed = read_json(path)
        require(not observed["timed_out"] and observed["observation_count_matches"] and
                not observed["unobserved_process_ids"], "An owned job lacks complete drain observation")
        observations.append({"record": reference(path), "passed": observed["passed"],
                             "parent_raw_exit": observed["parent_raw_exit"],
                             "created": observed["created_processes"], "observed": observed["observed_processes"]})
        for row in observed["native_target_exits"]:
            generations.add((row["pid"], row["created"]))
        high_exits.extend({"observation": str(path), **row} for row in observed["unrelayed_high_exits"])
    for path in sorted(ROOT.glob("*/launch.json")) + sorted(ROOT.glob("provider-*/*.launch.json")):
        row = read_json(path)
        generations.add((row["pid"], row["creation_filetime"]))
    states = [generation_state(pid, born) for pid, born in sorted(generations)]
    drain = {"at_utc": datetime.now(timezone.utc).isoformat(), "aggregate_grant": 2,
             "observer_jobs": observations, "generations": states, "active_owned_generations": 0,
             "free_memory_bytes": require_memory(),
             "observer_drain_contract": "The sealed observer returns normally only after job active count "
                                        "reaches zero, and its finally block verifies drain before closing the job.",
             "returnable_jobs": 2}
    write_json(output / "drain.json", drain)

    provider_path = ROOT / "provider-02/result.json"
    provider = read_json(provider_path)
    require(sources.inventory(provider["payload"]) == provider["files"], "Exported provider changed")
    archive = Path(provider["archive"]["path"])
    require(digest(archive) == provider["archive"]["sha256"], "Exported archive changed")
    validate_archive(archive, provider["files"])
    require(digest(archive) == digest(ROOT / "provider-01/tcl-native-msys-8.6.12-provider.tar.gz"),
            "The two prefix-independent exports are not byte-identical")
    api_path = ROOT / "relocated-provider-api-01/result.json"
    api = read_json(api_path)
    require(api["status"] == "passed" and api["runtime"]["unchanged"], "Relocated installed API not qualified")
    negative_path = ROOT / "expected-negative-01/result.json"
    negative = read_json(negative_path)
    raw_negative = read_json(ROOT / "expected-negative-01/native-job.json")
    require(negative["semantic_passed"] and negative["summaries"][0]["passed"] == 1 and
            raw_negative["parent_raw_exit"] == 0 and not raw_negative["passed"] and
            len(raw_negative["unrelayed_high_exits"]) == 1 and
            raw_negative["unrelayed_high_exits"][0]["raw_exit"] == 256,
            "The isolated original expected-negative/raw-exit evidence differs")

    retained = {
        "core-profile-01": "Eight failures from absent Unix TMPDIR; private TMPDIR fixes all temporary-file failures",
        "core-profile-02": "Single-process VFS load leaves deleted temporary DLL state that prevents later fork. "
                           "Unchanged upstream per-file isolation resolves regexp-14.3 without changing its oracle",
        "installed-api-01": "Semantic API passed; strict helper rejected equivalent extended-length Win32 DLL paths",
        "installed-api-02": "Raw paths preserved; same Win32 namespace-spelling mismatch. Frozen helper unchanged",
        "expected-negative-01": "Original basic-46.2 oracle passes; native MSYS exec-successor leaf raw256 "
                                "remains a real expected program failure, rejected by the collector",
    }
    maintained = {}
    archive_source = output / "maintained-native-tcl-qualification.tar.gz"
    with archive_source.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as tar:
            for path in sorted(Path(__file__).parent.iterdir()):
                if path.suffix not in (".py", ".tcl"):
                    continue
                maintained[path.name] = reference(path)
                info = tarfile.TarInfo(path.name)
                info.size, info.mode, info.mtime = path.stat().st_size, 0o644, 0
                with path.open("rb") as data:
                    tar.addfile(info, data)
    sqlite_module = Path(provider["payload"]) / "usr/lib/tcl8/8.6/tdbc/sqlite3-1.1.3.tm"
    require(digest(sqlite_module) == digest(ROOT / "source/pkgs/tdbcsqlite3-1.1.3/library/tdbcsqlite3.tcl"),
            "Installed TDBC SQLite Tcl module differs from its original source")
    verify_inputs()
    write_json(output / "result.json", {
        "schema": 1, "status": "native-msys-tcl-scoped-qualified-admission-gated",
        "supersedes": reference(ROOT / "result.json"),
        "revision_reason": "Distinguish registered MSYS exec-successor leaf wait status from "
                           "SQLite/Jim foreign-overlay topology, based on parent-relayed runtime-owner analysis",
        "package": "tcl-msys", "version": "8.6.12", "target": "aarch64-pc-cygwin",
        "platform": "unix", "data_model": "LP64", "word_size": 8, "pointer_size": 8, "threads": True,
        "rebuilds": 0, "compiler_or_runtime_changes": 0, "commits_pushes_ci_global_changes": 0,
        "coverage": {"totals": dict(total), "files": selected, "constraint_skips": dict(skips),
                     "details": reference(output / "coverage.json"), "full_upstream_suite": False,
                     "unselected_core_file_count": len(not_selected), "bundled_full_suites_run": False},
        "installed_api": {"result": reference(api_path),
                          "modules": reference(ROOT / "relocated-provider-api-01/validated-modules.json"),
                          "raw_modules": reference(ROOT / "relocated-provider-api-01/modules.json"),
                          "scope": "Exact native interpreter/core/msys/zlib/Itcl/TDBC/Thread DLLs; "
                                   "wide arithmetic, Unicode filename+UTF-8 data, dict/list/regexp/zlib, "
                                   "Itcl4.2.2/TDBC1.1.3 and Thread2.8.7 exchange"},
        "dltest": {"actual_dll_count": 7, "all_prebuilt": True,
                   "files": {p.name: digest(p) for p in sorted((ROOT / "test-bin/dltest").glob("*.dll"))},
                   "scope": "Unchanged load.test30/30 and unload.test27/27, native raw0, no fabricated DLL count"},
        "expected_negative": {"result": reference(negative_path),
                              "observer": reference(ROOT / "expected-negative-01/native-job.json"),
                              "semantic": "Original upstream basic-46.2 passed",
                              "raw_high_exits": raw_negative["unrelayed_high_exits"],
                              "observer_passed": False, "relay_records_forged": False,
                              "parent_relayed_runtime_analysis": "These are ordinary MSYS exec-successor "
                              "leaf exits with registered cygstarted. _exit(1) yields POSIX wait status256; "
                              "the native parent correctly understands1. This is not the foreign-overlay "
                              "helper topology and does not turn an expected program failure into success.",
                              "collector_limit": "Current job JSON does not capture cygstarted/final-exit-domain; "
                              "actual generation domain remains unproven and failclosed. Do not decode by "
                              "image, parent topology or numeric code alone. EXITCODE_FORK_FAILED0x00800000 "
                              "is distinct and must never be decoded as an ordinary wait status.",
                              "admission": "Pending shared runtime/observer owner qualification; no blanket high-exit approval"},
        "provider": {"receipt": reference(provider_path), "payload": provider["payload"],
                     "archive": reference(archive), "payload_files": len(provider["files"]),
                     "changed_metadata_files": 4, "relative_aliases": provider["aliases"],
                     "second_prefix_archive_byte_identical": True,
                     "metadata_environment": provider["metadata_environment"],
                     "metadata_contract": provider["metadata_contract"],
                     "pkg_config_execution": provider["pkg_config_execution"],
                     "alias_scope": provider["alias_scope"]},
        "bundled_database_scope": {
            "tdbc_sqlite_module": reference(sqlite_module),
            "sqlite3_binding": "Separate SQLite-child provider; original bundled sqlite3.36.0 intentionally excluded",
            "mysql_odbc_postgres": "Exact installed DLLs/scripts retained; no connector/account/remote database tests run"},
        "preserved_failures": {name: {"reason": reason, "result": reference(ROOT / name / "result.json")}
                               for name, reason in retained.items()},
        "all_raw_high_exits": high_exits,
        "inputs": {"before_and_after_inventories": reference(ROOT / "inputs.json"),
                   "unchanged": True, "original_stage_unchanged": True,
                   "core_and_bundled_library_bytes_unchanged": True},
        "maintained_export": {"archive": reference(archive_source), "sources": maintained,
                              "imported_tools": inputs["receipt_seals"]},
        "drain": reference(output / "drain.json"), "jobs_returnable": 2,
        "remaining_gates": ["Expected-negative native wait-status observer admission",
                            "Full upstream and bundled suites were not claimed",
                            "Full suites need separately reviewed concurrency/platform/local-fixture constraints",
                            "pkg-config process validation in an approved provider",
                            "Pipeline archive extraction/alias activation",
                            "Separate SQLite binding and external-connector qualifications"],
        "full_git_done": False,
    })
    print(json.dumps({"result": reference(output / "result.json"), "coverage": dict(total),
                      "observer_jobs": len(jobs), "owned_generations_drained": len(states),
                      "jobs_returnable": 2}, indent=2))


if __name__ == "__main__":
    main()
