"""Record the actual native Tcl to foreign host-driver environment boundary."""

import importlib.util
import json
import os
from pathlib import Path
import sys

from native_job_runner import run_observed
from sqlite_build_inputs import msys_path

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
root = Path(r"C:\ag-sqlite-e138-01")
output = root / "foreign-environment-01"
output.mkdir()
(output / "native-exits").mkdir()
env = launcher.environment(root, output, 1)
env["PATH"] = os.pathsep.join(map(str, (root / "tcl/usr/bin", root / "compiler/bin", root / "bootstrap/usr/bin",
                                      Path(os.environ["SystemRoot"]) / "System32")))
env.update(autosetup_tclsh=msys_path(root / "host-jim-01/jimsh.exe"),
           SQLITE_TEST_TCL_CONFIG=msys_path(root / "tcl-config-hostwin/tclConfig.sh"),
           CCACHE_DISABLE="1")
report = {"launcher": launcher.process_identity(), "steps": []}
launcher.write_json(output / "launch.json", report)
print(json.dumps(report["launcher"]), flush=True)
for name, command in (
    ("direct-host", [root / "host-jim-01/jimsh.exe", root / "host-source-02/autosetup/autosetup-test-tclsh"]),
    ("native-foreign", [sys.executable, "-B", Path(__file__).with_name("sqlite_tcl_relay.py"),
                        root / "tcl/usr/bin/tclsh8.6.exe",
                        msys_path(Path(__file__).parent / "fixtures/sqlite-foreign-environment.tcl"),
                        msys_path(root / "bootstrap/usr/bin/bash.exe"), msys_path(root / "host-jim-01/jimsh.exe"),
                        msys_path(root / "host-source-02/autosetup/autosetup-test-tclsh")]),
):
    report["steps"].append({"name": name, "command": list(map(str, command)), "process": run_observed(
        command, cwd=output, env=env, log_path=output / f"{name}.log", result_path=output / f"{name}.native-job.json",
        relay_records=output / "native-exits", timeout=60, driver_prefix=root / "observer")})
launcher.write_json(output / "result.json", report)
