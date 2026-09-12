"""Build one non-shipping fixture that invokes the real stty on an owned PTY."""

import json
import os
from pathlib import Path
import sys

from qualify import ROOT, OLD, copy, digest, load, write
from exercise import memory_available
from bounded_process import run
from native_job_runner import noninteractive_error_mode

TC = Path(r"C:\ag-e138920f\tc-cpp-guard-01")


def main():
    build = ROOT / "pty-build"
    build.mkdir(exist_ok=False)
    source = Path(__file__).with_name("pty-control.c")
    copies = []
    copy(source, build / source.name, digest(source), copies, "test-source")
    expected = load(OLD / "scratch-build/result.json")["tool_inputs_before_after"]
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Compiler identity changed: {path}")
    argv = [str(TC / "bin/gcc.exe"), "-O0", "-g", str(build / source.name),
            "-o", str(ROOT / "private/usr/bin/pty-control.exe")]
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join([str(TC / "bin"), str(Path(env["SystemRoot"]) / "System32")]),
                "TMP": str(build), "TEMP": str(build), "HOME": str(build), "USERPROFILE": str(build)})
    before = memory_available()
    with noninteractive_error_mode(), (build / "build.log").open("xb") as log:
        result = run(argv, cwd=build, env=env, log=log, timeout=120)
    record = {"schema": 1, "command": argv, "result": result, "sources": copies,
              "shipping_payload": False, "free_before": before, "free_after": memory_available()}
    if result["passed"]:
        record["fixture_sha256"] = digest(ROOT / "private/usr/bin/pty-control.exe")
    write(build / "result.json", record)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
