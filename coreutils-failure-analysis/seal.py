"""Seal exact grouped causes, failed replays, and remaining uncertainty."""

from collections import Counter
import io
import json
from pathlib import Path
import unittest

from inventory import ROOT, BUILD, SOURCE, PRODUCER, copy, digest, write


def load(path):
    return json.loads(Path(path).read_text())


def main():
    causes = load(ROOT / "causes.json")
    original = load(ROOT / "inventory.json")
    sources = []
    for relative in ("lib/progname.c", "src/remove.c", "src/stdbuf.c", "tests/lang-default"):
        copy(SOURCE / relative, ROOT / "mechanism-source" / relative, sources)
    copy(Path(r"C:\ag-e138920f\tc-cpp-guard-01\aarch64-pc-cygwin\include\dlfcn.h"),
         ROOT / "mechanism-source/dlfcn.h", sources)
    write(ROOT / "mechanism-sources.json", sources)
    before_after = {}
    for manifest_name in ("inventory.json", "replay-inputs.json", "support-layout-inputs.json", "api-diagnostic-inputs.json"):
        for row in load(ROOT / manifest_name)["copies"]:
            actual_source, actual_copy = digest(row["source"]), digest(row["copy"])
            if actual_source != row["before"] or actual_copy != row["copied"]:
                raise RuntimeError(f"Retained input changed: {row['source']}")
            before_after[row["source"]] = {"before": row["before"], "after": actual_source}
            before_after[row["copy"]] = {"before": row["copied"], "after": actual_copy}
    for line in (PRODUCER / "stage-coreutils.sha256").read_text().splitlines():
        sha, name = line.split(maxsplit=1)
        path = PRODUCER / "stage/coreutils" / name
        if digest(path) != sha:
            raise RuntimeError(f"Original Coreutils stage changed: {path}")
        before_after[str(path)] = {"before": sha, "after": digest(path)}
    write(ROOT / "identities-after.json", {"schema": 1, "all_unchanged": True, "files": before_after})
    primary = load(ROOT / "shell-batch-current-noacl.json")
    replace = {
        "tests/misc/help-version.sh": "complete-help-version-02",
        "tests/misc/help-version-getopt.sh": "complete-help-version-getopt-02",
        "tests/tail-2/inotify-hash-abuse2.sh": "complete-inotify-hash-abuse2-02",
    }
    final_replays = []
    for row in primary:
        path = ROOT / "runs" / replace[row["test"]] / "result.json" if row["test"] in replace else Path(row["case"]) / "result.json"
        replay = load(path)
        final_replays.append({"test": row["test"], "original_status": row["original_status"],
                              "path": str(path), "sha256": digest(path),
                              "test_shell_raw_exit": replay["semantic_test_shell_raw_exit"],
                              "observer_gate_passed": replay["observer_gate_passed"],
                              "timed_out": replay["native_job"]["timed_out"],
                              "coverage": [replay["native_job"]["observed_processes"], replay["native_job"]["created_processes"]]})
    summary = Counter(row["test_shell_raw_exit"] for row in final_replays)
    if summary != {0: 19, 1: 12, 1460: 1}:
        raise RuntimeError(f"Unexpected complete-shell replay totals: {summary}")
    acl = load(ROOT / "acl-batch-current-acl.json")
    previous = {row["test"]: row["test_shell_raw_exit"] for row in final_replays}
    acl_improved = [row["test"] for row in acl if row["test_shell_raw_exit"] == 0 and previous[row["test"]] == 1]
    acl_persisted = [row["test"] for row in acl if row["test_shell_raw_exit"] == 1]
    if len(acl_improved) != 5 or len(acl_persisted) != 7:
        raise RuntimeError("ACL differential counts changed")
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test_analysis.py")
    checked = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    with (ROOT / "validation.log").open("x", encoding="utf-8") as stream:
        stream.write(output.getvalue())
    if not checked.wasSuccessful():
        raise RuntimeError("Forensic accounting validation failed")
    runs = []
    created = observed = 0
    timeout_gaps = []
    for path in sorted((ROOT / "runs").glob("*/result.json")):
        record = load(path)
        native = record["native_job"]
        if record["outer"]["timed_out"] or record["outer"]["active_at_boundary"] != 0:
            raise RuntimeError(f"Outer owned tree did not drain: {path}")
        created += native["created_processes"]
        observed += native["observed_processes"]
        if native["timed_out"]:
            timeout_gaps.append({"run": path.parent.name, "raw_exit": record["semantic_test_shell_raw_exit"],
                                 "created": native["created_processes"], "observed": native["observed_processes"],
                                 "admissible_execution_evidence": False})
        elif (not native["observation_count_matches"] or native["unobserved_processes"] or native["unresolved_processes"]):
            raise RuntimeError(f"Unexpected incomplete non-timeout observation: {path}")
        runs.append({"path": str(path), "sha256": digest(path), "cohort": record["cohort"],
                     "test": record["test"], "test_shell_raw_exit": record["semantic_test_shell_raw_exit"],
                     "observer_gate_passed": record["observer_gate_passed"], "timed_out": native["timed_out"]})
    handoff = ROOT / "handoff"
    handoff.mkdir(exist_ok=False)
    tooling = []
    for path in sorted(Path(__file__).parent.iterdir()):
        if path.suffix in (".py", ".c"):
            copy(path, handoff / path.name, tooling)
    write(ROOT / "tooling.json", tooling)
    record = {
        "schema": 1, "status": "grouped-root-causes-with-explicit-unresolved-boundaries",
        "scope": "Exactly the retained41FAIL and4ERROR, not a new full Coreutils qualification",
        "original_totals": original["counts"], "original_full_suite_completed": False,
        "primary_group_counts": {row["id"]: row["counts"] for row in causes["groups"]},
        "groups": causes["groups"],
        "per_test_ledger": {"path": str(ROOT / "causes.json"), "sha256": digest(ROOT / "causes.json")},
        "diagnostic_diff_analysis": {"path": str(ROOT / "diagnostic-diff-analysis-v2.json"),
                                     "sha256": digest(ROOT / "diagnostic-diff-analysis-v2.json"),
                                     "not_an_output_normalization_or_test_verdict": True},
        "unchanged_shell_test_replays": {"tests": 32, "raw0": 19, "raw1": 12, "raw1460_bounded_incomplete": 1,
                                         "records": final_replays, "observer_gate_is_separate_from_test_semantics": True},
        "acl_control": {"tests": 13, "raw0": 6, "raw1": 7, "additional_original_failures_with_test_exit0": acl_improved,
                        "still_failing_with_acl": acl_persisted,
                        "scope": "Only a fresh private ACL-configured runtime view; not a shipped/global mount change"},
        "original41_followup_coverage": {
            "unchanged_test_script_exit0_in_coherent_or_acl_controls": 21,
            "unchanged_test_script_exit1_even_with_acl": 7,
            "unchanged_script_bounded_incomplete": 1,
            "Perl_scripts_not_fully_rerun": 12,
            "Perl_evidence_scope": "Complete retained logs/source plus native discriminating subcase replays; not claimed full script passes",
        },
        "genuine_semantic_gap": {
            "boundary": "MSYS/Windows POSIX permission behavior, reproduced below Coreutils",
            "evidence": str(ROOT / "runs/api-boundary-current-acl/result.json"),
            "observed": ["mode500/access(W_OK) denies butunlinkat(child) succeeds",
                         "open through mode600 parent succeeds whilechdir toparent denies"],
            "meaning": "Actual delete/traversal expectation failures, not seven tests reclassified as inapplicable",
        },
        "confirmed_setup_limits": {
            "RTLD_NEXT": "Target header lacks required symbol; original injected readdir helper fails to compile before rm assertions. ERROR99 retained, not SKIP/PASS.",
            "gzip": "No approved AA64 helper supplied; intake independently found only x64 copies. Fresh full help-version setup lacks gzip and the600s run remains incomplete. No bootstrap/fake fixture substituted.",
        },
        "unresolved_secondary_mechanisms": causes["unconfirmed_secondary_causes"],
        "hypotheses": {
            "message_catalog_or_translation_failures_evidenced": 0,
            "line_ending_only_failure_groups_evidenced": 0,
            "locale_reason": "Tests force LC_ALL=C (Perl also LANGUAGE/LANG=C); retained mismatches are paths/bytes/errno/status rather than catalog text.",
            "clangarm64_gettext": "Different provider/ABI from msys-intl-8.dll used by these AA64 MSYS candidates; cannot attribute its bindtextdomain defect to this suite.",
            "independent_coreutils_arithmetic_or_text_algorithm_defects_proven": 0,
            "not_proven": "No claim that every untested byte path or every full Coreutils test is correct",
        },
        "progression": [
            "Retained all48PASS41FAIL23SKIP4ERROR without relabelling.",
            "First3 fresh harness runs failed127 because Makefile-style lowercaseexports were not established inside the native shell; retained, fixed harness exports only.",
            "32unchanged shell tests: first17raw0/12raw1/3timeout; rerun2withlargerbounds reachedraw0, fullhelp stilltimeout.",
            "13unchanged permission tests withprivateACL:6raw0/7raw1 (5newimprovements overnoacl).",
            "Originalbaa runtime withnativeparent also passes diagnostic-dir-nonrecur, pwd-option,wc-proc, isolating parent/cohort fromruntimeupdate.",
            "Real original libstdbuf.dll initsconfiguredinstalledlocation removes125missinglibrarysubcase; wholehelp remainsunqualified.",
        ],
        "all_runs": runs, "rejected_timeout_observations": timeout_gaps,
        "drain": {"run_count": len(runs), "created": created, "observed": observed,
                  "coverage_gaps_retained": created - observed, "all_outer_job_trees_drained": True,
                  "max_aggregate_jobs_authorized": 3, "max_simultaneous_native_jobs_used": 2,
                  "test_only_api_fixture_build": str(ROOT / "api-build/result.json"),
                  "retained_workdirs": "KEEP=yes preserves real exp/out files for independent inspection"},
        "identities_after": {"path": str(ROOT / "identities-after.json"), "sha256": digest(ROOT / "identities-after.json")},
        "mechanism_sources": {"path": str(ROOT / "mechanism-sources.json"), "sha256": digest(ROOT / "mechanism-sources.json")},
        "tooling": {"path": str(ROOT / "tooling.json"), "sha256": digest(ROOT / "tooling.json")},
        "validation": {"checks": checked.testsRun, "failures": len(checked.failures), "errors": len(checked.errors),
                       "log_sha256": digest(ROOT / "validation.log")},
        "full_coreutils_admitted": False, "MVP_admission_changed": False, "old_receipts_modified": False,
        "binary_or_runtime_changes": False, "privilege_changes": False, "status_normalization": False,
    }
    write(ROOT / "result.json", record)
    print(json.dumps({"result": str(ROOT / "result.json"), "sha256": digest(ROOT / "result.json"),
                      "groups": record["primary_group_counts"], "raw_shell_counts": dict(summary),
                      "acl_improvements": len(acl_improved), "acl_persistent_failures": len(acl_persisted),
                      "runs": len(runs), "created": created, "observed": observed, "timeout_gaps": created - observed}))


if __name__ == "__main__":
    main()
