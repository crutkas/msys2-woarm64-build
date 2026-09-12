"""Seal a blocked-capability result without admitting or decoding any process."""

import json
from pathlib import Path
import shutil

from prepare import ROOT, digest, write_json


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_raw_record(record):
    for key, limit in (("pid", 2 ** 32), ("created", 2 ** 64), ("raw_exit", 2 ** 32)):
        value = record[key]
        if type(value) is not int or not 0 <= value < limit or (key != "raw_exit" and value == 0):
            raise ValueError(f"Invalid lossless {key}")
    if record["encoding"] != "UNKNOWN" or record["role"] != "UNKNOWN":
        raise ValueError("No exit domain or role is qualified by this experiment")
    if record["decoded_status"] is not None or record["terminal_evidence"] is not None:
        raise ValueError("The terminal provenance gate was not reached")
    if record.get("event_matches_handle_exit") is not True:
        raise ValueError("Debug event and retained generation handle must agree")
    return record["raw_exit"]


def main():
    pairs = []
    for path in sorted((ROOT / "cases").glob("*-parity.json")):
        pair = load(path)
        pairs.append({"path": str(path), "sha256": digest(path), "name": pair["name"],
                      "exit_parity": pair["behavioral_exit_parity"],
                      "ordinary": pair["ordinary"]["identities"], "debug": pair["debug"]["identities"]})
    successful_controls = [row for row in pairs if row["path"].endswith("-r2-parity.json")]
    if len(successful_controls) != 18 or not all(row["exit_parity"] for row in successful_controls):
        raise RuntimeError("The 18 fresh serial parity controls are incomplete")
    witnesses = []
    for name in ("cpp-exception-r3", "cpp-exception-r4", "cpp-exception-no-context",
                 "cpp-fork-exception-r4", "cpp-exception-r5", "cpp-exception-no-context-r5"):
        pair_path = ROOT / "cases" / f"{name}-parity.json"
        pair = load(pair_path)
        debug_path = ROOT / "cases" / f"{name}-debug" / "debug/result.json"
        ordinary_log = ROOT / "cases" / f"{name}-ordinary" / "observer.log"
        debug = load(debug_path)
        if (pair["behavioral_exit_parity"] or not pair["ordinary"]["full_observation"]
                or not pair["debug"]["full_observation"] or debug["error"] is not None
                or pair["ordinary"]["raw_exits"] != ([0, 0] if name.startswith("cpp-fork") else [0])
                or 0xC00000FF not in pair["debug"]["raw_exits"]
                or "caught DbException with exactly one destructor" not in ordinary_log.read_text()):
            raise RuntimeError(f"Incomplete semantic divergence witness: {name}")
        for record in debug["processes"]:
            validate_raw_record(record)
        if debug["memory_writes"] or debug["register_writes"]:
            raise RuntimeError("This blocker must be reproduced before instrumentation writes")
        faults = [row for row in debug["events"] if row["event"] == 1
                  and row["exception"]["code"] in (0x20474343, 0xC00000FF)]
        if (not any(row["exception"]["code"] == 0x20474343 for row in faults)
                or not any(row["exception"]["code"] == 0xC00000FF
                           and not row["exception"]["first_chance"] for row in faults)
                or any(row["continue_status"] != 0x80010001 for row in faults)):
            raise RuntimeError("Application exceptions must be forwarded rather than swallowed")
        witnesses.append({"name": name, "pair": str(pair_path), "pair_sha256": digest(pair_path),
                          "debug_receipt": str(debug_path), "debug_sha256": digest(debug_path),
                          "ordinary_stdout_sha256": digest(ordinary_log),
                          "fault_events": faults,
                          "ordinary_identities": pair["ordinary"]["identities"],
                          "debug_identities": pair["debug"]["identities"]})
        if name.endswith("-r5"):
            identities = [pair[mode]["fixture_identity"] for mode in ("ordinary", "debug")]
            hashes = {identity[field] for identity in identities for field in ("before", "after")}
            if hashes != {debug["processes"][0]["image"]["mapped_file_sha256"]}:
                raise RuntimeError("Final same-binary witness lacks before/after/mapped-file equality")
    no_context = load(ROOT / "cases/cpp-exception-no-context-debug/debug/result.json")
    if no_context["context_reads_enabled"]:
        raise RuntimeError("No-context isolation control unexpectedly read context")
    legacy_path = ROOT / "legacy-debug-only/capture/result.json"
    legacy = load(legacy_path)
    if legacy["exit_code"] != 0xC00000FF or legacy["timed_out"] or legacy["exception_limit_reached"]:
        raise RuntimeError("Sealed independent DEBUG_ONLY_THIS_PROCESS witness incomplete")

    inputs = load(ROOT / "inputs.json")
    checked = {}
    expected_paths = dict(inputs["locks"])
    expected_paths.update(inputs["tool_inputs_before"])
    for row in inputs["copies"]:
        expected_paths[row["source"]] = row["before"]
        expected_paths[row["copy"]] = row["copied"]
    expected_paths.update({
        r"C:\ag-tcl-e138-01\expected-negative-01\native-job.json":
            "62325232f725db19cbedf4f28a7451da116f938866f46da77da73699c439f134",
        r"C:\ag-sqlite-e138-01\configure-06\native-job.json":
            "6fbea7071fe0401f7fa8e603ae2f1660565acf8d056b88476f129fe4572b272c",
    })
    for path, before in sorted(expected_paths.items()):
        after = digest(path)
        if after != before:
            raise RuntimeError(f"Input or sealed helper changed: {path}")
        checked[path] = {"before": before, "after": after}
    after_path = ROOT / "identities-after.json"
    write_json(after_path, {"schema": 1, "all_unchanged": True, "files": checked})
    builds = load(ROOT / "build/result.json")
    for path, before in builds["outputs"].items():
        if digest(path) != before:
            raise RuntimeError(f"C fixture changed: {path}")
    fixture = ROOT / "runtime/usr/bin/exception-fixture.exe"
    if any(p["image"]["mapped_file_sha256"] != digest(fixture)
           for witness in witnesses for p in load(witness["debug_receipt"])["processes"]):
        raise RuntimeError("Exception witness did not load the exact same built fixture")
    raw_receipts = sorted((ROOT / "cases").glob("*/native-job.json")) + [ROOT / "legacy-debug-only/native-job.json"]
    processes = 0
    for path in raw_receipts:
        record = load(path)
        if (not record["observation_count_matches"] or record["timed_out"] or record["unobserved_process_ids"]
                or record["created_processes"] != record["observed_processes"]):
            raise RuntimeError(f"An owned tree lacks complete drain evidence: {path}")
        processes += record["created_processes"]
    abi = load(ROOT / "windows-abi.json")
    parser_lock = {
        "schema": 1, "runtime_sha256": "1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16",
        "source_manifest_sha256": "577aeab7449171c0edb092ccb019a8ee6b96c492c518e9395c396a73bbd14737",
        "windows_abi": abi, "windows_abi_receipt": str(ROOT / "abi/run.json"),
        "windows_abi_receipt_sha256": digest(ROOT / "abi/run.json"),
        "child_info": {"intro_source_value": "0xaf00fa64", "magic_source_value": "0xe4ccec6c",
                       "sizes": None, "offsets": None, "parser_enabled": False},
        "peb_runtime_info_bridge": {"qualified": False, "offsets": None, "parser_enabled": False},
        "pinfo": {"sizes": None, "offsets": None, "parser_enabled": False},
        "terminal_callsite": {"symbol": "_ZN5pinfo4exitEj", "symbol_table_section": 1,
                             "symbol_table_section_offset": "0x5ab84",
                             "symbol_table_sha256": digest(ROOT / "inspect/output.log"),
                             "rva": None, "instrumented": False, "qualified": False},
        "generation_binding": {"process": "duplicated CREATE_PROCESS_DEBUG_EVENT handle plus GetProcessTimes uint64",
                               "thread": "duplicated CREATE_[PROCESS/THREAD]_DEBUG_EVENT handle plus GetThreadTimes uint64",
                               "parent": "OS PPID and currently held generation retained, NOT creator-callsite-qualified",
                               "handle_lifetime": "held through EXIT_PROCESS_DEBUG_EVENT and GetExitCodeProcess, then closed"},
        "not_authoritative": ["image names", "tree shape", "raw divisibility", "strace text",
                              "startup record alone", "late pinfo reads", "matching repeated shared-memory reads"],
        "decision": "All domain/role/status decoding disabled. Coherent terminal ABI gate blocked by debug-launch semantic divergence.",
    }
    parser_path = ROOT / "parser-lock.json"
    write_json(parser_path, parser_lock)
    candidate = ROOT / "candidate"
    candidate.mkdir(exist_ok=False)
    candidate_files = []
    for path in sorted(Path(__file__).parent.iterdir()):
        if path.suffix not in (".py", ".c", ".cpp"):
            continue
        before = digest(path)
        target = candidate / path.name
        with path.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        copied, after = digest(target), digest(path)
        if before != copied or before != after:
            raise RuntimeError("Candidate source changed while sealing")
        candidate_files.append({"source": str(path), "copy": str(target),
                                "before": before, "copied": copied, "after": after})
    candidate_manifest = ROOT / "candidate.manifest.json"
    write_json(candidate_manifest, {"schema": 1, "status": "blocked-experimental-candidate",
                                   "copies": candidate_files, "qualified": False})
    pending = [
        "Creation STARTUPINFO binary RuntimeInfo OS/ARM64 bridge and actual 1bdf child_info layout",
        "Exact creator HANDLE/generation including fork duplicated parent HANDLE",
        "Coherent pinfo::exit decision with outgoing DWORD and shared exec/pinfo provenance",
        "Ordinary spawn masquerading as exec",
        "Wrong/reused parent and target generations",
        "Absent/late/reused startup and pinfo; shared-section reuse/ABA",
        "Ambiguous children and forged status/relay records",
        "Real loader-induced fork failure (only exact raw marker preservation exercised here)",
        "Instrumentation restore/semantic parity matrix (no breakpoint or context writes attempted)",
    ]
    write_json(ROOT / "result.json", {
        "schema": 1, "status": "BLOCKED-debugger-launch-semantic-divergence",
        "experimental": True, "qualified": False, "promoted": False, "exit_decoding_enabled": False,
        "provider_changes": False, "old_receipts_relabelled": False, "runtime_or_compiler_changes": False,
        "blocker": {"capability": "Semantics-preserving debugger observation of this MSYS ARM64 exception cohort",
                    "ordinary": "Same fresh executable catches DbException, unwinds one destructor, raw0",
                    "debug": "DEBUG_PROCESS and sealed DEBUG_ONLY_THIS_PROCESS reach actual raw0xC00000FF",
                    "isolated": "Still fails with GetThreadContext disabled and no memory/register writes",
                    "root_cause": "Not diagnosed; no permission to change runtime/compiler or override exceptions",
                    "consequence": "Cannot qualify debug/callsite collector for arbitrary native consumers under this immutable cohort"},
        "positive_exit_parity_controls": successful_controls, "semantic_failure_witnesses": witnesses,
        "independent_sealed_helper": {"path": str(legacy_path), "sha256": digest(legacy_path),
                                     "helper_sha256": "b5265ba881a53b1fa07e09dfb576058854f5380f8e17560e4baf0d28434b6be1"},
        "all_experiments": pairs, "unqualified_required_matrix_rows": pending,
        "parser_lock": {"path": str(parser_path), "sha256": digest(parser_path)},
        "candidate_source_copy": {"path": str(candidate_manifest), "sha256": digest(candidate_manifest)},
        "before_after_identities": {"path": str(after_path), "sha256": digest(after_path), "files": len(checked)},
        "prototype_sources": {str(path): digest(path) for path in sorted(Path(__file__).parent.iterdir())
                              if path.suffix in (".py", ".c", ".cpp")},
        "exception_fixture": {"path": str(fixture), "sha256": digest(fixture),
                              "build_receipt": str(ROOT / "cpp/result.json"), "build_sha256": digest(ROOT / "cpp/result.json")},
        "drain": {"native_job_receipts": len(raw_receipts), "created": processes, "observed": processes,
                  "missing": 0, "all_outer_jobs_returned": True, "active_owned_jobs": 0,
                  "enforcement": "sealed observer waits for active0; kill-on-close job and finally drain",
                  "concurrency_used": 1, "granted_cap": 2},
        "no_claim": "This is a concrete blocked capability, not a qualified exit-domain collector or package/provider admission.",
    })
    print(json.dumps({"result": str(ROOT / "result.json"), "sha256": digest(ROOT / "result.json"),
                      "positive_controls": len(successful_controls), "witnesses": len(witnesses),
                      "native_job_trees": len(raw_receipts), "created_observed": processes,
                      "input_identities_unchanged": len(checked)}))


if __name__ == "__main__":
    main()
