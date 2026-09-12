"""Seal targeted SQLite progress without promoting the upstream raw-exit gate."""

import argparse
import importlib.util
import json
from pathlib import Path

from sources import ContractError, digest, inventory
from sqlite_consumer_inputs import sealed_json, verify_files
from ssh_bootstrap import require_memory

spec = importlib.util.spec_from_file_location("original_sealer", Path(__file__).with_name("seal-native-sqlite.py"))
original_sealer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original_sealer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(r"C:\ag-sqlite-resume-01")
    output = args.output.resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ContractError("Fresh owned continuation handoff required")
    previous_path = Path(r"C:\ag-sqlite-e138-01\handoff-01\result.json")
    previous = sealed_json(previous_path, "9bfa0f82b6456b546e654e53da68661555fee0d8a9656b592258a052c2edf718")
    baseline_path = root / "baseline-01/result.json"
    baseline = sealed_json(baseline_path, "37e33ba0330acdf7cbeb48cb6eaaaf1092307466b7fb52f9f4dc22ac39848e21")
    consumer_path = root / "shell-composition-03/result.json"
    consumer = sealed_json(consumer_path, "b4a0ee773d0b06c946bce77f68acfb73c5f7157aef6e7f144eabed05be3ea8cd")
    upstream_path = root / "upstream-shell5-02/result.json"
    upstream = sealed_json(upstream_path, "a3db03945db18a5fcd6cb220d5f245a81929a9a2ff8077b957526198e0f7e634")
    if (baseline["input_integrity_errors"] or not baseline["tdbc_passed"]
            or baseline["shell_pipe_passed"] or baseline["shell5_import_passed"]):
        raise ContractError("Baseline does not preserve the actual reproduced shell failure")
    if (consumer["status"] != "native-msys-sqlite-shell-and-tdbc-consumers-passed-candidate-composition"
            or not consumer["input_integrity_passed"]
            or len(consumer["steps"]) != 2 or any(not s["process"]["passed"] for s in consumer["steps"])):
        raise ContractError("Native shell consumer evidence does not pass")
    if ((upstream["errors"], upstream["tests"], upstream["shell5_1_8_passed"]) != (0, 53, True)
            or upstream["process"]["passed"] or upstream["status"] != "failed"):
        raise ContractError("The exact assertion-success/observer-failure distinction must be preserved")
    prepared_path = root / "shell-composition-03/prepare.json"
    prepared = sealed_json(prepared_path, consumer["prepare_sha256"])
    verify_files(prepared_path.parent / "runtime", prepared["runtime"]["files"])
    verify_files(prepared_path.parent / "inputs", prepared["fixture_files"])
    if not (prepared_path.parent / "runtime/tmp").is_dir():
        raise ContractError("Required private /tmp is missing")
    for split in previous["payloads"].values():
        verify_files(split["stage"], split["files"])
    observer = json.loads((root / "upstream-shell5-02/native-job.json").read_text())
    if len(observer["unrelayed_high_exits"]) != 9 or not observer["observation_count_matches"]:
        raise ContractError("Unexpected upstream raw-exit evidence")
    drains = [original_sealer.require_launcher_exit(record["launcher"]) for record in (baseline, consumer, upstream)]
    receipts = {str(path): digest(path) for path in (previous_path, baseline_path, consumer_path, upstream_path, prepared_path)}
    for directory in root.iterdir():
        if directory.is_dir() and directory != output:
            for name in ("prepare.json", "launch.json", "result.json", "ordinary.native-job.json",
                         "captured.native-job.json", "native-job.json", "shell5-verbose.txt"):
                path = directory / name
                if path.is_file():
                    receipts[str(path)] = digest(path)
    current_files = inventory(Path(__file__).parent)
    old_files = previous["recipe_export"]["files"]
    changes = {name: {"before": old_files.get(name), "after": current_files.get(name)}
               for name in old_files.keys() | current_files.keys() if old_files.get(name) != current_files.get(name)}
    report = {
        "schema": 1, "status": "native-msys-sqlite-shell-consumer-fixed-upstream-observer-gate-retained",
        "version": "3.53.4", "target": "aarch64-pc-cygwin", "data_model": "MSYS LP64",
        "previous_handoff": {"path": str(previous_path), "sha256": receipts[str(previous_path)],
                             "all_seven_original_splits_unchanged": True},
        "fix_scope": ["Provide actual native /bin/sh and awk in the same private runtime",
                      "Create real private /tmp; do not filter the missing-directory diagnostic"],
        "baseline": {"shell_pipe_passed": False, "shell_import_passed": False,
                     "reason": "Native /bin/sh access and popen fail with ENOENT", "tdbc_passed": True},
        "native_consumer": {"passed": True, "ordinary_and_captured": True,
                            "runtime_sha256": consumer["runtime_sha256"],
                            "bash_candidate_sha256": consumer["bash_candidate_sha256"],
                            "sqlite_tcl_zlib_files_unchanged": prepared["runtime"]["sqlite_tcl_zlib_files_unchanged"],
                            "fstab_unchanged": prepared["runtime"]["fstab_unchanged"],
                            "steps": consumer["steps"]},
        "upstream_shell5": {"assertions_passed": True, "tests": 53, "errors": 0,
                            "formerly_failing_case_passed": True, "observer_passed": False,
                            "raw_exits": observer["unrelayed_high_exits"],
                            "created_processes": observer["created_processes"],
                            "observed_processes": observer["observed_processes"]},
        "remaining_gates": ["Runtime-aware provenance for nine raw-256 CLI exits; do not decode or promote them locally",
                            "Owning Bash full-suite/candidate admission",
                            "Original broader SQLite permission/symlink/WAL and missing sanitizer-library gates remain",
                            "Full SDK, Git, and provider admission are independent"],
        "full_git_complete": False, "provider_admission": False, "full_cpp_qualified": False,
        "full_upstream_qualified": False, "launcher_drain": drains,
        "free_ram_gib_at_seal": require_memory(), "maximum_concurrent_target_jobs": 1,
        "receipts": receipts, "source_delta": changes,
    }
    output.mkdir()
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "result": str(output / "result.json"),
                      "sha256": digest(output / "result.json")}))


if __name__ == "__main__":
    main()
