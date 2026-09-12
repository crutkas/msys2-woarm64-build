"""Run every real upstream run-* case and retain unmodified raw exits and outputs."""

import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory, write_json
from native_job_runner import run_observed

common = importlib.import_module("bash907-common")
ROOT = common.ROOT


def main():
    output = ROOT / "upstream-suite-01"
    if output.exists():
        raise ContractError("Fresh suite output required")
    inputs = json.loads((ROOT / "inputs.json").read_text())
    runtime = ROOT / "runtime"
    common.combined.sealed(runtime / "usr/bin/msys-2.0.dll", common.combined.RUNTIME_SHA)
    common.prepare.terminal.sealed(runtime / "usr/bin/bash.exe", common.prepare.BASH_SHA)
    output.mkdir()
    for name in ("home", "temp", "native-exits", "cases"):
        (output / name).mkdir()
    report = {"schema": 1, "status": "running", "pid": os.getpid(), "creation_filetime": common.birth(),
              "command": [sys.executable, *sys.argv], "runtime_sha256": common.combined.RUNTIME_SHA,
              "bash_sha256": common.prepare.BASH_SHA, "jobs": 1, "minimum_free_gib": require_memory(),
              "inputs_sha256": digest(ROOT / "inputs.json"), "cases": [],
              "scope": "Complete default upstream run-* cases; exact actual-build source copied, cases unmodified. Per-case current native observer, no raw-exit normalization."}
    write_json(output / "launch.json", report)
    print(json.dumps({key: report[key] for key in ("pid", "creation_filetime", "command", "runtime_sha256")}), flush=True)
    tests = ROOT / "source/tests"
    # Upstream's driver establishes these variables; case implementations remain unchanged.
    env = common.environment(output, runtime)
    env.update(THIS_SH=str(runtime / "usr/bin/bash.exe").replace("\\", "/"),
               BUILD_DIR=str(ROOT / "source").replace("\\", "/"),
               NATIVE_BASH_TEST_HELPERS=common.posix(runtime / "usr/bin"),
               MSYS2_ENV_CONV_EXCL="NATIVE_BASH_TEST_HELPERS")
    raw_counts = {}
    try:
        with common.cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            for name in inputs["expected_upstream_cases"]:
                require_memory()
                case = output / "cases" / name
                case.mkdir()
                env["BASH_TSTOUT"] = common.posix(case / "upstream.output")
                case_env = dict(env, WOARM64_NATIVE_EXIT_DIR=str(case / "native-exits"))
                (case / "native-exits").mkdir()
                command = [runtime / "usr/bin/sh.exe", name]
                timeout = 900
                started = time.monotonic()
                process = run_observed(command, cwd=tests, env=case_env,
                                       log_path=case / "observed.log", result_path=case / "native-job.json",
                                       relay_records=case / "native-exits", timeout=timeout,
                                       driver_prefix=ROOT / "observer")
                observation = json.loads((case / "native-job.json").read_text())
                for row in observation["native_target_exits"]:
                    key = str(row["raw_exit"])
                    raw_counts[key] = raw_counts.get(key, 0) + 1
                log = (case / "observed.log").read_text(errors="replace")
                entry = {"name": name, "command": list(map(str, command)), "seconds": time.monotonic() - started,
                         "parent_raw_exit": observation["parent_raw_exit"], "timed_out": observation["timed_out"],
                         "observer_passed": process["passed"], "created": observation["created_processes"],
                         "observed": observation["observed_processes"],
                         "unobserved": observation.get("unobserved_processes", []),
                         "unresolved": observation.get("unresolved_processes", []),
                         "unrelayed_high_exits": len(observation["unrelayed_high_exits"]),
                         "log": str(case / "observed.log"), "log_sha256": digest(case / "observed.log"),
                         "observation_sha256": digest(case / "native-job.json"),
                         "output_bytes": (case / "observed.log").stat().st_size,
                         "raw_status": "zero" if observation["parent_raw_exit"] == 0 and not observation["timed_out"] else "failure",
                         "failure_classification": "pending-evidence-review" if observation["parent_raw_exit"] != 0 or observation["timed_out"] else None}
                report["cases"].append(entry)
                report["raw_native_exit_counts"] = raw_counts
                (output / "progress.json").write_text(json.dumps(report, indent=2) + "\n")
                print(json.dumps({"case": name, "parent_raw_exit": entry["parent_raw_exit"], "timeout": entry["timed_out"],
                                  "observer_passed": entry["observer_passed"], "log_bytes": len(log)}), flush=True)
        report["status"] = "complete-raw-upstream-suite-evidence-review-required"
        report["counts"] = {"total": len(report["cases"]),
                            "parent_zero": sum(r["raw_status"] == "zero" for r in report["cases"]),
                            "parent_failures": sum(r["raw_status"] == "failure" for r in report["cases"]),
                            "timeouts": sum(r["timed_out"] for r in report["cases"]),
                            "observer_passes": sum(r["observer_passed"] for r in report["cases"])}
        if len(report["cases"]) != len(inputs["expected_upstream_cases"]):
            raise ContractError("Full upstream case count was not reached")
    except BaseException as error:
        report.update(status="incomplete", error=str(error))
        raise
    finally:
        report["runtime_binary_sha256_after"] = digest(runtime / "usr/bin/msys-2.0.dll")
        report["bash_sha256_after"] = digest(runtime / "usr/bin/bash.exe")
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "counts": report["counts"]}), flush=True)


if __name__ == "__main__":
    main()
