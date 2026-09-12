"""One explicit longer-wall-bound replay of the full IFS case, without dropping assertions."""

import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

from native_job_runner import run_observed
from sources import ContractError, digest
from ssh_bootstrap import write_json

common = importlib.import_module("bash907-common")
ROOT = common.ROOT


def main():
    output = ROOT / "run-ifs-posix-longer-bound-01"
    if output.exists():
        raise ContractError("Only one declared longer-bound IFS replay is permitted")
    original = ROOT / "upstream-suite-01/cases/run-ifs-posix/native-job.json"
    prior = json.loads(original.read_text())
    if not prior["timed_out"] or prior["parent_raw_exit"] != 1460:
        raise ContractError("This replay requires the exact observed wall-timeout boundary")
    output.mkdir()
    for name in ("home", "temp", "native-exits"):
        (output / name).mkdir()
    source = output / "source"
    shutil.copytree(common.prepare.BASH_ROOT / "source", source)
    runtime = ROOT / "runtime"
    env = common.environment(output, runtime)
    env.update(THIS_SH=str(runtime / "usr/bin/bash.exe").replace("\\", "/"),
               BUILD_DIR=str(source).replace("\\", "/"),
               BASH_TSTOUT=common.posix(output / "upstream.output"))
    command = [runtime / "usr/bin/sh.exe", "run-ifs-posix"]
    report = {"schema": 1, "status": "running", "pid": os.getpid(), "creation_filetime": common.birth(),
              "command": list(map(str, command)), "environment": env, "jobs": 1,
              "original_timeout_observation": str(original), "original_timeout_sha256": digest(original),
              "original_wall_seconds": 900, "declared_replay_wall_seconds": 1800,
              "assertions_expected_from_source": 6856, "cases_removed": 0,
              "source_script_sha256": digest(source / "tests/ifs-posix.tests"),
              "scope": "One full unchanged6856-assertion case with only wall bound enlarged; original timeout remains failure, no retry-until-green"}
    write_json(output / "launch.json", report)
    print(json.dumps({key: report[key] for key in ("pid", "creation_filetime", "command", "declared_replay_wall_seconds")}), flush=True)
    start = time.monotonic()
    with common.cpu_budget(1) as budget:
        report["cpu_budget"] = budget
        report["process"] = run_observed(command, cwd=source / "tests", env=env,
                                         log_path=output / "observed.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=1800,
                                         driver_prefix=ROOT / "observer")
    report["seconds"] = time.monotonic() - start
    report["raw_observation"] = json.loads((output / "native-job.json").read_text())
    report["status"] = "complete-longer-bound-raw-result"
    write_json(output / "result.json", report)
    print(json.dumps({"seconds": report["seconds"], "raw_parent": report["raw_observation"]["parent_raw_exit"],
                      "timeout": report["raw_observation"]["timed_out"]}), flush=True)


if __name__ == "__main__":
    main()
