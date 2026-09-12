"""Real native PTY qualification of unchanged admitted Bash on combined runtime 907."""

import importlib
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

from bounded_process import run
from native_job_runner import noninteractive_error_mode, run_observed
from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory, write_json

common = importlib.import_module("bash907-common")
ROOT, HERE = common.ROOT, common.HERE
module_check = importlib.import_module("test-native-terminal-chain").process_modules
EXPECTED_CASES = [
    "native-shell-identity", "pipeline-status-default", "pipefail-status",
    "subshell-command-substitution", "heredoc-expansion", "heredoc-quoted",
    "globbing", "quoted-space-unicode-path", "msys-windows-path-roundtrip",
    "msys-native-path-translation", "readline-unicode-edit", "readline-history",
    "ctrl-c-at-prompt", "window-resize", "job-suspend", "job-background-resume",
    "job-foreground-ctrl-c-pipeline", "background-wait-status", "normal-exit-terminal-restored",
]


def worker(output):
    launch = json.loads((output / "launch.json").read_text())
    runtime = output / "runtime"
    binary = runtime / "usr/bin/bash.exe"
    driver = runtime / "usr/bin/bash907-pty.exe"
    env = common.environment(output, runtime)
    env.update(PS1="BASH907__> ", PS2="BASH907_CONT> ", HISTFILE=common.posix(output / "history"),
               PROMPT_COMMAND="", HISTCONTROL="")
    if launch["focus_jobs"]:
        env["BASH907_FOCUS_JOBS"] = "1"
    if launch["direct_group_signal"]:
        env["BASH907_DIRECT_GROUP_SIGNAL"] = "1"
    if launch["pipeline"]:
        env["BASH907_PIPELINE"] = launch["pipeline"]
    if launch["delivery_only"]:
        env["BASH907_DELIVERY_ONLY"] = "1"
    expected_cases = launch["expected_cases"]
    report = {"status": "running", "expected_cases": expected_cases}

    def observe(parent):
        deadline = time.monotonic() + 30
        ready = output / "editor-ready.json"
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready.exists():
            raise ContractError("Actual interactive Bash did not reach owned PTY prompt")
        child = json.loads(ready.read_text())["windows_pid"]
        expected = {"msys-2.0.dll": {"path": str(runtime / "usr/bin/msys-2.0.dll"),
                                    "sha256": launch["runtime_sha256"]}}
        report["controller_identity"] = module_check(parent, driver, expected)
        report["bash_identity"] = module_check(child, binary, expected)
        for identity in (report["controller_identity"], report["bash_identity"]):
            for row in identity["modules"]:
                path = Path(row["path"])
                if path.is_relative_to(runtime):
                    row["pe"] = common.prepare.terminal.pe(path.read_bytes())
                elif not path.is_relative_to(Path(os.environ["SystemRoot"]) / "System32"):
                    raise ContractError(f"Loaded module outside exact private/System32 closure: {path}")
        report["environment"] = env
        write_json(output / "held-modules.json", report)
        (output / "continue").write_bytes(b"go\n")

    try:
        with noninteractive_error_mode(), (output / "pty-controller.log").open("xb") as log:
            report["controller_process"] = run([driver, binary, output / "controller-result.json"],
                                                cwd=output, env=env, log=log, timeout=720,
                                                on_started=observe, drain_grace=3)
        report["controller_result"] = json.loads((output / "controller-result.json").read_text())
        rows = [line.split("\t") for line in (output / "cases.tsv").read_text().splitlines()]
        seen = {name: value for name, value in rows}
        report["cases"] = [{"name": name, "status": seen.get(name, "NOT_REACHED")} for name in expected_cases]
        report["counts"] = {"total": len(expected_cases), "passed": sum(v == "PASS" for v in seen.values()),
                            "failed": sum(v == "FAIL" for v in seen.values()),
                            "not_reached": len(expected_cases) - len(seen)}
        report["status"] = "interactive-native-semantics-passed" if (
            report["controller_process"]["passed"] and all(row["status"] == "PASS" for row in report["cases"])) else "interactive-native-failure"
    finally:
        write_json(output / "worker-result.json", report)
    raise SystemExit(0 if report["status"] == "interactive-native-semantics-passed" else 1)


def main(args):
    output = ROOT / args.output_name
    if output.exists():
        raise ContractError("Fresh interactive proof output required")
    inputs = json.loads((ROOT / "inputs.json").read_text())
    if inventory(ROOT / "runtime") != inputs["private_runtime_files"]:
        raise ContractError("Immutable Bash runtime/testtool input differs")
    output.mkdir()
    for name in ("home", "temp", "native-exits"):
        (output / name).mkdir()
    shutil.copytree(ROOT / "runtime", output / "runtime")
    runtime_sha = common.combined.RUNTIME_SHA
    if args.baseline_d70:
        old = common.prepare.BASE_SUITE / "runtime/usr/bin/msys-2.0.dll"
        runtime_sha = "d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d"
        common.combined.sealed(old, runtime_sha)
        shutil.copyfile(old, output / "runtime/usr/bin/msys-2.0.dll")
    source = HERE / "fixtures/native-bash907-pty.c"
    shutil.copyfile(source, output / source.name)
    driver = output / "runtime/usr/bin/bash907-pty.exe"
    compiler = common.combined.ROOT / "compiler"
    sdk_record = json.loads((common.combined.ROOT / "inputs.json").read_text())
    if inventory(compiler) != sdk_record["compiler_files"]:
        raise ContractError("907 fixture compiler/sysroot copy differs")
    command = [compiler / "bin/gcc.exe", "-O2", "-g", "-Werror", "-fstack-protector-strong",
               "-Wl,--no-insert-timestamp", "-Wl,-t", output / source.name, "-o", driver, "-lutil"]
    report = {"schema": 1, "status": "running", "pid": os.getpid(), "creation_filetime": common.birth(),
              "command": [sys.executable, *sys.argv], "compile_command": list(map(str, command)), "jobs": 1,
              "runtime_sha256": runtime_sha, "bash_sha256": common.prepare.BASH_SHA,
              "input_receipt_sha256": digest(ROOT / "inputs.json"), "source_sha256": digest(source),
              "minimum_free_gib": require_memory(),
              "focus_jobs": args.focus_jobs, "direct_group_signal": args.direct_group_signal,
              "pipeline": args.pipeline,
              "delivery_only": args.delivery_only,
              "baseline_d70": args.baseline_d70,
              "expected_cases": ([EXPECTED_CASES[0], *EXPECTED_CASES[16:]] if args.delivery_only else
                                 [EXPECTED_CASES[0], *EXPECTED_CASES[14:]] if args.focus_jobs else EXPECTED_CASES)}
    write_json(output / "launch.json", report)
    print(json.dumps({key: report[key] for key in ("pid", "creation_filetime", "command", "compile_command")}), flush=True)
    try:
        with common.cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            compiled = common.observed(command, output / "compile", output / "runtime", timeout=120, cwd=output)
            if not compiled["passed"]:
                raise ContractError("Native PTY controller compilation failed")
            report["fixture_pe"] = {**common.prepare.terminal.pe(driver.read_bytes()), "sha256": digest(driver)}
            report["process"] = common.observed([sys.executable, "-B", Path(__file__).resolve(), "--worker", output],
                                                 output / "run", output / "runtime", timeout=780, cwd=output)
        report["raw_observation"] = json.loads((output / "run/native-job.json").read_text())
        if (output / "worker-result.json").exists():
            report["semantics"] = json.loads((output / "worker-result.json").read_text())
        report["status"] = "complete-raw-interactive-evidence" if report.get("semantics") else "failed-before-semantic-result"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["bash_sha256_after"] = digest(output / "runtime/usr/bin/bash.exe")
        report["runtime_sha256_after"] = digest(output / "runtime/usr/bin/msys-2.0.dll")
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "counts": report.get("semantics", {}).get("counts"),
                      "observer_passed": report.get("process", {}).get("passed")}), flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(Path(sys.argv[2]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("output_name")
        parser.add_argument("--focus-jobs", action="store_true")
        parser.add_argument("--baseline-d70", action="store_true")
        parser.add_argument("--direct-group-signal", action="store_true")
        parser.add_argument("--pipeline")
        parser.add_argument("--delivery-only", action="store_true")
        main(parser.parse_args())
