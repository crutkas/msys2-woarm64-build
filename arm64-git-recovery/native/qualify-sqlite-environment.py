"""Compare real inherited/Tcl-mutated/C-setenv exports; never infer a pass from raw zero."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

from native_job_runner import run_observed
from sources import ContractError, digest, verify_tree
from sqlite_build_inputs import msys_path

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
root = Path(r"C:\ag-sqlite-e138-01")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
if not output.is_relative_to(root):
    raise ContractError("Private differential output required")
output.mkdir()
(output / "native-exits").mkdir()
fixtures = output / "inputs"
fixtures.mkdir()
for path in (Path(__file__).parent / "fixtures").glob("sqlite-env-*"):
    shutil.copyfile(path, fixtures / path.name)
exe = output / "native-env.exe"
env = launcher.environment(root, output, 1)
marker = output / "path-marker"
marker.mkdir()
env["PATH"] = os.pathsep.join(map(str, (marker, root / "tcl/usr/bin", root / "compiler/bin", root / "bootstrap/usr/bin",
                                      Path(os.environ["SystemRoot"]) / "System32")))
env.update(WOARM64_ENV_INHERITED="inherited-marker", CCACHE_DISABLE="1", MSYSTEM="CYGWIN")
env.pop("WOARM64_ENV_NEW", None)
report = {"schema": 1, "status": "diagnostic-only", "scope": "Synthetic inherited and mutated POSIX vs Windows environment, same-runtime/foreign-MSYS/native-Windows children",
          "launcher": launcher.process_identity(), "jobs": 1, "max_simultaneous_parent_and_child": 2,
          "minimum_free_gib": launcher.require_memory(), "steps": []}
launcher.write_json(output / "launch.json", report)
print(json.dumps({"launch": report["launcher"], "log_root": str(output)}), flush=True)
commands = [
    ("compile", [root / "compiler/bin/gcc.exe", "-O2", "-g", "-fstack-protector-strong",
                 "-D_FORTIFY_SOURCE=2", fixtures / "sqlite-env-differential.c", "-o", exe]),
    ("tcl", [root / "tcl/usr/bin/tclsh8.6.exe", msys_path(fixtures / "sqlite-env-differential.tcl"),
             msys_path(exe), msys_path(root / "bootstrap/usr/bin/bash.exe"),
             msys_path(fixtures / "sqlite-env-child.sh"), Path(sys.executable).as_posix(),
             (fixtures / "sqlite-env-child.py").resolve().as_posix()]),
    ("c", [exe, msys_path(root / "bootstrap/usr/bin/bash.exe"), msys_path(fixtures / "sqlite-env-child.sh"),
           Path(sys.executable).as_posix(), (fixtures / "sqlite-env-child.py").resolve().as_posix()]),
]
try:
    for name, command in commands:
        process = run_observed(command, cwd=output, env=env, log_path=output / f"{name}.log",
                               result_path=output / f"{name}.native-job.json", relay_records=output / "native-exits",
                               timeout=120, driver_prefix=root / "observer")
        report["steps"].append({"name": name, "command": list(map(str, command)), "process": process,
                                "log_sha256": digest(output / f"{name}.log")})
        if name == "compile" and not process["passed"]:
            raise ContractError("Native environment fixture compilation failed")
    report["status"] = "environment-observations-collected-not-a-qualification-pass"
finally:
    verify_tree(root / "tcl", root / "tcl.inventory.json")
    verify_tree(root / "compiler", root / "compiler-runtime.inventory.json")
    report["input_source_hashes"] = {p.name: digest(p) for p in fixtures.glob("sqlite-env-*")}
    launcher.write_json(output / "result.json", report)
