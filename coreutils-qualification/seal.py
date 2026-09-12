"""Seal a candid limited-projection handoff; admission belongs to the intake owner."""

import io
import json
from pathlib import Path
import unittest

from evidence import check_package, check_positive
from exercise import memory_available
from qualify import ROOT, CORE_NAMES, EXTRA_NAMES, RUNTIME_SHA, copy, digest, load, write


def main():
    inputs = load(ROOT / "inputs.json")
    packages = [load(ROOT / "package/candidate.json"), *load(ROOT / "extra-candidates.json")]
    eligible = packages[0]["commands"] + EXTRA_NAMES
    cases, coverage = [], []
    for name in eligible:
        receipts = []
        for root, suffix in (("private", "03"), ("moved", "01")):
            label = f"{root}-{name}-{suffix}"
            record = check_positive(label)
            receipts.append({"path": str(ROOT / "cases" / label / "result.json"),
                             "sha256": digest(ROOT / "cases" / label / "result.json"),
                             "raw_exits": record["raw_generation_exits"]})
        coverage.append({"utility": name, "status": "limited-positive-907-both-roots",
                         "full_upstream_package_qualified": False,
                         "locale_scope": "C", "receipts": receipts})
    for name in ("chmod", "stty", "false"):
        path = ROOT / "cases" / f"private-{name}-03/result.json"
        record = load(path)
        coverage.append({"utility": name, "status": "withheld-from-positive-projection",
                         "receipt": str(path), "sha256": digest(path),
                         "raw_exits": record["raw_generation_exits"],
                         "stdout": record["stdout"], "stderr": record["stderr"], "checks": record["checks"]})
    for package in packages:
        check_package(package)
    required_closure = load(ROOT / "closure-04-required.json")
    if not required_closure["complete"] or required_closure["failures"]:
        raise RuntimeError("Required loader closure is unresolved")
    identities = {}
    for path, expected in inputs["locks"].items():
        after = digest(path)
        if after != expected:
            raise RuntimeError(f"Locked input changed: {path}")
        identities[path] = {"before": expected, "after": after}
    for row in inputs["copies"]:
        if digest(row["source"]) != row["before"] or digest(row["copy"]) != row["copied"]:
            raise RuntimeError(f"Candidate/source bytes changed: {row['source']}")
        identities[row["source"]] = {"before": row["before"], "after": digest(row["source"])}
        identities[row["copy"]] = {"before": row["copied"], "after": digest(row["copy"])}
    moved = load(ROOT / "moved-inputs.json")
    for row in moved["dependency_copies"]:
        if digest(row["source"]) != row["before"] or digest(row["copy"]) != row["copied"]:
            raise RuntimeError("Moved runtime dependency changed")
        identities[row["copy"]] = {"before": row["copied"], "after": digest(row["copy"])}
    for relative, row in moved["extracted_inventory"].items():
        if digest(ROOT / "moved" / relative) != row["sha256"]:
            raise RuntimeError("Moved archive readback changed")
    for row in required_closure["images"]:
        if digest(row["path"]) != row["sha256"]:
            raise RuntimeError("A dependency changed since the closure scan")
        identities[row["path"]] = {"before": row["sha256"], "after": digest(row["path"])}
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern="test_evidence.py")
    tested = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    with (ROOT / "evidence-tests.log").open("x", encoding="utf-8") as stream:
        stream.write(output.getvalue())
    if not tested.wasSuccessful():
        raise RuntimeError("Final evidence invariant tests failed")
    observed = created = 0
    raw_failures = []
    minimum_memory = memory_available()
    for path in sorted((ROOT / "cases").glob("*/result.json")):
        record = load(path)
        native = load(path.parent / "native-job.json")
        if record["launch"]["timed_out"] or record["launch"]["active_at_boundary"] != 0:
            raise RuntimeError(f"Owned job not drained: {path}")
        created += native["created_processes"]
        observed += native["observed_processes"]
        minimum_memory = min(minimum_memory, record["free_before"], record["free_after"])
        row = {"path": str(path), "sha256": digest(path), "utility": record["utility"],
               "status": record["status"], "raw_exits": record["raw_generation_exits"],
               "complete_strict_observation": record["complete_observation"],
               "mapped_failure_count": len(record["mapped_failures"]),
               "failed_checks": [check["check"] for check in record["checks"] if not check["passed"]]}
        cases.append(row)
        if record["status"] == "failed":
            raw_failures.append(row)
    handoff = ROOT / "handoff"
    handoff.mkdir(exist_ok=False)
    source_copies = []
    for source in sorted(Path(__file__).parent.iterdir()):
        if source.suffix in (".py", ".c"):
            copy(source, handoff / source.name, digest(source), source_copies, "qualification-recipe")
    write(ROOT / "qualification-sources.json", source_copies)
    write(ROOT / "identities-after.json", {"schema": 1, "all_verified": True, "files": identities})
    ownership = {}
    for package in packages:
        for path, row in load(package["ownership"]).items():
            if path in ownership:
                raise RuntimeError("Package file ownership collision")
            ownership[path] = {"projection": package["package_name"], **row}
    write(ROOT / "file-ownership.json", ownership)
    result = {
        "schema": 1, "status": "limited-MVP-projection-candidate-full-provider-blocked",
        "admitted": False, "admission_owner": "a2dd0a44-30ad-4164-89bb-f2d7aaa0e5e5",
        "assembly_owner": "f6ea7713-2cec-41d5-b3f9-b4373e60fa33",
        "requester": "ece7fd0d-2da8-4291-9297-7df1a6f3b078",
        "required": {"coreutils": CORE_NAMES, "other_packages": EXTRA_NAMES, "present": 40, "missing": inputs["missing"]},
        "eligible_projection": {"coreutils_commands": packages[0]["commands"], "extra_commands": EXTRA_NAMES,
                                "positive_names": 37, "both_original_and_moved_root": True,
                                "full_coreutils_provides": False, "withheld_names": ["chmod", "stty", "false"]},
        "packages": packages,
        "file_ownership": {"path": str(ROOT / "file-ownership.json"), "sha256": digest(ROOT / "file-ownership.json")},
        "runtime": {"sha256": RUNTIME_SHA, "configuration": "Private fstab noacl and MSYS=winsymlinks:sys; LC_ALL=C",
                    "PATH": ["EXACT_PRIVATE_ROOT\\usr\\bin", "C:\\Windows\\System32"],
                    "loaded_module_evidence": "Actual CREATE_PROCESS/LOAD_DLL file-handle hashes and generation-bound raw exits for every accepted control"},
        "architecture": {"required_programs": 40, "machine": "0xAA64", "package_PEs": 37,
                         "x64_or_bootstrap_PEs_in_packages": 0, "byte_changes_to_candidate_utilities": 0},
        "required_closure": {"path": str(ROOT / "closure-04-required.json"),
                             "sha256": digest(ROOT / "closure-04-required.json"),
                             "images": len(required_closure["images"]), "failures": 0,
                             "scope": "All private normal/delay imports and eager System32 dependencies/forwarded symbols; includes non-shipping harness PE",
                             "deferred_OS_imports": len(required_closure["deferred_system_imports"])},
        "expanded_OS_scan": {"path": str(ROOT / "closure-02.json"), "sha256": digest(ROOT / "closure-02.json"),
                             "status": "not-universally-resolved", "failures": len(load(ROOT / "closure-02.json")["failures"]),
                             "scope": "Optional Windows feature delay imports and their descendant graph; not represented as resolved"},
        "source_provenance": {"recipes": str(ROOT / "provenance/recipes.json"),
                              "recipes_sha256": digest(ROOT / "provenance/recipes.json"),
                              "source_inventory": str(ROOT / "coreutils-source-inventory.json"),
                              "source_inventory_sha256": digest(ROOT / "coreutils-source-inventory.json"),
                              "complete_native13_compiler_inputs": False, "original_PKGBUILD_present": False,
                              "full_upstream_suite_completed": False},
        "limitations": [
            "Full Coreutils producer/admission remains blocked; historical suite terminated at48PASS/41FAIL/23SKIP/4ERROR.",
            "chmod600 returns raw0 but actualmode644 under suppliednoacl. Readonly-bit chmoda-w=>444 succeeds; chmod omitted from eligible package.",
            "false returns raw1 by design; failure is retained, not normalized or included in positive package claims.",
            "stty nonTTY returnsraw1. RealownedPTY sttysize returns24 80/raw0, but ConPTY creates conhostraw109 and external ProgramDataOpenConsoleProxy DLL; strictwholecapture fails and noPTY/proxy is shipped.",
            "find/xargs/sed contain an old compiled private NLS localedir. Their separate projections are C-locale positive operations only, not translated-NLS/locatedb/full-package qualification.",
            "Only named commands, not all107 producerstageCoreutils executables, are proposed for MVP.",
        ],
        "progression": [
            {"phase": "prior-producer-suite", **inputs["prior_suite"]},
            {"phase": "initial-harness-01", "status": "failed-retained", "reason": "Collector starts in debug output dir, not fixture parent; extended Win32 paths also miscompared. Raw failures preserved."},
            {"phase": "harness-02", "status": "partly-failed-retained", "reason": "Working directory corrected; repeated same-hash runtime mappings incorrectly demanded cardinality1. No program-status normalization."},
            {"phase": "current-03", "status": "limited-positive-with-explicit-holdouts", "reason": "Exact paths and every repeated mapped runtime identity checked; genuine mode/TTY/nonzero failures retained."},
            {"phase": "moved-01", "status": "all37eligible-named-controls-and-pipeline-positive", "reason": "Core archive extracted; exact extra-command bytes copied and later archive-readback-matched; all dependencies mapped only from movedroot/System32."},
        ],
        "coverage": coverage, "all_case_progression": cases, "retained_failed_cases": raw_failures,
        "identities_after": {"path": str(ROOT / "identities-after.json"), "sha256": digest(ROOT / "identities-after.json")},
        "qualification_sources": {"path": str(ROOT / "qualification-sources.json"), "sha256": digest(ROOT / "qualification-sources.json")},
        "validation": {"evidence_invariants": tested.testsRun, "failures": len(tested.failures), "errors": len(tested.errors),
                       "log": str(ROOT / "evidence-tests.log"), "log_sha256": digest(ROOT / "evidence-tests.log")},
        "drain": {"case_jobs": len(cases), "created_processes": created, "observed_processes": observed,
                  "all_case_jobs_drained": True, "max_concurrent_jobs_used": 1, "granted_ceiling": 2,
                  "minimum_free_bytes": minimum_memory,
                  "one_non_shipping_PTY_fixture_build": str(ROOT / "pty-build/result.json")},
        "no_runtime_make": True, "runtime_or_compiler_modified": False, "no_status_normalization": True,
        "old_receipts_modified": False, "observer_implementation_ownership": "0af73d1b-9b87-4723-8e25-1e32f44a090c",
    }
    write(ROOT / "result.json", result)
    print(json.dumps({"result": str(ROOT / "result.json"), "sha256": digest(ROOT / "result.json"),
                      "positive_names": 37, "core_commands": 34, "missing": [],
                      "withheld": ["chmod", "stty", "false"], "case_jobs": len(cases),
                      "created": created, "observed": observed, "tests": tested.testsRun,
                      "ownership_sha256": digest(ROOT / "file-ownership.json")}))


if __name__ == "__main__":
    main()
