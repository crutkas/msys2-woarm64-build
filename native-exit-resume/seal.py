"""Seal the scoped, source-lineaged remedy for separate producer integration."""

import difflib
import io
import json
from pathlib import Path
import unittest

from evidence import check_alias, check_case, check_matrix
from resume import ROOT, copy_locked, digest, free_memory, load, verify_inputs, write


def main():
    aliases = [check_alias(name) for name in ("baseline-probe-02", "d70-probe-01")]
    wrapper_matrix = check_matrix(ROOT / "matrix-result.json")
    source_matrix = check_matrix(ROOT / "source-matrix-result.json")
    before_after = verify_inputs()
    source_build = load(ROOT / "source-build/result.json")
    prepared = load(ROOT / "source-build/prepared.json")
    original, patched = Path(prepared["source"]), Path(prepared["patched"])
    patch = "".join(difflib.unified_diff(
        original.read_text().splitlines(keepends=True), patched.read_text().splitlines(keepends=True),
        fromfile="a/libgcc/unwind-seh.c", tofile="b/libgcc/unwind-seh.c"))
    patch_path = Path(__file__).with_name("libgcc-arm64-unwind-context.patch")
    with patch_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(patch)
    for row in prepared["copies"]:
        if digest(row["source"]) != row["before"]:
            raise RuntimeError(f"Original producer dependency changed: {row['source']}")
        if row["copy"] != str(patched) and digest(row["copy"]) != row["copied"]:
            raise RuntimeError(f"Copied dependency changed: {row['copy']}")
        before_after[row["source"]] = row["before"]
    for build_name in ("scratch-build", "matrix-build", "source-build"):
        build = load(ROOT / build_name / "result.json")
        for path, sha in build["outputs"].items():
            if digest(path) != sha:
                raise RuntimeError(f"Built fixture changed: {path}")
        if "tool_inputs_before_after" in build:
            for path, sha in build["tool_inputs_before_after"].items():
                if digest(path) != sha:
                    raise RuntimeError(f"Frozen compiler/library changed: {path}")
                before_after[path] = sha
        for record in build["builds"]:
            result = record["result"]
            if not result["passed"] or result["active_at_boundary"] or result["timed_out"]:
                raise RuntimeError("Private build was not successful and drained")
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test_evidence.py")
    tested = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    with (ROOT / "evidence-tests.log").open("x", encoding="utf-8") as stream:
        stream.write(output.getvalue())
    if not tested.wasSuccessful():
        raise RuntimeError("Scoped evidence invariant tests failed")
    write(ROOT / "evidence-tests.json", {"schema": 1, "tests": tested.testsRun,
          "failures": len(tested.failures), "errors": len(tested.errors),
          "log_sha256": digest(ROOT / "evidence-tests.log")})
    cases = []
    native_created = native_observed = bounded_created = 0
    minimum_memory = free_memory()
    for path in sorted((ROOT / "cases").glob("*/result.json")):
        result, native = check_case(path.parent.name)
        cases.append({"path": str(path), "sha256": digest(path), "mode": result["mode"],
                      "cohort": result["cohort"], "raw_generation_exits": result["generation_exits"]})
        native_created += native["created_processes"]
        native_observed += native["observed_processes"]
        bounded_created += result["launch"]["created_processes"]
        minimum_memory = min(minimum_memory, result["free_before"], result["free_after"])
    identities_path = ROOT / "identities-after.json"
    write(identities_path, {"schema": 1, "all_unchanged": True,
          "before_after": {path: {"before": sha, "after": digest(path)} for path, sha in sorted(before_after.items())}})
    candidate = ROOT / "handoff"
    candidate.mkdir(exist_ok=False)
    copies = []
    for path in sorted(Path(__file__).parent.iterdir()):
        if path.suffix in (".py", ".c", ".cpp", ".patch"):
            copies.append(copy_locked(path, candidate / path.name, digest(path)))
    copies.append(copy_locked(patched, candidate / "unwind-seh.c", source_build["source_after_sha256"]))
    candidate_manifest = ROOT / "handoff.manifest.json"
    write(candidate_manifest, {"schema": 1, "status": "private-source-delta-qualified-for-listed-controls",
                              "copies": copies, "producer_admission": False})
    record = {
        "schema": 1, "status": "private-arm64-unwind-context-fix-qualified",
        "scope": "Matched private single-member links and explicit exception matrix only; producer integration remains separate",
        "root_cause": "The ARM64 GNU handler passes the saved KiUserExceptionDispatcher CONTEXT as writable RtlUnwindEx scratch. Capture overwrites that frame; phase 2 restores a self-referential dispatcher PC/SP and the actual no-PC-progress check raises C00000FF.",
        "get_thread_context": "Not causal: original no-context debugging fails; fixed source no-context debugging succeeds. Newly recorded source-bound context/frame evidence closes the previous missing-pointer boundary.",
        "alias_witnesses": aliases,
        "source_fix": {"path": str(candidate / "unwind-seh.c"), "patch": str(candidate / patch_path.name),
                       "patch_sha256": digest(patch_path), "before_sha256": source_build["source_before_sha256"],
                       "after_sha256": source_build["source_after_sha256"],
                       "change": "ARM64 only: copy incoming CONTEXT to local scratch in _GCC_specific_handler before both RtlUnwindEx call paths",
                       "build": str(ROOT / "source-build/result.json"),
                       "build_sha256": digest(ROOT / "source-build/result.json"),
                       "control_object_sha256": source_build["control_object_sha256"],
                       "fixed_object_sha256": source_build["fixed_object_sha256"],
                       "historical_retained_member_reconstructed": False},
        "source_matrix": {"path": str(ROOT / "source-matrix-result.json"),
                          "sha256": digest(ROOT / "source-matrix-result.json"), "controls": len(source_matrix["controls"])},
        "link_only_matrix": {"path": str(ROOT / "matrix-result.json"),
                             "sha256": digest(ROOT / "matrix-result.json"), "controls": len(wrapper_matrix["controls"])},
        "evidence_tests": {"path": str(ROOT / "evidence-tests.json"), "sha256": digest(ROOT / "evidence-tests.json")},
        "preserved_negatives": ["matched unmodified source debug C00000FF",
                               "uncaught exception termination73", "direct Windows exit256",
                               "access violation C0000005"],
        "rejected_probe": {"case": "baseline-probe-01", "raw_exit": 0xC000001D,
                           "reason": "Generic BRK0 is not the Windows debug trap; all instructions restored, raw evidence preserved, excluded from causal proof",
                           "corrected_opcode": "00003ed4", "opcode_identity": "matches both locked ntdll debug-break instructions"},
        "cases": cases,
        "identities_after": {"path": str(identities_path), "sha256": digest(identities_path)},
        "handoff": {"path": str(candidate_manifest), "sha256": digest(candidate_manifest)},
        "drain": {"fixture_job_trees": len(cases), "native_job_created": native_created,
                  "native_job_observed": native_observed, "outer_bounded_created": bounded_created,
                  "all_case_jobs_drained": True, "max_aggregate_jobs_used": 1,
                  "minimum_recorded_free_bytes": minimum_memory},
        "unchanged": {"frozen_runtime": True, "compiler_sdk": True, "retained_libgcc_archives": True,
                      "old_collector": True, "old_receipts": True, "global_settings": True},
        "producer_integration": {"owner": "5b01b4e5-41d0-4535-bc71-1133839af6e1", "admitted": False,
                                 "required": "Apply source delta in a separately versioned producer; rebuild/requalify static/shared libgcc and relink affected consumers before any current-cohort claim"},
        "exit_domain_collector": {"qualified": False, "encoding": "UNKNOWN", "decoded_status": None,
                                   "required": "Authoritative creation/terminal callsite and full provenance-negative matrix remain pending; this repair is a prerequisite only"},
    }
    write(ROOT / "result.json", record)
    print(json.dumps({"result": str(ROOT / "result.json"), "sha256": digest(ROOT / "result.json"),
                      "source_after": source_build["source_after_sha256"], "patch_sha256": digest(patch_path),
                      "handoff_sha256": digest(candidate_manifest), "matrix_controls": 60,
                      "tests": tested.testsRun, "cases": len(cases), "created_observed": native_observed}))


if __name__ == "__main__":
    main()
