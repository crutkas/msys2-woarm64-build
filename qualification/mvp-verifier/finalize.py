"""Seal an independent mixed-result verdict without changing any producer artifact."""

from collections import Counter
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from audit import inspect_pe, inventory
from observe import save, sha


ROOT = Path(r"C:\ag-tcl-e138-01\independent replay 20260911-01")
NAMED_SHA = "7a4e99306da86abfc5591b96056ef06279bb8c4ca7353a7572a0e266abcdc854"


def ref(path):
    return {"path": str(path), "sha256": sha(path), "size": path.stat().st_size}


def compare_bytes(left, right):
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            aa, bb = a.read(1024 * 1024), b.read(1024 * 1024)
            if aa != bb:
                return False
            if not aa:
                return True


def observe_drain():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    identities, records = set(), []
    for path in ROOT.rglob("observation.json"):
        if "candidate with spaces" in path.parts:
            continue
        record = json.loads(path.read_text())
        if record.get("active_owned_at_cleanup") != 0:
            raise ValueError("A verifier-owned job has not drained")
        records.append({"path": str(path), "sha256": sha(path), "status": record["status"],
                        "parent_raw_exit": record.get("parent_raw_exit")})
        identities.update((p["pid"], p["creation_filetime"]) for p in record.get("processes", []))
    states = []
    for pid, born in sorted(identities):
        handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error != 87:
                raise ctypes.WinError(error)
            state = "recorded-process-no-longer-exists"
        else:
            try:
                ts = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in ts]):
                    raise ctypes.WinError(ctypes.get_last_error())
                actual = ts[0].dwHighDateTime << 32 | ts[0].dwLowDateTime
                if actual != born:
                    state = "PID-reused-not-recorded-generation"
                elif kernel.WaitForSingleObject(handle, 0) == 0:
                    state = "recorded-generation-exited"
                else:
                    raise ValueError(f"Recorded verifier-owned generation remains active: {pid}/{born}")
            finally:
                kernel.CloseHandle(handle)
        states.append({"pid": pid, "creation_filetime": born, "state": state})
    return {"observed_jobs": records, "recorded_generations": states, "active_recorded_generations": 0,
            "all_job_cleanup_active_counts_zero": True, "new_grant_returnable": 3}


def triage_paths(artifact, scan):
    counts, file_counts, selected, all_rows = Counter(), Counter(), [], []
    for row in scan["embedded_paths"]:
        path = artifact / row["file"]
        sections = inspect_pe(path)["sections"] if row["is_pe"] else []
        categories = set()
        for match in row["matches"]:
            section = next((s["name"] for s in sections
                            if s["raw"] <= match["offset"] < s["raw"] + s["raw_size"]), None)
            text = match["value"]
            if section and section.startswith(".debug"):
                category = "debug-section-provenance-not-runtime-path-lookup"
            elif not row["is_pe"] and ("/test/" in row["file"] or "/tests/" in row["file"]):
                category = "non-PE-upstream-test-data-not-executed"
            elif row["file"] == "mingwarm64/bin/libcurl-4.dll" and "ca-bundle.crt" in text:
                category = "operational-CA-default-confirmed-by-real-failure"
            elif "/locale" in text and row["is_pe"]:
                category = "locale-default-candidate-disclosed-or-unverified-not-retested"
            elif row["is_pe"] and re.search(r"\.(?:c|cc|cpp|cxx|h|hpp)(?:$|[ :])", text):
                category = "source-filename-literal-no-file-lookup-proven"
            else:
                category = "other-embedded-path-candidate-not-proven-operational"
            counts[category] += 1
            categories.add(category)
            current = {"file": row["file"], "offset": match["offset"], "section": section,
                       "category": category, "value": text}
            all_rows.append(current)
            if category == "operational-CA-default-confirmed-by-real-failure":
                selected.append(current)
        file_counts.update(categories)
    return {"path_candidate_file_count": len(scan["embedded_paths"]),
            "pe_candidate_file_count": sum(r["is_pe"] for r in scan["embedded_paths"]),
            "matches_by_category": dict(counts), "files_by_category_nonexclusive": dict(file_counts),
            "confirmed_operational": selected, "matches": all_rows,
            "warning": "Counts are NOT vulnerability or defect counts. COFF /number section aliases are "
                       "resolved to actual section names; debug, source-name, test-data and unknown candidates "
                       "are not promoted to runtime dependencies without execution evidence."}


def observations(base, artifact):
    rows, nonzero, outside_images, outside_modules = [], [], [], []
    unique = set()
    system = Path(r"C:\Windows")
    for path in sorted(base.glob("*/observation.json")):
        record = json.loads(path.read_text())
        if record.get("active_owned_at_cleanup") != 0:
            raise ValueError(f"Unproved process drain: {path}")
        row = {"case": path.parent.name, "record": ref(path), "status": record["status"],
               "parent_raw_exit": record.get("parent_raw_exit"), "timed_out": record.get("timed_out"),
               "created": record.get("created_processes"), "observed": record.get("observed_processes"),
               "missing_events": record.get("missing_process_events"),
               "unidentified": record.get("unidentified_processes", []),
               "module_snapshot_error_count": len(record.get("module_snapshot_errors", []))}
        if record["status"] != "observed":
            row["qualification"] = "VERIFIER-INCOMPLETE attempt; not an artifact result"
        else:
            for process in record["processes"]:
                unique.add((process["pid"], process["creation_filetime"]))
                if process.get("raw_exit") != 0:
                    nonzero.append({"case": row["case"], **process})
                if process.get("image"):
                    value = Path(process["image"])
                    if not value.is_relative_to(artifact) and not value.is_relative_to(system):
                        outside_images.append({"case": row["case"], **process})
            for module in record["module_snapshots"]:
                value = Path(module["path"])
                if not value.is_relative_to(artifact) and not value.is_relative_to(system):
                    outside_modules.append({"case": row["case"], **module})
        rows.append(row)
    return {"cases": rows, "unique_measured_generations": len(unique), "raw_nonzero_processes": nonzero,
            "non_SystemRoot_external_process_images": outside_images,
            "non_SystemRoot_external_sampled_modules": outside_modules,
            "module_coverage": "Ordinary-process sampling, not exhaustive DLL load tracing"}


def main():
    output = ROOT / "report-01"
    output.mkdir()
    generation_records = {}
    for name in ("candidate-01", "named ZIP"):
        custody, base = ROOT / (name + " custody"), ROOT / (name + " baseline")
        intake = json.loads((custody / "intake.json").read_text())
        artifact = Path(intake["extraction"])
        after = inventory(artifact)
        changes = [{"path": p, "before": intake["files"].get(p), "after": after.get(p)}
                   for p in sorted(after.keys() | intake["files"].keys()) if after.get(p) != intake["files"].get(p)]
        scan = json.loads((custody / "static-audit.json").read_text())
        triage = triage_paths(artifact, scan)
        save(output / (name + "-path-triage.json"), triage)
        if name == "candidate-01":
            source_unchanged = inventory(Path(intake["source"])) == intake["files"]
            manifest_path = Path(intake["producer_manifest"]["path"])
            manifest_unchanged = sha(manifest_path) == intake["producer_manifest"]["sha256"]
            limitations_inside = [n for n in after if n in ("README-HANDOFF.md", "provenance.json", "manifest.json")]
            conflict_count = len(intake["tcl_conflict_scope_excluded_from_functional_judgment"])
        else:
            source_unchanged = sha(intake["archive"]["path"]) == intake["archive"]["sha256"]
            manifest_path = Path(intake["producer_receipt"]["path"])
            manifest_unchanged = sha(manifest_path) == intake["producer_receipt"]["sha256"]
            limitations_inside = [n for n in after if n in ("README-HANDOFF.md", "provenance.json", "manifest.json")]
            manifest = json.loads((artifact / "manifest.json").read_text())
            conflict_count = sum(re.search(r"(?i)(?:^|-)(?:tcl|tk|itcl)(?:$|-)",
                                          row.get("provenance", {}).get("package", "")) is not None
                                 for row in manifest["files"].values())
        if not source_unchanged or not manifest_unchanged:
            raise ValueError("Producer input mutated during independent verification")
        generation_records[name] = {
            "custody": ref(custody / "intake.json"), "extraction": str(artifact), "file_count": len(after),
            "all_pe_count": len(scan["pe"]), "non_aa64": scan["non_aa64"], "pe_parse_errors": scan["pe_parse_errors"],
            "static_unresolved_imports": [r for r in scan["static_import_closure"]
                                          if r["classification"] == "unresolved-static-import"],
            "static_audit": ref(custody / "static-audit.json"), "path_triage": ref(output / (name + "-path-triage.json")),
            "post_replay_file_changes": changes, "producer_input_unchanged": source_unchanged,
            "producer_manifest_or_receipt_unchanged": manifest_unchanged,
            "self_contained_metadata_files_present": limitations_inside,
            "Tcl_Tk_functional_verdict_excluded_file_count": conflict_count,
            "environment": ref(base / "environment-policy.json"),
            "behavior": observations(base, artifact),
        }
    artifact = Path(generation_records["named ZIP"]["extraction"])
    final_dir = Path(r"C:\ag-mvp-f6-20260911\first-artifact-901256b")
    copies = [
        final_dir / "arm64-vnext-2026-08-31-v1-git-bash-mvp-arm64.zip",
        final_dir / "independent-recreation.zip",
        Path(r"C:\ag-mvp-f6-20260911\final-zip-readback-01\recreated.zip"),
        Path(r"C:\ag-mvp-f6-20260911\final ZIP readback 02\recreated.zip"),
        ROOT / "fresh independently recreated.zip",
    ]
    reproduction = [ref(path) for path in copies]
    for path in copies:
        if sha(path) != NAMED_SHA or not compare_bytes(copies[0], path):
            raise ValueError("Claimed ZIP reproduction is not byte-identical")
    diagnostics = [Path(r"C:\ag-mvp-f6-20260911\deterministic-diagnostic-01") / name for name in
                   ("NON-ADMITTED-experimental-diagnostic.zip", "NON-ADMITTED-independent-recreation.zip")]
    if not compare_bytes(*diagnostics):
        raise ValueError("Diagnostic ZIP copies differ")
    curl = ROOT / "named ZIP standalone curl baseline"
    curl_observation = json.loads((curl / "observation.json").read_text())
    curl_root = next(p for p in curl_observation["processes"] if p["pid"] == curl_observation["parent_pid"])
    if curl_observation["parent_raw_exit"] != 77:
        raise ValueError("Recorded standalone curl failure changed")
    if json.loads((ROOT / "shipped recreation baseline/observation.json").read_text())["parent_raw_exit"] != 0:
        raise ValueError("Actual shipped recreation failed")
    curl_tls = [m for m in curl_observation["module_snapshots"]
                if Path(m["path"]).name.lower() in ("libcurl-4.dll", "libssl-3-arm64.dll", "libcrypto-3-arm64.dll")]
    artifacts = {
        "tls": ref(ROOT / "independent-tls-evidence-01.json"),
        "recreation": ref(ROOT / "recreation.json"),
        "standalone_curl": {"request": ref(curl / "request.json"), "output": ref(curl / "output.log"),
                           "observation": ref(curl / "observation.json"), "parent_raw_exit": 77,
                           "generation": curl_root, "sampled_tls": curl_tls},
    }
    drain = observe_drain()
    save(output / "drain.json", drain)
    findings = [
        {"id": "TLS-01", "severity": "blocking", "generations": ["candidate-01", "named ZIP"],
         "title": "Superseded OpenSSL bytes are shipped and actually loaded, without supersession disclosure",
         "evidence": artifacts["tls"],
         "details": "Both manifest-bound generations ship libssl819faa/libcrypto0d35d from256c archive, "
                    "which current provider v18 supersedes with02f2 under4c3a admission. Named ZIP README "
                    "does not identify this crypto supersession. Its successful HTTPS clone is not evidence "
                    "for the admitted replacement TLS stack."},
        {"id": "CA-01", "severity": "blocking-for-candidate01", "generations": ["candidate-01"],
         "title": "Candidate-01 HTTPS clone fails after relocation despite bundled CA file",
         "evidence": artifacts["tls"],
         "details": "Raw128: compiled libcurl /mingwarm64/etc/ssl/certs/ca-bundle.crt becomes "
                    "C:/mingwarm64/... instead of the extracted bundle. Active shipped Git config has no "
                    "sslCAInfo. No verifier workaround applied. Named ZIP has its own working %(prefix) config."},
        {"id": "CA-02", "severity": "shipped-tool-failure", "generations": ["named ZIP"],
         "title": "Standalone shipped curl HTTPS still fails with the compiled absolute CA default",
         "evidence": artifacts["standalone_curl"],
         "details": "curl.exe HTTPS HEAD raw77; the Git-specific prefix-relative config does not configure "
                    "curl CLI. This is distinct from the successful named-ZIP Git clone. No CA repair applied."},
        {"id": "LABEL-01", "severity": "disclosure-risk", "generations": ["candidate-01"],
         "title": "Candidate-01 tree does not carry its non-admission or limitation metadata inside the tree",
         "details": "Only sibling disposition/manifest state NON-ADMITTED and publication false. A copied "
                    "candidate tree loses those sibling labels. It is not a self-describing distributable artifact."},
        {"id": "AUTH-01", "severity": "historical-authorization-superseded", "generations": ["named ZIP"],
         "title": "Historical detached receipt authorizes publication while current coordinator denies it",
         "details": "Preserve historical receipt verbatim. Current coordinator has requested an additive "
                    "named-ZIP-specific superseding disposition from the producer. Candidate01 disposition "
                    "does not apply to the named ZIP; verifier performs no producer-side correction."},
    ]
    corrected_case = ROOT / "candidate-01 baseline/documented-launcher-correct-CMD-transport/observation.json"
    if json.loads(corrected_case.read_text())["parent_raw_exit"] != 0:
        raise ValueError("Correct CMD transport did not pass")
    scripts = {}
    for path in Path(__file__).parent.iterdir():
        if path.suffix == ".py":
            shutil.copyfile(path, output / path.name)
            scripts[path.name] = ref(output / path.name)
    current = {
        "schema": 1, "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "status": "MIXED RESULTS; current provider admission NOT satisfied",
        "independence": "Verifier built no Git/Bash/HTTPS component in either audited generation; all Tcl/Tk "
                        "functionality excluded conservatively under coordinator's conflict-of-interest ruling",
        "generations": generation_records, "findings": findings, "evidence": artifacts,
        "reproduction": {"actual_all_five_named_zip_bytes_equal": True, "copies": reproduction,
                         "diagnostic_pair_bytes_equal": True, "diagnostic_pair": [ref(p) for p in diagnostics],
                         "scope": "Actual fresh moved shipped-recipe archive repackaging, not rebuilding packages"},
        "positive_scopes": [
            "Both generations' local Git init/add/commit/log/status/grep/fsck, real hook and bare clone succeeded",
            "Correct raw CMD transport runs the documented console entry; no interactive PTY/job-control claim",
            "Named ZIP public HTTPS clone succeeds without artifact repair and checks out7fd1a60b01f91b314f59955a4e4d4e80d8edf11d",
            "Observed dynamic sh/git-upload-pack/git-remote-https helpers came from the respective extracted root",
        ],
        "harness_failures_preserved": [
            {"record": ref(ROOT / "candidate-01 baseline/documented-launcher/observation.json"),
             "cause": "Verifier used CRT quoting for nested CMD /c; raw1 onlycmd created. Corrected raw Windows "
                      "command line, no candidate/env changes; retry passed.",
             "corrected": ref(corrected_case)},
            {"record": ref(ROOT / "named ZIP baseline/local-bare-clone/observation.json"),
             "cause": "Verifier QueryFullProcessImageName WinError31 on short-lived child; attempt interrupted "
                      "by job cleanup and explicitly observer-incomplete. Retry records metadata failure and "
                      "retains raw status rather than inventing identity; fresh-destination clone passed."},
        ],
        "environment_assistance": "All actual values logged per request and environment-policy. System32-only "
                                  "baselinePATH, fresh privateHOME/USERPROFILE/TMP/TEMP, GIT_CONFIG_GLOBAL=NUL "
                                  "and GIT_TERMINAL_PROMPT=0 for user-config/credential isolation. Original OS "
                                  "SystemRoot/WINDIR/COMSPEC/PATHEXT/PROGRAMDATA retained. Commit identity "
                                  "and pack.threads=1 supplied per command. NO CA, exec-path or artifact fixes. "
                                  "Shipped launcher sets its own documentedPATH; that is artifact behavior, not verifier repair.",
        "limitations": [
            "No new admitted-OpenSSL replacement candidate was provided in this run; follow-up needed",
            "Ordinary module sampling is incomplete for short-lived DLL loads; no universal dynamic closure claim",
            "No independent SSH authentication/service, GUI/Tk, interactive PTY/editor/pager or Perl replay",
            "Embedded debug/source/test-data strings are not counted as operational defects",
            "Named ZIP current publication/admission remains denied regardless of historical receipt or byte determinism",
        ],
        "verifier_scripts": scripts, "producer_writes": False,
        "new_grant": 3, "drain": ref(output / "drain.json"),
    }
    save(output / "report.json", current)
    print(json.dumps({"report": ref(output / "report.json"), "findings": len(findings)}, indent=2))


if __name__ == "__main__":
    main()
