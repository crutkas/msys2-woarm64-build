"""Summarize unchanged mutex cases from sampled generations and raw native exits."""

import argparse
import json
from pathlib import Path
import re

from db_channel_checks import expected_mutex_matrix
from sources import ContractError, digest
from ssh_bootstrap import write_json


CASE_ARGUMENTS = re.compile(r" -p (\d+) -t (\d+) -a (\d+) -n (\d+)(?:\s|$)")


def summarize(samples, exits):
    generations = {}
    for sample in samples:
        for worker in sample["workers"]:
            match = CASE_ARGUMENTS.search(worker.get("command") or "")
            if not match or Path(worker["image"]).name.lower() != "test_mutex.exe":
                continue
            identity = (worker["pid"], worker["created"])
            if identity not in generations:
                generations[identity] = {"pid": identity[0], "created": identity[1],
                    "image": worker["image"],
                    "configuration": tuple(map(int, match.groups())), "first_sample": sample["monotonic"],
                    "last_sample": sample["monotonic"], "maximum_os_threads": worker["actual_os_threads"],
                    "cpu_100ns": worker["kernel_time_100ns"] + worker["user_time_100ns"]}
            row = generations[identity]
            row["last_sample"] = sample["monotonic"]
            row["maximum_os_threads"] = max(row["maximum_os_threads"], worker["actual_os_threads"])
            row["cpu_100ns"] = max(row["cpu_100ns"], worker["kernel_time_100ns"] + worker["user_time_100ns"])
    outcomes = {(row["pid"], row["created"]): row for row in exits}
    cases = []
    for config in expected_mutex_matrix():
        candidates = [row for row in generations.values() if row["configuration"] == config]
        if not candidates:
            raise ContractError(f"No observed unchanged configuration: {config}")
        # A fork-copy can briefly retain the parent's argv. The long-lived driver
        # is distinguished by its observed lifetime; retain every candidate below.
        row = max(candidates, key=lambda item: item["last_sample"] - item["first_sample"])
        event = outcomes.get((row["pid"], row["created"]))
        if (event is None or event["raw_exit"] != 0
                or Path(event.get("executable", "")).resolve() != Path(row["image"]).resolve()):
            raise ContractError(f"Configuration lacks a successful generation-bound raw exit: {config}")
        concurrent_samples = [sample for sample in samples if any(
            worker["pid"] == row["pid"] and worker["created"] == row["created"] for worker in sample["workers"])]
        maximum_worker_cpu = max(sum(worker["kernel_time_100ns"] + worker["user_time_100ns"]
                                     for worker in sample["workers"]
                                     if Path(worker["image"]).name.lower() == "test_mutex.exe")
                                 for sample in concurrent_samples)
        cases.append({**row, "ordinal": len(cases) + 1, "raw_exit": event["raw_exit"],
                      "sampled_duration_seconds": row["last_sample"] - row["first_sample"],
                      "sampled_driver_cpu_seconds": row["cpu_100ns"] / 10_000_000,
                      "maximum_concurrent_worker_cpu_seconds": maximum_worker_cpu / 10_000_000,
                      "observed_candidate_generations": candidates})
    if [row["created"] for row in cases] != sorted(row["created"] for row in cases):
        raise ContractError("Observed matrix ordering differs")
    for index, row in enumerate(cases[:-1]):
        row["next_case_start_interval_seconds"] = (cases[index + 1]["created"] - row["created"]) / 10_000_000
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads((args.run / "result.json").read_text())
    observed_path = args.run / "01-TestMutexAlignment.native-job.json"
    observed = json.loads(observed_path.read_text())
    if (result.get("status") != "passed" or result.get("inputs_unchanged") is not True
            or observed.get("passed") is not True or observed.get("timed_out")
            or observed["created_processes"] != observed["observed_processes"]):
        raise ContractError("Cannot turn a timeout or partial native observation into a passed matrix")
    sample_path = args.run / "mutex-progress.jsonl"
    samples = [json.loads(line) for line in sample_path.read_text().splitlines()]
    cases = summarize(samples, observed["native_target_exits"])
    write_json(args.output, {"schema": 1, "status": "all-24-unchanged-cases-completed",
        "generator_sha256": digest(Path(__file__)),
        "run_result": {"path": str(args.run / "result.json"), "sha256": digest(args.run / "result.json")},
        "native_observer": {"path": str(observed_path), "sha256": digest(observed_path)},
        "samples": {"path": str(sample_path), "sha256": digest(sample_path)},
        "cases": cases, "created_processes": observed["created_processes"],
        "observed_processes": observed["observed_processes"],
        "minimum_free_gib": result["minimum_free_gib"],
        "timing_scope": "Durations are lower bounds from first/last half-second samples; "
                        "next-case intervals use kernel process-creation FILETIMEs. Raw exits bind exact generations.",
        "full_upstream_suite_claim": False})
    print(json.dumps({"cases": len(cases), "output": str(args.output), "sha256": digest(args.output)}))


if __name__ == "__main__":
    main()
