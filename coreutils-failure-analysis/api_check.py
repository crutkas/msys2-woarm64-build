"""Separate runtime API behavior from Coreutils algorithm behavior."""

import json
import os
from pathlib import Path
import sys

from inventory import ROOT, copy, digest, write
from replay import run, memory, bounded_run, noninteractive_error_mode

TC = Path(r"C:\ag-e138920f\tc-cpp-guard-01")
PREVIOUS = Path(r"C:\ag-exit-e138-01\resume-20260909-01")


def main():
    build = ROOT / "api-build"
    build.mkdir(exist_ok=False)
    source = Path(__file__).with_name("api-control.c")
    copies = []
    copy(source, build / source.name, copies)
    expected = json.loads((PREVIOUS / "scratch-build/result.json").read_text())["tool_inputs_before_after"]
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Frozen compiler input differs: {path}")
    executable = build / "api-control.exe"
    argv = [str(TC / "bin/gcc.exe"), "-O0", "-g", str(build / source.name), "-o", str(executable)]
    environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    environment.update({"PATH": os.pathsep.join([str(TC / "bin"), str(Path(environment["SystemRoot"]) / "System32")]),
                        "TMP": str(build), "TEMP": str(build)})
    before = memory()
    with noninteractive_error_mode(), (build / "build.log").open("xb") as log:
        result = bounded_run(argv, cwd=build, env=environment, log=log, timeout=90)
    write(build / "result.json", {"schema": 1, "command": argv, "result": result, "free_before": before,
                                 "free_after": memory(), "sources": copies})
    if not result["passed"]:
        raise RuntimeError("Runtime API diagnostic fixture did not build")
    for cohort in ("current-noacl", "current-acl"):
        copy(executable, ROOT / cohort / "usr/bin/api-control.exe", copies)
        run(cohort, "api-boundary-" + cohort, command="exec /usr/bin/api-control.exe", timeout=35)
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError("Compiler inputs changed")
    write(ROOT / "api-diagnostic-inputs.json", {"schema": 1, "copies": copies, "tool_inputs_unchanged": True,
          "scope": "Test-only calls to runtime APIs, not alternative rm/chmod implementations or a provider"})


if __name__ == "__main__":
    main()
