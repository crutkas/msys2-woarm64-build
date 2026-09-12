#!/usr/bin/env python3
"""Capture one owned myfault fixture with the preserved zero-write debugger."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "fixture", "runtime", "libgcc"):
        parser.add_argument("--" + name, type=Path, required=True)
        if name != "root":
            parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--mode", choices=("ordinary", "debug", "no-context"), default="debug")
    parser.add_argument("--seconds", type=int, choices=range(2, 21), default=10)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    manifest = json.loads((root / "inputs.json").read_text())
    for path, record in manifest["files"].items():
        if sha(root / path) != record["sha256"]:
            raise ValueError("Capture helper differs")
    fixture = root / "fixture"
    fixture.mkdir(exist_ok=False)
    files = {}
    for source, name, expected in ((args.fixture, "myfault.exe", args.fixture_sha256),
                                   (args.runtime, "msys-2.0.dll", args.runtime_sha256),
                                   (args.libgcc, "msys-gcc_s-seh-1.dll", args.libgcc_sha256)):
        if sha(source) != expected:
            raise ValueError(f"Capture input differs: {source}")
        shutil.copy2(source, fixture / name)
        files[name] = {"source": str(source), "sha256": expected}
    case = root / "case"
    case.mkdir(exist_ok=False)
    argv = [str(fixture / "myfault.exe")]
    if args.mode != "ordinary":
        argv = [sys.executable, "-B", str(root / "debug_tree.py"), "--output", str(case / "debug"),
                "--abi", str(root / "windows-abi.json"), "--timeout", str(args.seconds),
                *(["--no-context"] if args.mode == "no-context" else []), "--", *argv]
    command = [sys.executable, "-I", "-B", str(root / "driver/native-job.py"),
               "--cwd", str(case), "--target-root", str(root), "--relay-records", str(case / "relay"),
               "--log", str(case / "fixture.log"), "--result", str(case / "native-job.json"),
               "--timeout", str(args.seconds + 5), "--", *argv]
    env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
    env.update(PATH=str(fixture) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
               HOME=str(case), TMP=str(case), TEMP=str(case))
    sys.path.insert(0, str(root / "support"))
    try:
        bounded = runpy.run_path(str(root / "support/bounded_process.py"))["run"]
        quiet = runpy.run_path(str(root / "support/native_job_runner.py"))["noninteractive_error_mode"]
    finally:
        sys.path.pop(0)
    with (case / "outer.log").open("xb") as stream, quiet():
        result = bounded(command, cwd=case, env=env, log=stream, timeout=args.seconds + 10)
    report = {"schema": 1, "status": "myfault-capture-completed-not-qualified", "command": command,
              "mode": args.mode, "inputs": files, "process": result,
              "observer": json.loads((case / "native-job.json").read_text())}
    if args.mode != "ordinary":
        debug = json.loads((case / "debug/result.json").read_text())
        if debug["memory_writes"] or debug["register_writes"] or debug["unwind_probes"] is not None:
            raise ValueError("Capture was not zero-write")
        report["debug"] = {"path": str(case / "debug/result.json"), "sha256": sha(case / "debug/result.json")}
    for name, entry in files.items():
        if sha(fixture / name) != entry["sha256"] or sha(Path(entry["source"])) != entry["sha256"]:
            raise ValueError("Capture input changed")
    (root / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(root / "result.json")


if __name__ == "__main__":
    main()
