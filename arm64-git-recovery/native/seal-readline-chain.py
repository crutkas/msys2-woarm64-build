"""Validate and bundle the completed private terminal-library chain without admission."""

from contextlib import redirect_stdout
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import unittest
import zipfile

from native_job_runner import run_observed, verify_driver
from readline_chain_inputs import ROOT, HERE, SEALS, fresh, sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json

build = importlib.import_module("build-readline-chain")
HANDOFFS = {
    "ncurses": ("ncurses-handoff-01", "eabe9fb4635cf4698c88c895bd4a138eb005efb7c789af1fbcfe908642c47003"),
    "readline": ("readline-handoff-01", "4fa5aeb8f7e86288e86f8076789c7a30a0475905319b97d235f1278c16261cb2"),
    "libedit": ("libedit-handoff-01", "b39c05d1201511d76545251af977d8417fd0bbc7c9140d0d716a69919e7427ff"),
}


def main():
    output = ROOT / "chain-handoff-01"
    fresh(output)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "ssh-tests"):
        (output / name).mkdir()
    os.environ.update(TMP=str(output / "temp"), TEMP=str(output / "temp"), SSH_TEST_ROOT=str(output / "ssh-tests"))
    report = {"schema": 1, "status": "validating", "pid": os.getpid(),
              "creation_filetime": build.current_birth(), "command": [sys.executable, *sys.argv],
              "minimum_free_gib": require_memory(), "jobs": 1, "full_package_or_shared_admission": False}
    print(json.dumps(report), flush=True)
    try:
        modules = ["test_readline_chain", "test_native_job_runner", "test_bounded_process",
                   "test_posix_package", "test_ssh_bootstrap", "test_ssh_build_inputs"]
        suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
        with (output / "unit-tests.log").open("x", encoding="utf-8") as log, redirect_stdout(log):
            result = unittest.TextTestRunner(stream=log).run(suite)
        report["unit_tests"] = {"count": result.testsRun, "passed": result.wasSuccessful(),
                                "modules": modules, "log_sha256": digest(output / "unit-tests.log")}
        if not result.wasSuccessful():
            raise ContractError("Maintained chain/helper tests failed")
        report["shell_syntax"] = []
        for index, script in enumerate(sorted(HERE.glob("*.sh"))):
            if b"\r" in script.read_bytes():
                raise ContractError(f"Shell driver is not LF: {script.name}")
            command = [build.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", "-n", script.as_posix()]
            observation = run_observed(command, cwd=output, env=build.environment(output, 1),
                                       log_path=output / f"syntax-{index}.log",
                                       result_path=output / f"syntax-{index}.native-job.json",
                                       relay_records=output / "native-exits", timeout=60, driver_prefix=build.OBSERVER)
            report["shell_syntax"].append({"file": script.name, "sha256": digest(script), "process": observation})
            if not observation["passed"]:
                raise ContractError(f"Native bootstrap shell syntax check failed: {script.name}")
        sealed(build.COMPILER_RECEIPT, SEALS["compiler"])
        verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
        verify_tree(build.BOOTSTRAP, build.BOOTSTRAP_RECEIPT)
        bootstrap = json.loads(build.BOOTSTRAP_RECEIPT.read_text())
        if directory_names(build.BOOTSTRAP) != bootstrap["directories"]:
            raise ContractError("Frozen private bootstrap directory tree changed")
        sealed(verify_driver(build.OBSERVER), SEALS["observer"])
        sealed(sys.executable, build.PYTHON_SHA)
        report["packages"] = {}
        for package, (directory, expected) in HANDOFFS.items():
            handoff = ROOT / directory / "handoff.json"
            sealed(handoff, expected)
            record = json.loads(handoff.read_text())
            sealed(record["stage_manifest"], record["stage_manifest_sha256"])
            count = verify_tree(record["stage"], record["stage_manifest"])
            source_manifest = ROOT / "sources" / package / "source.prepare.json"
            sealed(source_manifest, SEALS[package])
            verify_tree(ROOT / "sources" / package / "source", source_manifest)
            report["packages"][package] = {"handoff": str(handoff), "handoff_sha256": expected,
                                           "stage": record["stage"], "stage_manifest": record["stage_manifest"],
                                           "stage_manifest_sha256": record["stage_manifest_sha256"],
                                           "files": count, "status": record["status"]}
        files = inventory(HERE)
        archive = output / "maintained-native-chain.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, row in files.items():
                if "sha256" not in row:
                    raise ContractError("Maintained bundle requires regular files")
                bundle.write(HERE / name, name)
        with zipfile.ZipFile(archive) as bundle:
            if set(bundle.namelist()) != set(files):
                raise ContractError("Maintained bundle member inventory differs")
            for name, row in files.items():
                if hashlib.sha256(bundle.read(name)).hexdigest() != row["sha256"]:
                    raise ContractError(f"Maintained bundle content differs: {name}")
        if inventory(HERE) != files:
            raise ContractError("Maintained code changed while sealing")
        write_json(output / "maintained-files.json", {"source": str(HERE), "files": files})
        observations = []
        for path in sorted(ROOT.rglob("*.json")):
            if not (path.name == "native-job.json" or path.name.endswith(".native-job.json")
                    or path.name.startswith("compile-")):
                continue
            value = json.loads(path.read_text())
            if "parent_pid" not in value:
                continue
            observations.append({"path": str(path), "sha256": digest(path),
                                 "parent_pid": value["parent_pid"], "parent_raw_exit": value["parent_raw_exit"],
                                 "passed": value["passed"], "created": value["created_processes"],
                                 "observed": value["observed_processes"],
                                 "unrelayed_high_exit_count": len(value["unrelayed_high_exits"])})
        write_json(output / "observations.json", observations)
        report.update({
            "status": "private-native-ncurses-readline-libedit-chain-complete",
            "bundle": {"path": str(archive), "sha256": digest(archive), "files": len(files)},
            "maintained_manifest_sha256": digest(output / "maintained-files.json"),
            "observations_manifest_sha256": digest(output / "observations.json"),
            "helper_import": {"path": str(ROOT / "helper-import.json"), "sha256": digest(ROOT / "helper-import.json")},
            "compiler_receipt_sha256": SEALS["compiler"], "runtime_sha256": build.RUNTIME_SHA,
            "full_cpp_qualified": False, "bootstrap_receipt_sha256": digest(build.BOOTSTRAP_RECEIPT),
            "observer_manifest_sha256": SEALS["observer"], "input_integrity_unchanged": True,
            "remaining_gates": [
                "Pipeline-owned genuine packages/signing/install/shared admission",
                "Ncurses relative terminfo package symlink: existing-destination/type/order boundary, not missing-privilege evidence",
                "Parent-owned full Bash/readline/gettext-NLS and SQLite/Heimdal/OpenSSH integration",
                "Libedit inherited supplementary UTF-16 and changing-only-ignored-prompt-bytes behavior is not newly qualified",
            ],
            "execution_boundary": {"aggregate_grant": 2, "code_only_subagent_execution_jobs": 0,
                                   "factories": 0, "commits_push_pr_ci": False, "global_settings_changed": False},
        })
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        write_json(output / "handoff.json", report)
    print(json.dumps({"path": str(output / "handoff.json"), "sha256": digest(output / "handoff.json"),
                      "status": report["status"], "bundle_sha256": report["bundle"]["sha256"]}), flush=True)


if __name__ == "__main__":
    main()
