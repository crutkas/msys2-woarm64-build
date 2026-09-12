"""Matched private relinks testing scratch isolation without changing libgcc."""

import json
import os
from pathlib import Path
import sys

from resume import ROOT, OLD, copy_locked, digest, free_memory, load, verify_inputs, write

TC = Path(r"C:\ag-e138920f\tc-cpp-guard-01")
sys.path.insert(0, str(ROOT / "support"))
from bounded_process import run
from native_job_runner import noninteractive_error_mode


def main():
    verify_inputs()
    expected = {path: sha for path, sha in load(OLD / "inputs.json")["tool_inputs_before"].items()
                if Path(path).is_relative_to(TC)}
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Compiler input changed: {path}")
    build = ROOT / "scratch-build"
    build.mkdir(exist_ok=False)
    source = Path(__file__).with_name("unwind_context.c")
    copies = [copy_locked(source, build / source.name, digest(source))]
    for name, runtime in (("relink", ROOT / "baseline/usr/bin/msys-2.0.dll"),
                          ("scratch", ROOT / "baseline/usr/bin/msys-2.0.dll"),
                          ("scratch-d70", ROOT / "d70/usr/bin/msys-2.0.dll")):
        for path, rel in ((runtime, Path("usr/bin/msys-2.0.dll")),
                          (ROOT / "baseline/etc/fstab", Path("etc/fstab"))):
            copies.append(copy_locked(path, ROOT / name / rel, digest(path)))
    gcc, gxx = str(TC / "bin/gcc.exe"), str(TC / "bin/g++.exe")
    commands = [
        ("fixture-object", [gxx, "-O0", "-g", "-c", str(ROOT / "fixture.cpp"), "-o", str(build / "fixture.o")]),
        ("scratch-object", [gcc, "-std=c11", "-O0", "-g", "-c", str(build / "unwind_context.c"),
                            "-o", str(build / "unwind_context.o")]),
        ("relink-control", [gxx, "-static-libgcc", "-static-libstdc++", str(build / "fixture.o"),
                            "-o", str(ROOT / "relink/usr/bin/exception-fixture.exe")]),
        ("scratch-candidate", [gxx, "-static-libgcc", "-static-libstdc++", str(build / "fixture.o"),
                               str(build / "unwind_context.o"), "-Wl,--wrap=__imp_RtlUnwindEx",
                               "-o", str(ROOT / "scratch/usr/bin/exception-fixture.exe")]),
    ]
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join([str(TC / "bin"), str(Path(env["SystemRoot"]) / "System32")]),
                "TMP": str(build), "TEMP": str(build), "HOME": str(build), "USERPROFILE": str(build)})
    records = []
    for name, argv in commands:
        memory = free_memory()
        with noninteractive_error_mode(), (build / f"{name}.log").open("xb") as log:
            result = run(argv, cwd=build, env=env, log=log, timeout=120)
        record = {"name": name, "command": argv, "result": result,
                  "free_before": memory, "free_after": free_memory()}
        write(build / f"{name}.json", record)
        records.append(record)
        if not result["passed"]:
            raise RuntimeError(f"Private relink failed: {name}")
    fixture = ROOT / "scratch/usr/bin/exception-fixture.exe"
    copies.append(copy_locked(fixture, ROOT / "scratch-d70/usr/bin/exception-fixture.exe", digest(fixture)))
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Compiler input changed during private build: {path}")
    outputs = {str(ROOT / name / "usr/bin/exception-fixture.exe"):
               digest(ROOT / name / "usr/bin/exception-fixture.exe") for name in ("relink", "scratch", "scratch-d70")}
    write(build / "result.json", {"schema": 1, "status": "private-link-only-scratch-control-built",
          "builds": records, "copies": copies, "outputs": outputs, "tool_inputs_before_after": expected,
          "same_fixture_object": {"path": str(build / "fixture.o"), "sha256": digest(build / "fixture.o")},
          "libgcc_changed": False, "runtime_changed": False, "compiler_changed": False,
          "qualified_producer": False, "provider_admission": False})
    print(json.dumps({"builds": len(records), "outputs": outputs}))


if __name__ == "__main__":
    main()
