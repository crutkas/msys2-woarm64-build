"""Reconcile the final native Tcl package, current-runtime evidence, and resource drain for assembly."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import combined_runtime
from finalize import generation_state, reference
from qualify import ROOT, digest, import_tools, read_json, require, require_memory, write_json


def main():
    sources = import_tools()
    current = ROOT / "combined-20260911-package-01"
    receipt_path = current / "package-receipt.json"
    receipt = read_json(receipt_path)
    package = Path(receipt["package_root"])
    require(sources.inventory(package) == receipt["files"], "Package payload changed")
    require(len(receipt["files"]) == 1152 and len(receipt["pe"]) == 9,
            "Actual native Tcl package shape differs")
    require(digest(receipt["archive"]["path"]) == receipt["archive"]["sha256"],
            "Final archive changed")
    pe = {}
    for name, row in receipt["pe"].items():
        actual = combined_runtime.pe_record(package / name)
        require(actual == row, "Final packaged PE architecture/import/identity changed")
        pe[name] = actual
    for alias, row in receipt["aliases"].items():
        require(digest(package / alias) == digest(package / row["resolved_target"]) == row["sha256"],
                "Declared regular-copy alias differs")
    compatibility = read_json(receipt["tests"]["path"])
    require(len(compatibility["rows"]) == 35, "Expected two API and 33 selected core scopes")
    tests = compatibility["rows"]
    summary, observations, native_generations = Counter(), [], {}
    for test in tests:
        observed = read_json(test["observer"]["path"])
        require(digest(test["observer"]["path"]) == test["observer"]["sha256"] and
                observed["observation_count_matches"] and not observed["timed_out"] and
                not observed["unobserved_process_ids"] and observed["parent_raw_exit"] == 0,
                "Current-runtime observation is incomplete")
        if test["name"] == "basic":
            require(not observed["passed"] and len(observed["unrelayed_high_exits"]) == 4 and
                    all(row["raw_exit"] == 256 for row in observed["unrelayed_high_exits"]),
                    "Expected-negative record differs from its exact documented scope")
        else:
            require(observed["passed"] and not observed["unrelayed_high_exits"],
                    "A positive current-runtime scope failed observation")
        require(test["semantic_passed"] and not test["failed_tests"] and not test["file_errors"],
                "Current runtime has an unresolved semantic failure")
        summary.update(created=observed["created_processes"], observed=observed["observed_processes"])
        observations.append({"name": test["name"], "argv_pid_birth_log": test["launch"],
                             "observer": test["observer"], "passed": observed["passed"]})
        for row in observed["native_target_exits"]:
            native_generations[row["pid"], row["created"]] = generation_state(row["pid"], row["created"])
    extracted = read_json(receipt["zip_extraction_qualification"]["path"])
    observed = read_json(extracted["raw_observer"]["path"])
    require(observed["passed"] and observed["observation_count_matches"] and
            not observed["unrelayed_high_exits"], "Actual extracted package execution failed")
    summary.update(created=observed["created_processes"], observed=observed["observed_processes"])
    observations.append({"name": "zip-extracted-alias-api", "argv_pid_birth_log": extracted["launch"],
                         "observer": extracted["raw_observer"], "passed": observed["passed"]})
    for row in observed["native_target_exits"]:
        native_generations[row["pid"], row["created"]] = generation_state(row["pid"], row["created"])
    require(summary["created"] == summary["observed"] == 94 and len(native_generations) == 58,
            "Final execution/drain count differs")
    combined_runtime.verify_private()
    write_json(current / "assembly-intake.json", {
        "schema": 1, "status": "native-msys-tcl-ready-for-named-scope-assembly",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "package_receipt": reference(receipt_path), "archive": receipt["archive"],
        "manifest": receipt["manifest"], "package_root": receipt["package_root"],
        "file_count": len(receipt["files"]), "pe_count": len(pe), "all_pe_aa64": True,
        "x64_payload_count": 0, "aliases": receipt["aliases"],
        "runtime_dependency": receipt["runtime_handoff"], "runtime_sha256": receipt["runtime_sha256"],
        "other_dependencies": receipt["runtime_dependencies"],
        "source_repository": "https://core.tcl-lang.org/tcl",
        "source_commit_scheme": "Fossil manifest.uuid from pinned official source archive, not a Git SHA",
        "source_commit": receipt["source_provenance"]["upstream_fossil_commit"],
        "source_tree": {key: value for key, value in receipt["source_provenance"]["source_tree"].items()
                        if key != "inventory"},
        "archive_origin": receipt["source_provenance"]["upstream"],
        "recipe_repository": receipt["source_provenance"]["recipe_repository"],
        "recipe_commit": receipt["source_provenance"]["recipe_commit"],
        "recipe": receipt["source_provenance"]["recipe"],
        "historical_build_orchestration": "The already-admitted build used x64/emulated MSYS shell/make "
                                         "drivers with the native ARM64 cross-target compiler. Those drivers "
                                         "are neither shipped nor used in this current qualification.",
        "rebuilds": 0, "current_native_scope": receipt["coverage"],
        "installed_alias_and_extensions": receipt["zip_extraction_qualification"],
        "supported_paths": receipt["actual_supported_paths"],
        "unsupported_without_other_providers": receipt["not_supported_without_separate_native_provider"],
        "limitations": receipt["limitations"],
        "expected_negative_collector_gate": "Four native basic-test raw256 exits remain collector-failed "
                                           "despite passing original expected-error assertions; no decoder "
                                           "or universal current-runtime exit-domain approval is inferred.",
        "observations": observations,
        "drain": {"fresh_grant": 2, "observed_jobs": 36, "process_counts": dict(summary),
                  "native_generations": list(native_generations.values()), "active_owned_generations": 0,
                  "free_memory_bytes": require_memory(), "returnable_jobs": 2},
    })
    print(json.dumps({"intake": reference(current / "assembly-intake.json"),
                      "package": reference(receipt_path), "archive": receipt["archive"],
                      "jobs_drained": 36, "native_generations_drained": 58, "returnable_jobs": 2}, indent=2))


if __name__ == "__main__":
    main()
