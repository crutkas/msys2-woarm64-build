#!/usr/bin/env python3
"""Bound one native MSYS library stage and preserve its raw log/child drain."""
import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import runpy

RECIPE = Path(__file__).resolve().parent


@contextmanager
def noninteractive():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetErrorMode.restype = ctypes.c_uint
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]
    kernel.SetErrorMode.restype = ctypes.c_uint
    before = kernel.GetErrorMode()
    kernel.SetErrorMode(before | 0x8003)
    try:
        yield
    finally:
        kernel.SetErrorMode(before)
        if kernel.GetErrorMode() != before:
            raise RuntimeError("Owned process error mode was not restored")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    parser.add_argument("--successor", type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.runner.read_bytes()).hexdigest() != args.runner_sha256:
        parser.error("Bounded runner identity changed")
    root = args.root.resolve(strict=True)
    if bool(args.successor) != (args.stage == "libgcc-unwind"):
        parser.error("The isolated libgcc stage requires its own successor directory")
    evidence = args.successor.resolve(strict=True) if args.successor else root
    if args.successor:
        prepared = json.loads((evidence / "receipts" / "inputs.json").read_text())
        if Path(prepared["base"]).resolve() != root:
            parser.error("The successor was prepared against a different producer")
    log_path = evidence / "logs" / (args.run_id + ".bin")
    report_path = evidence / "logs" / (args.run_id + ".json")
    if log_path.exists() or report_path.exists():
        parser.error("Use a fresh stage evidence name")
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update(PATH=str(root / "bootstrap" / "usr" / "bin") + os.pathsep + str(root / "sdk" / "bin")
               + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               TMP=str(root / "tmp"), TEMP=str(root / "tmp"), MSYSTEM="MSYS", CHERE_INVOKING="1")
    run = runpy.run_path(str(args.runner))["run"]
    native = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    bash = root / "bootstrap" / "usr" / "bin" / "bash.exe"
    command = [str(bash), "--noprofile", "--norc", (root / "build-msys-shared-runtimes.sh").as_posix(),
               root.as_posix(), args.stage, str(args.jobs)]
    if args.successor:
        command.append(evidence.as_posix())
    observed = []
    print(f"Starting stage {args.stage}: {command}", flush=True)
    with log_path.open("wb") as log, noninteractive():
        process = run(command, cwd=root, env=env, log=log, timeout=args.timeout,
                      on_started=lambda pid: observed.append(native(pid, bash)))
    report = {"schema": 1, "stage": args.stage, "command": command, "process": process,
              "native_parent": observed, "log": str(log_path),
              "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256((root / "build-msys-shared-runtimes.sh").read_bytes()).hexdigest(),
              "root": str(root), "max_jobs": args.jobs}
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report_path, flush=True)
    if not process["passed"]:
        raise SystemExit(f"Stage failed: {process}")


if __name__ == "__main__":
    main()
