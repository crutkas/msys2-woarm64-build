"""Run the existing shared/static SQLite API fixtures normally on907, without a debugger."""

import argparse
import importlib.util
import json
import os
from pathlib import Path

from native_job_runner import run_observed
from sources import ContractError, digest
from sqlite_consumer_inputs import sealed_json, verify_files
from sqlite_build_inputs import msys_path
from ssh_bootstrap import require_memory

spec = importlib.util.spec_from_file_location("sqlite_launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepared = sealed_json(args.prepared / "prepare.json", args.sha256)
    project = Path(prepared["project_root"])
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(project):
        raise ContractError("Fresh ordinary combined-runtime proof directory required")
    runtime = Path(prepared["runtime_path"])
    verify_files(runtime, prepared["runtime_files"])
    output.mkdir()
    (output / "native-exits").mkdir()
    (output / "temp").mkdir()
    old = Path(r"C:\ag-sqlite-e138-01")
    env = launcher.environment(old, output, 1)
    env.update(PATH=os.pathsep.join(map(str, (runtime / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
               HOME=str(output), TMP=str(output / "temp"), TEMP=str(output / "temp"),
               TMPDIR=msys_path(output / "temp"), WOARM64_NATIVE_TEST_ROOT=str(project))
    report = {"schema": 1, "status": "failed", "launcher": launcher.process_identity(),
              "prepared_sha256": args.sha256, "runtime_sha256": prepared["runtime_sha256"],
              "combined_receipt_sha256": prepared["combined_receipt_sha256"], "jobs": 1,
              "scope": "Ordinary non-debugger shared/static SQLite C API and direct helper APIs; no compiler rebuild",
              "free_ram_gib": require_memory(), "steps": []}
    launcher.write_json(output / "launch.json", report)
    print(json.dumps({"launcher": report["launcher"], "log_root": str(output)}), flush=True)
    try:
        for name, filename, arguments, marker in (
            ("shared", "sqlite-api-shared.exe", [msys_path(output / "shared.sqlite")], "sqlite-native-api-passed"),
            ("static", "sqlite-api-static.exe", [msys_path(output / "static.sqlite")], "sqlite-native-api-passed"),
            ("helpers", "sqlite-helper-apis.exe", [msys_path(runtime / "usr/bin"), msys_path(output / "helper.sqlite"),
                                                   msys_path(output / "helper.sql")], "sqlite-native-helper-apis-passed"),
        ):
            executable = args.prepared / "consumers" / filename
            if digest(executable) != prepared["consumer_files"][filename]["sha256"]:
                raise ContractError("Ordinary consumer input changed")
            command = [executable, *arguments]
            process = run_observed(command, cwd=output, env=env, log_path=output / f"{name}.log",
                                   result_path=output / f"{name}.native-job.json",
                                   relay_records=output / "native-exits", timeout=120, driver_prefix=old / "observer")
            report["steps"].append({"name": name, "command": list(map(str, command)), "process": process,
                                    "log_sha256": digest(output / f"{name}.log")})
            if not process["passed"] or marker not in (output / f"{name}.log").read_text():
                raise ContractError(f"Ordinary native SQLite consumer failed: {name}")
        report["status"] = "ordinary-native-sqlite-combined-runtime-apis-passed"
    finally:
        verify_files(runtime, prepared["runtime_files"])
        if digest(args.prepared / "prepare.json") != args.sha256:
            raise ContractError("Prepared runtime receipt changed")
        report["inputs_unchanged"] = True
        launcher.write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "result": str(output / "result.json"),
                      "sha256": digest(output / "result.json")}))


if __name__ == "__main__":
    main()
