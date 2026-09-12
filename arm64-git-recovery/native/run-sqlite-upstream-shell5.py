"""Replay the entire unchanged upstream shell5 file in the native shell composition."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

from native_job_runner import run_observed
from sources import ContractError, digest, inventory
from sqlite_consumer_inputs import sealed_json, verify_files
from sqlite_build_inputs import msys_path
from sqlite_test_results import shell5_summary
from ssh_bootstrap import require_memory

spec = importlib.util.spec_from_file_location("sqlite_launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
TESTFIXTURE_SHA = "1c624aa778ffb2946544cc737bb720aecf337d38831a035ab5ab5a596a77f771"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument("--consumer-sha256", required=True)
    args = parser.parse_args()
    root = Path(r"C:\ag-sqlite-resume-01")
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(root):
        raise ContractError("Fresh private upstream test output required")
    candidate = args.consumer.resolve()
    if not candidate.is_relative_to(root):
        raise ContractError("Private consumer composition required")
    consumer = sealed_json(candidate / "result.json", args.consumer_sha256)
    prepared = sealed_json(candidate / "prepare.json", consumer["prepare_sha256"])
    if consumer["status"] != "native-msys-sqlite-shell-and-tdbc-consumers-passed-candidate-composition":
        raise ContractError("Successful real shell-pipeline consumer prerequisite required")
    runtime = candidate / "runtime"
    verify_files(runtime, prepared["runtime"]["files"])
    old = Path(r"C:\ag-sqlite-e138-01")
    source_manifest = json.loads((old / "prepared.inventory.json").read_text())
    verify_files(old / "prepared", source_manifest["files"])
    fixture = old / "build-06/testfixture.exe"
    if digest(fixture) != TESTFIXTURE_SHA:
        raise ContractError("Original full-profile native testfixture changed")
    output.mkdir()
    for name in ("bin", "inputs", "work", "home", "temp", "native-exits"):
        (output / name).mkdir()
    shutil.copyfile(fixture, output / "bin/testfixture.exe")
    shutil.copyfile(runtime / "usr/bin/sqlite3.exe", output / "bin/sqlite3.exe")
    script = Path(__file__).parent / "fixtures/sqlite-upstream-shell5.sh"
    shutil.copyfile(script, output / "inputs/driver.sh")
    env = launcher.environment(old, output, 1)
    env.update(PATH=os.pathsep.join(map(str, (runtime / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
               HOME=msys_path(output / "home"), TMP=str(output / "temp"), TEMP=str(output / "temp"),
               TMPDIR=msys_path(output / "temp"), TCL_LIBRARY=msys_path(runtime / "usr/lib/tcl8.6"),
               TCLLIBPATH=msys_path(runtime / "usr/lib"), WOARM64_NATIVE_TEST_ROOT=str(root))
    command = [runtime / "usr/bin/bash.exe", "--noprofile", "--norc", msys_path(output / "inputs/driver.sh"),
               msys_path(output), msys_path(runtime), msys_path(old / "prepared/source")]
    report = {"schema": 1, "status": "failed", "launcher": launcher.process_identity(), "jobs": 1,
              "command": list(map(str, command)), "minimum_free_ram_gib": require_memory(),
              "scope": "Entire original shell5.test only; native Bash/d70 candidate composition, not full quicktest admission",
              "source_sha256": source_manifest["files"]["source/test/shell5.test"]["sha256"],
              "testfixture_sha256": TESTFIXTURE_SHA, "sqlite_sha256": digest(output / "bin/sqlite3.exe"),
              "candidate_prepare_sha256": digest(candidate / "prepare.json"), "provider_admission": False}
    report["candidate_consumer_sha256"] = args.consumer_sha256
    launcher.write_json(output / "launch.json", report)
    print(json.dumps({"launcher": report["launcher"], "log": str(output / "shell5.log")}), flush=True)
    try:
        report["process"] = run_observed(command, cwd=output / "work", env=env,
                                         log_path=output / "shell5.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=300,
                                         driver_prefix=old / "observer")
        text = (output / "shell5.log").read_text(encoding="utf-8", errors="replace")
        verbose = (output / "shell5-verbose.txt").read_text(encoding="utf-8", errors="replace")
        summary = shell5_summary(text, verbose, report["process"]["passed"])
        report.update(summary, verbose_sha256=digest(output / "shell5-verbose.txt"))
        if summary["passed"]:
            report["status"] = "native-msys-sqlite-upstream-shell5-all-53-passed"
    finally:
        verify_files(runtime, prepared["runtime"]["files"])
        verify_files(old / "prepared", source_manifest["files"])
        if digest(fixture) != TESTFIXTURE_SHA:
            raise ContractError("Original testfixture changed during execution")
        report["inputs_unchanged"] = True
        launcher.write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "result": str(output / "result.json"),
                      "sha256": digest(output / "result.json")}))
    if report["status"] != "native-msys-sqlite-upstream-shell5-all-53-passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
