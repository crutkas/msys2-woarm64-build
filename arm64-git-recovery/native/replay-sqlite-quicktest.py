"""Replay the entire upstream quicktest with explicit private host/target paths."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil

from native_job_runner import run_observed
from sources import ContractError, digest, inventory, verify_tree
from sqlite_build_inputs import msys_path

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("build-msys-sqlite.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
root = Path(r"C:\ag-sqlite-e138-01")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--build", type=Path, required=True)
args = parser.parse_args()
output, build, source = args.output.resolve(), args.build.resolve(), root / "host-source-05"
if any(not p.is_relative_to(root) for p in (output, build)):
    raise ContractError("Fresh private quicktest outputs required")
output.mkdir()
build.mkdir()
(output / "native-exits").mkdir()
(output / "verbose").mkdir()
verify_tree(source, root / "host-source-05.inventory.json")
original = root / "build-06"
# Keep the original quicktest database/logs and failed fixtures untouched.
# Copy only the configured/generated build products that quicktest depends on.
names = ("Makefile", "sqlite_cfg.h", "sqlite3.pc", "sqlite3.c", "sqlite3.h", "sqlite3ext.h",
         "sqlite3.o", "ctime.c", "pragma.h", "parse.c", "parse.h", "opcodes.c", "opcodes.h",
         "keywordhash.h", "fts5.c", "fts5.h", "shell.c", "lemon.exe", "lempar.c",
         "mkkeywordhash.exe", "mksourceid.exe", "src-verify.exe", "srcck1.exe",
         "tclsqlite-ex.c", "tclsqlite.o", "tclsqlite-shell.o", ".target_source",
         ".main.mk.checks", "cygsqlite3.53.4.dll", "pkgIndex.tcl", "msys-sqlite3-0.dll",
         "libsqlite3.a", "libsqlite3.dll.a", "sqlite3.exe", "testfixture.exe")
copied = {}
for name in names:
    path = original / name
    if not path.is_file():
        raise ContractError(f"Required real quicktest input missing: {name}")
    shutil.copy2(path, build / name)
    copied[name] = digest(path)
shutil.copytree(original / "tsrc", build / "tsrc")
env = launcher.environment(root, output, 1)
env.update(SQLITE_TEST_SHELL_INIT=msys_path(Path(__file__).with_name("sqlite-test-environment-02.sh")),
           SQLITE_TEST_EXIT_DIR=msys_path(output / "native-exits"),
           SQLITE_TEST_VERBOSE_DIR=msys_path(output / "verbose"))
script = Path(__file__).with_suffix(".sh")
command = [root / "bootstrap/usr/bin/bash.exe", "--noprofile", "--norc", script.resolve().as_posix(),
           str(root), str(build), str(source)]
report = {"schema": 1, "status": "failed", "scope": "All original quicktest jobs; only explicit host/path transport fixes",
          "jobs": 1, "nested_jobs": 1, "launcher": launcher.process_identity(), "command": list(map(str, command)),
          "source_manifest_sha256": digest(root / "host-source-05.inventory.json"),
          "copied_build_inputs": copied, "minimum_free_gib": launcher.require_memory()}
launcher.write_json(output / "launch.json", report)
print(json.dumps({"launch": report["launcher"], "command": report["command"], "log": str(output / "build.log")}), flush=True)
try:
    report["process"] = run_observed(command, cwd=build, env=env, log_path=output / "build.log",
                                     result_path=output / "native-job.json", relay_records=output / "native-exits",
                                     timeout=14400, driver_prefix=root / "observer")
    report["status"] = "upstream-quicktest-passed" if report["process"]["passed"] else "upstream-quicktest-failed"
finally:
    verify_tree(source, root / "host-source-05.inventory.json")
    if any(digest(original / name) != sha for name, sha in copied.items()):
        report["status"] = "failed-original-build-input-changed"
    report["test_evidence"] = {p.name: digest(p) for p in build.glob("testrunner.*") if p.is_file()}
    report["verbose_files"] = {p.name: digest(p) for p in (output / "verbose").glob("*.txt")}
    launcher.write_json(output / "result.json", report)
if report["status"] != "upstream-quicktest-passed":
    raise SystemExit(1)
