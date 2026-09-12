"""Capture the unmodified native source-id generator failure without changing it."""

import importlib.util
import json
from pathlib import Path
import sys

from native_job_runner import run_observed
from sources import digest

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
root = Path(r"C:\ag-sqlite-e138-01")
output = root / "mksourceid-diagnostic-01"
output.mkdir()
(output / "native-exits").mkdir()
env = launcher.environment(root, output, 1)
exe = root / "build-06/mksourceid.exe"
report = {"launcher": launcher.process_identity(), "sha256": digest(exe), "steps": []}
launcher.write_json(output / "launch.json", report)
print(json.dumps(report["launcher"]), flush=True)
for name, command, cwd in (
    ("ordinary", [exe, "manifest"], root / "prepared/source"),
    ("capture", [sys.executable, "-B", Path(__file__).with_name("capture-native-exception.py"),
                 "--executable", exe, "--output", output / "capture",
                 "--path-directory", root / "compiler/bin",
                 "/c/ag-sqlite-e138-01/prepared/source/manifest"], output),
):
    report["steps"].append({"name": name, "command": list(map(str, command)),
                            "process": run_observed(
        command, cwd=cwd, env=env, log_path=output / f"{name}.log",
        result_path=output / f"{name}.native-job.json", relay_records=output / "native-exits",
        timeout=60, driver_prefix=root / "observer")})
launcher.write_json(output / "result.json", report)
