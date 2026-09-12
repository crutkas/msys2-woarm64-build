"""A/B the original compiled PTY controller without changing Bash/helpers/controller bytes."""

import importlib
import json
import os
from pathlib import Path
import shutil
import sys

from native_job_runner import run_observed
from sources import ContractError, digest, inventory
from ssh_bootstrap import write_json

common = importlib.import_module("bash907-common")
ROOT = common.ROOT
ORIGINAL = Path(r"C:\ag-bash907-20260911-01\interactive-01")


def main(mode):
    if mode not in ("907", "d70"):
        raise ContractError("Explicit original-controller comparison runtime required")
    output = ROOT / ("original-controller-" + mode + "-01")
    if output.exists():
        raise ContractError("Fresh comparison output required")
    original_report = json.loads((ORIGINAL / "launch.json").read_text())
    original_source = ORIGINAL / "native-bash907-pty.c"
    common.combined.sealed(original_source, original_report["source_sha256"])
    original_driver = ORIGINAL / "runtime/usr/bin/bash907-pty.exe"
    old_result = json.loads((ORIGINAL / "result.json").read_text())
    common.combined.sealed(original_driver, old_result["fixture_pe"]["sha256"])
    output.mkdir()
    for name in ("home", "temp", "native-exits"):
        (output / name).mkdir()
    shutil.copytree(ROOT / "runtime", output / "runtime")
    shutil.copyfile(original_driver, output / "runtime/usr/bin/bash907-pty.exe")
    shutil.copyfile(original_source, output / "native-bash907-pty.c")
    runtime_sha = common.combined.RUNTIME_SHA
    if mode == "d70":
        runtime_sha = "d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d"
        source = common.prepare.BASE_SUITE / "runtime/usr/bin/msys-2.0.dll"
        common.combined.sealed(source, runtime_sha)
        shutil.copyfile(source, output / "runtime/usr/bin/msys-2.0.dll")
    controller = importlib.import_module("run-bash907-interactive")
    report = {"schema": 1, "status": "running", "pid": os.getpid(), "creation_filetime": common.birth(),
              "comparison": mode, "runtime_sha256": runtime_sha, "bash_sha256": common.prepare.BASH_SHA,
              "source_sha256": digest(original_source), "controller_sha256": digest(original_driver),
              "focus_jobs": False, "direct_group_signal": False, "pipeline": None, "delivery_only": False,
              "expected_cases": controller.EXPECTED_CASES, "original_failure": str(ORIGINAL / "result.json"),
              "subject_dependency_contract_sha256": "4dc1ff625c82d762d25f157538146288758b7ffa2a150e09c6c4e8b28e137162",
              "scope": "Finite predeclared exact-controller A/B; correct admitted dependency bytes both runs, only runtime changes. No recompile/normalization/retry-until-pass."}
    write_json(output / "launch.json", report)
    print(json.dumps({k: report[k] for k in ("pid", "creation_filetime", "comparison", "runtime_sha256", "controller_sha256")}), flush=True)
    with common.cpu_budget(1) as budget:
        report["cpu_budget"] = budget
        result = common.observed([sys.executable, "-B", Path(controller.__file__), "--worker", output],
                                 output / "run", output / "runtime", timeout=780, cwd=output)
    report["observer"] = result
    report["raw_observation"] = json.loads((output / "run/native-job.json").read_text())
    if (output / "worker-result.json").exists():
        report["semantics"] = json.loads((output / "worker-result.json").read_text())
    report["runtime_files_after"] = inventory(output / "runtime")
    report["status"] = "comparison-recorded-with-raw-results"
    write_json(output / "result.json", report)
    print(json.dumps({"comparison": mode, "counts": report.get("semantics", {}).get("counts")}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
