"""Observe real native-shell SQLite consumers and check database/DLL identity."""

import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys

from native_job_runner import run_observed, verify_driver
from sources import ContractError, digest, inventory
from sqlite_consumer_inputs import sealed_json, verify_files
from sqlite_build_inputs import msys_path
from ssh_bootstrap import require_memory

spec = importlib.util.spec_from_file_location("sqlite_launch", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def verify_database(path, query, expected):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        actual = db.execute(query).fetchall()
    if actual != expected:
        raise ContractError(f"Native SQLite consumer data mismatch: {path}: {actual}")
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    output = args.prepared.resolve()
    root = Path(r"C:\ag-sqlite-resume-01")
    if not output.is_relative_to(root) or (output / "result.json").exists():
        raise ContractError("An unused private prepared consumer is required")
    manifest = output / "prepare.json"
    prepared = sealed_json(manifest, args.sha256)
    if prepared["status"] != "private-native-sqlite-shell-consumer-prepared-not-executed":
        raise ContractError("Consumer preparation is incomplete")
    runtime = output / "runtime"
    verify_files(runtime, prepared["runtime"]["files"])
    if prepared.get("required_runtime_directories") != ["tmp"]:
        raise ContractError("Private runtime must declare its required /tmp directory")
    if not (runtime / "tmp").is_dir() or (runtime / "tmp").is_symlink() or (runtime / "tmp").is_junction():
        raise ContractError("Private runtime /tmp must be a real local directory")
    verify_files(output / "inputs", prepared["fixture_files"])
    old = Path(r"C:\ag-sqlite-e138-01")
    observer_manifest = verify_driver(old / "observer")
    if digest(observer_manifest) != "1f5384459cc239e0b373b05f42e60ef06ec580d45046e1484a4ba4d46de5b3fa":
        raise ContractError("Unexpected observer: do not promote high raw exits")
    if digest(sys.executable) != "7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29":
        raise ContractError("Exact native Python required")
    env = launcher.environment(old, output, 1)
    env.update(PATH=os.pathsep.join(map(str, (runtime / "usr/bin", Path(os.environ["SystemRoot"]) / "System32"))),
               HOME=msys_path(output / "home"), TMP=str(output / "temp"), TEMP=str(output / "temp"),
               TMPDIR=msys_path(output / "temp"), TCL_LIBRARY=msys_path(runtime / "usr/lib/tcl8.6"),
               TCLLIBPATH=msys_path(runtime / "usr/lib"), WOARM64_NATIVE_TEST_ROOT=str(output))
    bash = runtime / "usr/bin/bash.exe"
    script = msys_path(output / "inputs/sqlite-shell-consumer.sh")
    report = {"schema": 1, "status": "failed", "launcher": launcher.process_identity(),
              "jobs": 1, "minimum_free_ram_gib": require_memory(),
              "prepare_sha256": args.sha256, "runtime_sha256": prepared["runtime"]["runtime_sha256"],
              "bash_candidate_sha256": prepared["runtime"]["bash_sha256"],
              "scope": "Targeted native-shell/runtime-substitution SQLite consumer proof; not full Bash/SQLite/upstream admission",
              "provider_admission": False, "full_upstream_qualified": False, "steps": []}
    launcher.write_json(output / "launch.json", report)
    print(json.dumps({"launcher": report["launcher"], "log_root": str(output)}), flush=True)
    try:
        for name in ("ordinary", "captured"):
            command = [bash, "--noprofile", "--norc", script, msys_path(output), name]
            if name == "captured":
                command = [sys.executable, "-B", Path(__file__).with_name("capture-native-exception.py"),
                           "--executable", bash, "--output", output / "capture",
                           "--path-directory", runtime / "usr/bin", "--tcl-environment",
                           "--", "--noprofile", "--norc", script, msys_path(output), name]
            step = {"name": name, "command": list(map(str, command))}
            step["process"] = run_observed(command, cwd=output / "work", env=env,
                                           log_path=output / f"{name}.log",
                                           result_path=output / f"{name}.native-job.json",
                                           relay_records=output / "native-exits", timeout=120,
                                           driver_prefix=old / "observer")
            report["steps"].append(step)
            text = (output / f"{name}.log").read_text(encoding="utf-8", errors="replace")
            if name == "captured":
                details = json.loads((output / "capture/result.json").read_text())
                step["raw_target_exit"] = details["exit_code"]
                text = (output / "capture/stdout.bin").read_text(encoding="utf-8", errors="replace")
                if details["exit_code"] != 0 or details["timed_out"] or details["exception_limit_reached"]:
                    raise ContractError("Native Bash capture failed; ordinary result remains independent")
                loaded = {}
                for entry in details["modules"]:
                    path = Path(entry["path"].removeprefix("\\\\?\\")).resolve()
                    if path.is_relative_to(runtime):
                        rel = path.relative_to(runtime).as_posix()
                        if digest(path) != prepared["runtime"]["files"][rel]["sha256"]:
                            raise ContractError("Captured native module differs from prepared payload")
                    elif not path.is_relative_to(Path(os.environ["SystemRoot"])):
                        raise ContractError(f"Foreign module outside private runtime: {path}")
                    loaded[path.name.lower()] = {"path": str(path), "sha256": digest(path)}
                step["loaded_modules"] = loaded
                if (loaded["msys-2.0.dll"]["sha256"] != report["runtime_sha256"]
                        or loaded["bash.exe"]["sha256"] != report["bash_candidate_sha256"]):
                    raise ContractError("Native parent runtime/Bash identity mismatch")
            if not step["process"]["passed"] or "native-msys-sqlite-shell-consumer-passed" not in text:
                raise ContractError(f"Native shell consumer failed: {name}")
            step["import_rows"] = verify_database(output / "work" / name / "import.sqlite",
                                                 "SELECT x,y FROM t1 ORDER BY CAST(x AS INTEGER)",
                                                 [(str(i), f"this is {i}") for i in range(1, 6)])
            step["tdbc_rows"] = verify_database(output / "work" / name / "tdbc-candidate.sqlite",
                                               "SELECT id,value FROM records ORDER BY id",
                                               [(1, "native \u03bb \u96ea"), (3, "committed")])
            observed = json.loads((output / f"{name}.native-job.json").read_text())
            executables = {Path(p["executable"]).name.lower() for p in observed["native_target_exits"]}
            required = {"bash.exe", "sh.exe", "awk.exe", "sqlite3.exe", "tclsh8.6.exe", "sqlite-shell-pipe.exe"}
            if not required.issubset(executables):
                raise ContractError(f"Actual native consumer process coverage missing: {required - executables}")
            step["native_executables"] = sorted(executables)
        report["status"] = "native-msys-sqlite-shell-and-tdbc-consumers-passed-candidate-composition"
    finally:
        verify_files(runtime, prepared["runtime"]["files"])
        verify_files(output / "inputs", prepared["fixture_files"])
        if digest(manifest) != args.sha256:
            raise ContractError("Consumer preparation receipt changed")
        report["input_integrity_passed"] = True
        launcher.write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "result": str(output / "result.json"),
                      "sha256": digest(output / "result.json")}))


if __name__ == "__main__":
    main()
