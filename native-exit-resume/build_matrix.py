"""Build matched original-library matrix fixtures with/without scratch isolation."""

import json
import os
from pathlib import Path
import sys

from resume import ROOT, copy_locked, digest, free_memory, load, verify_inputs, write
from build_scratch import TC
from bounded_process import run
from native_job_runner import noninteractive_error_mode


def main():
    verify_inputs()
    expected = load(ROOT / "scratch-build/result.json")["tool_inputs_before_after"]
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Compiler input changed: {path}")
    build = ROOT / "matrix-build"
    build.mkdir(exist_ok=False)
    source = Path(__file__).with_name("unwind_matrix.cpp")
    copies = [copy_locked(source, build / source.name, digest(source))]
    gxx = str(TC / "bin/g++.exe")
    commands = [
        ("compile", [gxx, "-O0", "-g", "-c", str(build / source.name), "-o", str(build / "matrix.o")]),
        ("relink", [gxx, "-static-libgcc", "-static-libstdc++", str(build / "matrix.o"),
                    "-o", str(ROOT / "relink/usr/bin/unwind-matrix.exe")]),
        ("scratch", [gxx, "-static-libgcc", "-static-libstdc++", str(build / "matrix.o"),
                     str(ROOT / "scratch-build/unwind_context.o"), "-Wl,--wrap=__imp_RtlUnwindEx",
                     "-o", str(ROOT / "scratch/usr/bin/unwind-matrix.exe")]),
    ]
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join([str(TC / "bin"), str(Path(env["SystemRoot"]) / "System32")]),
                "TMP": str(build), "TEMP": str(build), "HOME": str(build), "USERPROFILE": str(build)})
    receipts = []
    for name, argv in commands:
        memory = free_memory()
        with noninteractive_error_mode(), (build / f"{name}.log").open("xb") as log:
            result = run(argv, cwd=build, env=env, log=log, timeout=120)
        receipt = {"command": argv, "result": result, "free_before": memory, "free_after": free_memory()}
        receipts.append(receipt)
        write(build / f"{name}.json", receipt)
        if not result["passed"]:
            raise RuntimeError(f"Matrix build failed: {name}")
    path = ROOT / "scratch/usr/bin/unwind-matrix.exe"
    copies.append(copy_locked(path, ROOT / "scratch-d70/usr/bin/unwind-matrix.exe", digest(path)))
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Compiler changed: {path}")
    outputs = {str(ROOT / name / "usr/bin/unwind-matrix.exe"): digest(ROOT / name / "usr/bin/unwind-matrix.exe")
               for name in ("relink", "scratch", "scratch-d70")}
    write(build / "result.json", {"schema": 1, "builds": receipts, "copies": copies, "outputs": outputs,
          "same_matrix_object": {"path": str(build / "matrix.o"), "sha256": digest(build / "matrix.o")},
          "producer_changes": False})
    print(json.dumps({"outputs": outputs}))


if __name__ == "__main__":
    main()
