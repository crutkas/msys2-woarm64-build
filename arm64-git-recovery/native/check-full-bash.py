"""Run every upstream Bash default test case, retaining outputs and raw native observations."""

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import sys

from bash_chain_inputs import ROOT, HERE, fresh
from readline_chain_inputs import SEALS, sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory, write_json

nls = importlib.import_module("build-bash-nls")


def main(args):
    root = ROOT / args.build
    stage = root / "stage"
    stage_manifest = root / "stage.inventory.json"
    sdk = ROOT / args.sdk
    output = ROOT / args.output
    fresh(output)
    verify_tree(stage, stage_manifest)
    verify_tree(sdk, sdk.parent / "stage.inventory.json")
    if json.loads(stage_manifest.read_text())["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Wrong native Bash test cohort")
    output.mkdir()
    for name in ("home", "temp", "cache", "cases", "native-exits", "recipes"):
        (output / name).mkdir()
    runtime = output / "runtime"
    binaries = runtime / "usr/bin"
    binaries.mkdir(parents=True)
    for directory in ("tmp", "var/tmp", "etc"):
        (runtime / directory).mkdir(parents=True)
    copied = {}
    for provider in (nls.terminal.COMPILER / "bin", sdk / "usr/bin"):
        for file in provider.glob("msys-*.dll"):
            target = binaries / file.name
            if target.exists() and digest(target) != digest(file):
                raise ContractError("Conflicting private Bash test DLL")
            shutil.copyfile(file, target)
            copied[file.name] = {"source": str(file), "sha256": digest(file)}
    for name in ("bash.exe", "sh.exe"):
        shutil.copyfile(stage / "usr/bin" / name, binaries / name)
        copied[name] = {"source": str(stage / "usr/bin" / name), "sha256": digest(binaries / name)}
    sealed(binaries / "msys-2.0.dll", nls.terminal.RUNTIME_SHA)
    if (stage / "usr/share/locale").exists():
        shutil.copytree(stage / "usr/share/locale", runtime / "usr/share/locale")
    script = HERE / "check-full-bash.sh"
    patch = HERE / "patches/bash-5.3-record-all-tests.patch"
    for file in (script, patch, HERE / "check-full-bash.py"):
        shutil.copyfile(file, output / "recipes" / file.name)
    test_directory = root / "source/tests"
    expected = sorted(p.name for p in test_directory.glob("run-*")
                      if p.name not in ("run-all", "run-minimal", "run-gprof") and not p.name.endswith((".orig", "~")))
    if not expected:
        raise ContractError("Bash upstream test discovery is empty")
    command = [nls.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc",
               script.as_posix(), root, output, sdk, nls.BOOTSTRAP]
    report = {"schema": 1, "status": "launched", "pid": os.getpid(),
              "creation_filetime": nls.terminal.current_birth(), "command": list(map(str, command)),
              "jobs": 1, "minimum_free_gib": require_memory(), "expected_cases": expected,
              "stage_manifest_sha256": digest(stage_manifest), "compiler_receipt_sha256": SEALS["compiler"],
              "copied_inputs": copied, "scope": "Every default upstream run-* case; existing minimal/gprof exclusions unchanged; all outputs retained, no failure waiver"}
    write_json(output / "launch.json", report)
    print(json.dumps(report), flush=True)
    try:
        with nls.cpu_budget(1) as budget:
            report["cpu_budget"] = budget
            report["process"] = nls.run_observed(command, cwd=output, env=nls.environment(output, 1),
                                                 log_path=output / "observed.log", result_path=output / "native-job.json",
                                                 relay_records=output / "native-exits", timeout=14400,
                                                 driver_prefix=nls.terminal.OBSERVER)
        results_file = output / "cases/results.tsv"
        if results_file.exists():
            results = [line.split("\t") for line in results_file.read_text().splitlines()]
            report["case_results"] = [{"name": name, "exit": int(code)} for name, code in results]
            if sorted(name for name, _ in results) != expected:
                raise ContractError("Not every required Bash test case completed")
            if any(int(code) for _, code in results):
                raise ContractError("Bash upstream case failure; per-case evidence retained")
        else:
            raise ContractError("Upstream Bash case accounting was not produced")
        if not report["process"]["passed"]:
            raise ContractError("Bash upstream native observation did not pass")
        report["status"] = "Bash-upstream-cases-complete-output-anomaly-review-required"
        report["case_evidence"] = inventory(output / "cases")
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        verify_tree(stage, stage_manifest)
        verify_tree(sdk, sdk.parent / "stage.inventory.json")
        write_json(output / "result.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--output", required=True)
    main(parser.parse_args())
