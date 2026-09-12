"""Use the upstream administrative halt/njob commands without editing its database."""

import argparse
import importlib.util
import json
import os
from pathlib import Path

from native_job_runner import run_observed
from sources import ContractError
from sqlite_build_inputs import msys_path

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--runner", type=Path, required=True)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--operation", choices=("halt", "njob"), required=True)
parser.add_argument("--jobs", type=int, choices=(0, 1, 2))
args = parser.parse_args()
root = Path(r"C:\ag-sqlite-e138-01")
if any(not p.resolve().is_relative_to(root) for p in (args.runner, args.source, args.output)):
    raise ContractError("Only an owned upstream runner may be controlled")
if (args.operation == "njob") != (args.jobs is not None):
    raise ContractError("njob requires an explicit bounded job count")
args.output.mkdir()
(args.output / "native-exits").mkdir()
env = launcher.environment(root, args.output, 1)
env["PATH"] = os.pathsep.join(map(str, (root / "tcl/usr/bin", root / "bootstrap/usr/bin",
                                      Path(os.environ["SystemRoot"]) / "System32")))
command = [root / "build-06/testfixture.exe", msys_path(args.source / "test/testrunner.tcl"), args.operation]
if args.jobs is not None:
    command.append(str(args.jobs))
report = {"scope": "Upstream administrative control only, not test execution or a passing suite",
          "launcher": launcher.process_identity(), "command": list(map(str, command))}
launcher.write_json(args.output / "launch.json", report)
report["process"] = run_observed(command, cwd=args.runner, env=env, log_path=args.output / "control.log",
                                 result_path=args.output / "native-job.json", relay_records=args.output / "native-exits",
                                 timeout=60, driver_prefix=root / "observer")
launcher.write_json(args.output / "result.json", report)
print(json.dumps(report))
if not report["process"]["passed"]:
    raise SystemExit(1)
