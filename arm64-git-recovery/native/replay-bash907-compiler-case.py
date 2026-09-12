"""Replay one real upstream compiler-dependent case with a copied AA64 test compiler."""

import importlib
import json
import os
from pathlib import Path
import shutil
import sys

from native_job_runner import run_observed
from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory, write_json

common = importlib.import_module("bash907-common")
ROOT = common.ROOT


def main(name):
    if name not in ("run-glob-bracket",):
        raise ContractError("Only the evidenced missing-compiler upstream case may be replayed")
    output = ROOT / (name + "-native-compiler-01")
    if output.exists():
        raise ContractError("Fresh supplemental compiler-dependent case required")
    output.mkdir()
    for part in ("home", "temp", "native-exits"):
        (output / part).mkdir()
    shutil.copytree(ROOT / "runtime", output / "runtime")
    source = output / "source"
    shutil.copytree(common.prepare.BASH_ROOT / "source", source)
    compiler = common.combined.ROOT / "compiler"
    compiler_record = json.loads((common.combined.ROOT / "inputs.json").read_text())
    if inventory(compiler) != compiler_record["compiler_files"]:
        raise ContractError("Sealed native907 compiler copy differs")
    added = {}
    for relative, row in compiler_record["compiler_files"].items():
        if "sha256" not in row:
            raise ContractError("Test compiler copy requires regular files")
        target = output / "runtime/usr" / relative
        if target.exists():
            if digest(target) != row["sha256"]:
                raise ContractError(f"Compiler/test-subject collision: {relative}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(compiler / relative, target)
            common.combined.sealed(target, row["sha256"])
            added[relative] = row
    images = {}
    for path in (output / "runtime").rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                magic = stream.read(2)
            if magic == b"MZ":
                images[str(path.relative_to(output))] = {**common.prepare.terminal.pe(path.read_bytes()),
                                                        "sha256": digest(path), "bytes": path.stat().st_size}
    env = common.environment(output, output / "runtime")
    env.update(THIS_SH=str(output / "runtime/usr/bin/bash.exe").replace("\\", "/"),
               BUILD_DIR=str(source).replace("\\", "/"), BASH_TSTOUT=common.posix(output / "upstream.output"))
    command = [output / "runtime/usr/bin/sh.exe", name]
    report = {"schema": 1, "status": "running", "pid": os.getpid(), "creation_filetime": common.birth(),
              "command": list(map(str, command)), "environment": env, "jobs": 1,
              "runtime_sha256": common.combined.RUNTIME_SHA, "bash_sha256": common.prepare.BASH_SHA,
              "added_test_only_compiler_files": added, "pe_images": images, "minimum_free_gib": require_memory(),
              "original_raw_failure_not_replaced": str(ROOT / "upstream-suite-01/cases" / name / "native-job.json"),
              "scope": "Additional real upstreamcase with genuine copied AA64compiler, no Bash/library/runtime rebuild, no stubs or statusnormalization"}
    write_json(output / "launch.json", report)
    print(json.dumps({"pid": report["pid"], "creation_filetime": report["creation_filetime"], "command": report["command"]}), flush=True)
    try:
        with common.cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            report["observer"] = run_observed(command, cwd=source / "tests", env=env,
                                              log_path=output / "observed.log", result_path=output / "native-job.json",
                                              relay_records=output / "native-exits", timeout=900,
                                              driver_prefix=ROOT / "observer")
        report["raw_observation"] = json.loads((output / "native-job.json").read_text())
        report["status"] = "supplemental-raw-case-result"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "parent_raw_exit": report["raw_observation"]["parent_raw_exit"],
                      "observer_passed": report["observer"]["passed"]}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
