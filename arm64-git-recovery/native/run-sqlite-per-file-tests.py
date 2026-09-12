"""Run every upstream veryquick file independently with the existing native fixture."""

import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
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
parser.add_argument("--jobs", type=int, choices=(1, 2), required=True)
args = parser.parse_args()
output = args.output.resolve()
if not output.is_relative_to(root):
    raise ContractError("Private test output required")
output.mkdir()
(output / "native-exits").mkdir()
(output / "verbose").mkdir()
source = root / "host-source-05"
verify_tree(root / "prepared", root / "prepared.inventory.json")
verify_tree(source, root / "host-source-05.inventory.json")
copied = {}
for name in ("testfixture.exe", "sqlite3.exe"):
    path = root / "build-06" / name
    copied[name] = digest(path)
    shutil.copy2(path, output / name)
env = launcher.environment(root, output, 1)
env["PATH"] = os.pathsep.join(map(str, (root / "tcl/usr/bin", root / "readline/usr/bin",
                                      root / "ncurses/usr/bin", root / "zlib/usr/bin",
                                      root / "bootstrap/usr/bin", Path(os.environ["SystemRoot"]) / "System32")))
env.update(MAKEFLAGS="-j1", MFLAGS="-j1", TCLLIBDIR="/usr/lib/sqlite3.53.4",
           SQLITE_TEST_SHELL_INIT=msys_path(Path(__file__).with_name("sqlite-test-environment-02.sh")),
           SQLITE_TEST_EXIT_DIR=msys_path(output / "native-exits"),
           SQLITE_TEST_VERBOSE_DIR=msys_path(output / "verbose"))
command = [output / "testfixture.exe", msys_path(source / "test/testrunner.tcl"), "veryquick", "--jobs", str(args.jobs)]
report = {"schema": 1, "status": "failed", "scope": "All original veryquick test bodies with explicit private driver environment; existing full-profile fixture, not quicktest All-O0/All-Debug",
          "source_manifest_sha256": digest(root / "host-source-05.inventory.json"),
          "launcher": launcher.process_identity(), "jobs": args.jobs, "command": list(map(str, command)),
          "copied_inputs": copied, "minimum_free_gib": launcher.require_memory()}
launcher.write_json(output / "launch.json", report)
print(json.dumps({"launch": report["launcher"], "command": report["command"], "log": str(output / "build.log")}), flush=True)
try:
    report["process"] = run_observed(command, cwd=output, env=env, log_path=output / "build.log",
                                     result_path=output / "native-job.json", relay_records=output / "native-exits",
                                     timeout=14400, driver_prefix=root / "observer")
    database = output / "testrunner.db"
    if database.is_file():
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            report["states"] = dict(db.execute("SELECT state,count(*) FROM jobs GROUP BY state"))
            report["counts"] = dict(zip(("tests", "errors"), db.execute(
                "SELECT coalesce(sum(ntest),0),coalesce(sum(nerr),0) FROM jobs").fetchone()))
            report["failed_jobs"] = [
                {"name": name, "tests": tests, "errors": errors, "output": text}
                for name, tests, errors, text in db.execute(
                    "SELECT displayname,ntest,nerr,output FROM jobs WHERE state='failed' ORDER BY displayname")]
        if (report["process"]["passed"] and report["states"] and set(report["states"]) == {"done"}
                and not report["failed_jobs"] and not report["counts"]["errors"]):
            report["status"] = "native-upstream-veryquick-per-file-passed"
        else:
            report["status"] = "native-upstream-veryquick-per-file-failed"
finally:
    verify_tree(root / "prepared", root / "prepared.inventory.json")
    verify_tree(source, root / "host-source-05.inventory.json")
    if any(digest(root / "build-06" / name) != sha for name, sha in copied.items()):
        raise ContractError("Original testfixture input changed")
    report["evidence"] = {p.name: digest(p) for p in output.glob("testrunner.*") if p.is_file()}
    report["verbose_files"] = {p.name: digest(p) for p in (output / "verbose").glob("*.txt")}
    launcher.write_json(output / "result.json", report)
if report["status"] != "native-upstream-veryquick-per-file-passed":
    raise SystemExit(1)
