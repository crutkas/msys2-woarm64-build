"""Seal complete raw Bash907 requalification, retaining the controlling interactive failure."""

import importlib
import json
from pathlib import Path
import shutil

from sources import ContractError, digest
from ssh_bootstrap import write_json

common = importlib.import_module("bash907-common")
ROOT = common.ROOT


def evidence(path):
    path = Path(path)
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def main():
    output = ROOT / "qualification-handoff-01"
    if output.exists():
        raise ContractError("Fresh immutable result handoff required")
    inputs = json.loads((ROOT / "inputs.json").read_text())
    suite_path = ROOT / "upstream-suite-01/result.json"
    suite = json.loads(suite_path.read_text())
    if suite["status"] != "complete-raw-upstream-suite-evidence-review-required":
        raise ContractError("Do not seal an incomplete upstream run as complete")
    if sorted(row["name"] for row in suite["cases"]) != inputs["expected_upstream_cases"] or len(suite["cases"]) != 86:
        raise ContractError("Exactly all86 default upstream cases are required")
    baseline = json.loads((common.prepare.BASE_SUITE / "qualification.json").read_text())
    classifications_path = ROOT / "upstream-case-classifications.json"
    classifications = json.loads(classifications_path.read_text()) if classifications_path.exists() else {}
    buckets = {"bash_or_current_runtime_behavior": 0, "absent_or_non_native_helper": 0,
               "harness_or_MSYS_Windows_assumption": 0}
    unresolved_timeouts = []
    case_evidence = []
    review_needed = []
    accounting_gaps = []
    for case in suite["cases"]:
        log = Path(case["log"])
        common.combined.sealed(log, case["log_sha256"])
        observation_path = log.with_name("native-job.json")
        common.combined.sealed(observation_path, case["observation_sha256"])
        observation = json.loads(observation_path.read_text())
        if (observation["parent_raw_exit"] != case["parent_raw_exit"]
                or observation["created_processes"] != case["created"]
                or observation["observed_processes"] != case["observed"]):
            raise ContractError("Case summary differs from original raw observation")
        if case["created"] != case["observed"] or case["unobserved"] or case["unresolved"]:
            accounting_gaps.append({key: case[key] for key in
                                    ("name", "parent_raw_exit", "timed_out", "created", "observed", "unobserved", "unresolved")})
        baseline_row = baseline["case_evidence"].get(case["name"] + ".log", {})
        matches_baseline = baseline_row.get("sha256") == case["log_sha256"]
        nonzero = case["parent_raw_exit"] != 0 or case["timed_out"]
        anomalous_output = case["output_bytes"] > 0 and not matches_baseline
        classification = classifications.get(case["name"])
        if nonzero or anomalous_output:
            if (not classification or classification.get("bucket") not in (*buckets, "unresolved_timeout")
                    or not classification.get("evidence") or not classification.get("explanation")):
                review_needed.append(case["name"])
            else:
                if classification["bucket"] == "unresolved_timeout":
                    unresolved_timeouts.append(case["name"])
                else:
                    buckets[classification["bucket"]] += 1
        case_evidence.append({**case, "matches_prior_registered_case_output": matches_baseline,
                              "failure_classification": classification})
    if review_needed:
        raise ContractError(f"Classify actual raw/output failures before sealing: {review_needed}")
    controlling = Path(r"C:\ap11-native-provider-intake\bash-runtime907-qualification-failure-v1.json")
    common.combined.sealed(controlling, "ad40b7e220d3be4373ef0811523cd443a71da60058c9b9c1c90ab11794294ac5")
    signal = ROOT / "signal-failure-handoff-01/handoff.json"
    common.combined.sealed(signal, "3c753f5b569c2760fb58ad93e5099ef4aa74e6a0a39063dba00236ba6ec57b3e")
    for name, row in inputs["private_runtime_files"].items():
        common.combined.sealed(ROOT / "runtime" / name, row["sha256"])
    common.combined.sealed(inputs["package"]["copy"], inputs["package"]["sha256"])
    original = json.loads((ROOT / "original-controller-907-01/result.json").read_text())
    current = json.loads((ROOT / "interactive-01/result.json").read_text())
    paths = ROOT / "unicode-paths-01/result.json"
    output.mkdir()
    report = {
        "schema": 1, "status": "Bash907-requalification-complete-with-controlling-interactive-failure",
        "runtime907_compatibility_admitted": False, "existing_d70_admission_unchanged": True,
        "input_contract": evidence(inputs["provider_qualification_contract"]),
        "input_inventory": evidence(ROOT / "inputs.json"),
        "subject_package": inputs["package"], "bash_sha256": inputs["bash_sha256"],
        "runtime": {"path": str(ROOT / "runtime/usr/bin/msys-2.0.dll"),
                    "sha256": common.combined.RUNTIME_SHA, "bytes": (ROOT / "runtime/usr/bin/msys-2.0.dll").stat().st_size,
                    "machine": "0xAA64", "producer_handoff": evidence(common.combined.HANDOFF)},
        "subject_dependencies": inputs["subject_dependencies"],
        "pe_images": inputs["pe_images"], "test_source_pe_images": inputs["source_pe_images"],
        "source_archive": inputs["source_release_archive"],
        "actual_source_tree": evidence(inputs["source_snapshot_manifest"]),
        "source_recipe_producer": evidence(Path(r"C:\ag-bash-e138-01\bash-provider-handoff-02\handoff.json")),
        "upstream": {"result": evidence(suite_path), "raw_counts": suite["counts"],
                     "confirmed_failure_buckets": buckets,
                     "unresolved_timeout_count": len(unresolved_timeouts),
                     "unresolved_timeout_cases": unresolved_timeouts,
                     "classification_limit": "Requested three buckets are reported for confirmed causes. Two bounded noncompletions remain unresolved rather than being assigned a false cause.",
                     "cases": case_evidence,
                     "observer_accounting": {
                         "created": sum(case["created"] for case in suite["cases"]),
                         "observed": sum(case["observed"] for case in suite["cases"]),
                         "gaps": accounting_gaps,
                         "complete_generation_accounting_claimed": False if accounting_gaps else True,
                         "nonzero_or_missing_observer_verdicts_not_normalized": True,
                     },
                     "raw_native_exit_DWORD_counts": suite["raw_native_exit_counts"],
                     "raw_DWORDs_normalized": False,
                     "observer_rule": "Conservative high-child-exit verdicts are reported separately from raw upstream driver statuses. No division, truncation, expected-exit override, or blanket success.",
                     "stdout_rule": "Nonempty logs matched the original registered warnings or received explicit evidence-based failure classification; oldd70passes were not reused."},
        "supplemental_missing_compiler_replay": {
            "result": evidence(ROOT / "run-glob-bracket-native-compiler-01/result.json"),
            "scope": "Same real upstream glob-bracket case, genuine copied AA64 test compiler, no stubs. This does not replace the original raw missing-gcc failure or its bucket count.",
        },
        "supplemental_IFS_timeout_replay": {
            "result": evidence(ROOT / "run-ifs-posix-longer-bound-01/result.json"),
            "scope": "Same unchanged6856-assertion source, one predeclared1800-second bound; timed out again, not a semantic pass.",
        },
        "interactive": {
            "controlling_failure": evidence(signal), "provider_failure_disposition": evidence(controlling),
            "original_controller907": original["semantics"]["counts"],
            "instrumented907": current["semantics"]["counts"],
            "instrumented_pass_is_not_failure_waiver": True,
            "per_member_process_group_evidence": evidence(ROOT / "interactive-01/group-members.tsv"),
            "additional_unicode_path_checks": evidence(paths),
        },
        "historical_invalid_selection": evidence(Path(r"C:\ag-bash907-20260911-01\invalid-selection.json")),
        "boundaries": {"Bash_rebuilt": False, "admitted_libraries_rebuilt": False, "runtime_rebuilt": False,
                       "provider_or_package_mutations": False, "x64_private_PE_inputs": 0,
                       "test_only_utilities_not_shipped_or_admitted": True,
                       "PATH": "Only the exact private AA64 runtime usr/bin plus Windows System32 at capture launch",
                       "desktop_console_touched": False},
    }
    write_json(output / "handoff.json", report)
    code = output / "maintained"
    code.mkdir()
    for path in (common.HERE / "prepare-bash907.py", common.HERE / "bash907-common.py",
                 common.HERE / "run-bash907-suite.py", common.HERE / "run-bash907-interactive.py",
                 common.HERE / "replay-bash907-original.py", common.HERE / "seal-bash907-signal-failure.py",
                 common.HERE / "seal-bash907-results.py", common.HERE / "fixtures/native-bash907-pty.c",
                 common.HERE / "fixtures/bash907-paths.bash"):
        shutil.copyfile(path, code / path.name)
    print(json.dumps({"handoff": str(output / "handoff.json"), "sha256": digest(output / "handoff.json"),
                      "upstream_raw_counts": suite["counts"], "failure_buckets": buckets,
                      "unresolved_timeouts": unresolved_timeouts,
                      "runtime907_admission": False}), flush=True)


if __name__ == "__main__":
    main()
