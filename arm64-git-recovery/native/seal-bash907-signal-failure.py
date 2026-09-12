"""Seal the runtime-only interactive A/B failure without relabelling the pending suite."""

import importlib
import json
from pathlib import Path
import shutil

from sources import ContractError, digest
from ssh_bootstrap import write_json

common = importlib.import_module("bash907-common")
ROOT = common.ROOT


def evidence(path):
    return {"path": str(path), "sha256": digest(path), "size": path.stat().st_size}


def main():
    output = ROOT / "signal-failure-handoff-01"
    if output.exists():
        raise ContractError("Fresh immutable signal-failure handoff required")
    first = ROOT / "original-controller-907-01/result.json"
    second = ROOT / "original-controller-d70-01/result.json"
    current, baseline = (json.loads(path.read_text()) for path in (first, second))
    names = set(current["runtime_files_after"]) | set(baseline["runtime_files_after"])
    changes = sorted(name for name in names if current["runtime_files_after"].get(name) != baseline["runtime_files_after"].get(name))
    if changes != ["usr/bin/msys-2.0.dll"] or current["controller_sha256"] != baseline["controller_sha256"]:
        raise ContractError("The comparison does not differ only in runtime DLL")
    if current["semantics"]["counts"] != {"total": 19, "passed": 16, "failed": 1, "not_reached": 2}:
        raise ContractError("Unexpected original-controller current-runtime result")
    if baseline["semantics"]["counts"] != {"total": 19, "passed": 19, "failed": 0, "not_reached": 0}:
        raise ContractError("Unexpected original-controller baseline result")
    output.mkdir()
    controls = {}
    for name in ("interactive-01", "group-direct-01", "group-mixed-sleep-read-01",
                 "group-mixed-read-cat-01", "group-two-sleeps-01", "group-reversed-01", "group-builtin-01"):
        path = ROOT / name / "result.json"
        record = json.loads(path.read_text())
        controls[name] = {"result": evidence(path), "counts": record["semantics"]["counts"],
                          "module_capture": evidence(path.parent / "held-modules.json"),
                          "group_members": evidence(path.parent / "group-members.tsv")}
    provider = Path(r"C:\ap11-native-provider-intake\bash-runtime907-qualification-input-v1.json")
    common.combined.sealed(provider, "4dc1ff625c82d762d25f157538146288758b7ffa2a150e09c6c4e8b28e137162")
    report = {
        "schema": 1, "status": "runtime-dependent-interactive-foreground-pipeline-failure-reproduced",
        "full_Bash907_qualification": False, "upstream_suite": "Still running separately; no completed86-count claim in this receipt",
        "subject_contract": evidence(provider), "subject_inputs": evidence(ROOT / "inputs.json"),
        "bash_sha256": common.prepare.BASH_SHA,
        "controller_sha256": current["controller_sha256"],
        "only_binary_difference": changes,
        "runtime907": {"sha256": current["runtime_sha256"], "result": evidence(first),
                       "counts": current["semantics"]["counts"],
                       "foreground_pipeline_shell_status": 0,
                       "sleep_windows_exit_DWORD": 2, "cat_windows_exit_DWORD": 0},
        "baseline_d70": {"sha256": baseline["runtime_sha256"], "result": evidence(second),
                         "counts": baseline["semantics"]["counts"],
                         "foreground_pipeline_shell_status": 130,
                         "sleep_windows_exit_DWORD": 2, "cat_windows_exit_DWORD": 2},
        "interpretation": [
            "Bash reports the last pipeline member's status correctly when cat exits zero; no demonstrated Bash arithmetic/status-decoding error.",
            "The unchanged compiled controller reproduces the failure on907 and passes onD70 in this finite controlled pair, with every other runtime-tree file byte-identical.",
            "A separate instrumented907 run passes19/19 after foreground/member startup synchronization. This is timing-sensitive, not proof the original failure vanished.",
            "Every measured external/builtin member PGID matches the master foreground PGID; missing exec group membership is not supported by those captures.",
            "A separate sleep|read case gives shell PIPESTATUS130 1 with both members in one foreground PGID; retain as failure against expected130, with EOF/signal ordering mechanism unresolved.",
            "Exact GetExitCodeProcess DWORDs are retained. They are not normalised to POSIX wait words or shell exit codes.",
        ],
        "controls": controls,
        "failure_classification": {
            "original_controller907": "Behavioral regression evidence under current runtime, timing-sensitive signal delivery/EOF ordering unresolved; not a confirmed Bash source defect.",
            "missing_or_non_native_helper": False,
            "earlier_slave_tcgetpgrp_failure": "Harness vantage-point assumption: controller slave returned ENOTTY25; master ioctl successfully measures foreground PGID.",
        },
        "invalid_selection_history": evidence(Path(r"C:\ag-bash907-20260911-01\invalid-selection.json")),
        "payload_or_provider_mutations": False, "runtime_or_Bash_rebuilds": False,
        "next_owner": "Runtime integration67 for causal investigation; this worker continues unchanged full upstream Bash suite and reports raw three-bucket counts.",
    }
    write_json(output / "handoff.json", report)
    for path in (common.HERE / "fixtures/native-bash907-pty.c",
                 common.HERE / "run-bash907-interactive.py", common.HERE / "replay-bash907-original.py",
                 ROOT / "original-controller-907-01/native-bash907-pty.c"):
        filename = "original-" + path.name if path.parent.name.startswith("original-controller") else path.name
        shutil.copyfile(path, output / filename)
    print(json.dumps({"handoff": str(output / "handoff.json"), "sha256": digest(output / "handoff.json")}), flush=True)


if __name__ == "__main__":
    main()
