"""Resume pinned library work with narrow, sealed source fixes and new observations."""

import argparse
import importlib
import json
import os
import shutil
import sys

from native_job_runner import run_observed
from readline_chain_inputs import ROOT, HERE, SEALS, fresh, sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory, write_json

build = importlib.import_module("build-readline-chain")
PATCHES = {
    "readline": ("readline-8.3-history-example-link.patch", "examples/Makefile.in"),
    "libedit": ("libedit-20240808-read-ioctl.patch", "src/read.c"),
}


def main(package):
    print(json.dumps({"pid": os.getpid(), "creation_filetime": build.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    root = ROOT / (package + "-01")
    output = root / "finish-02"
    fresh(output)
    original = json.loads((root / "native-job.json").read_text())
    if (original["parent_raw_exit"] != 2 or original["timed_out"] or not original["observation_count_matches"]
            or original["unobserved_process_ids"] or original["unrelayed_high_exits"]):
        raise ContractError("Unexpected original native library failure boundary")
    manifest = ROOT / "sources" / package / "source.prepare.json"
    sealed(manifest, SEALS[package])
    verify_tree(ROOT / "sources" / package / "source", manifest)
    verify_tree(root / "source", manifest)
    sealed(build.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
    verify_tree(build.BOOTSTRAP, build.BOOTSTRAP_RECEIPT)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "recipes"):
        (output / name).mkdir()
    patch_name, changed_file = PATCHES[package]
    patch = HERE / "patches" / patch_name
    script = HERE / "finish-terminal-library.sh"
    for path in (patch, script, HERE / "finish-terminal-library.py"):
        shutil.copyfile(path, output / "recipes" / path.name)
    command = [build.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(), package, root, output]
    report = {
        "schema": 1, "status": "launched", "package": package, "jobs": 1,
        "pid": os.getpid(), "creation_filetime": build.current_birth(), "command": list(map(str, command)),
        "compiler_receipt_sha256": SEALS["compiler"], "source_manifest_sha256": SEALS[package],
        "preserved_failure": {"path": str(root / "result.json"), "sha256": digest(root / "result.json")},
        "source_patch": {"path": str(patch), "sha256": digest(patch), "changed_file": changed_file,
                         "before_sha256": digest(root / "source" / changed_file)},
        "minimum_free_gib": require_memory(),
    }
    write_json(output / "launch.json", report)
    try:
        report["process"] = run_observed(command, cwd=root, env=build.environment(output, 1),
                                         log_path=output / "observed.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=3600, driver_prefix=build.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native library continuation failed")
        files = inventory(root / "stage")
        missing = [name for name in build.required_files(package) if name not in files]
        if missing:
            raise ContractError(f"Required native library outputs missing: {missing}")
        expected_source = json.loads(manifest.read_text())["files"]
        actual_source = inventory(root / "source")
        changed = sorted(name for name in expected_source.keys() | actual_source.keys()
                         if expected_source.get(name) != actual_source.get(name))
        if changed != [changed_file]:
            raise ContractError(f"Unexpected working-source changes: {changed}")
        report["source_patch"]["after_sha256"] = digest(root / "source" / changed_file)
        if package == "readline":
            report["multibyte_configuration"] = {
                linkage: build.readline_multibyte((root / "build" / linkage / "config.h").read_text())
                for linkage in ("static", "shared")}
        report["status"] = "native-built-upstream-checks-not-yet-api-pty-admitted"
        write_json(root / "stage.inventory.json", {
            "schema": 1, "package": package, "compiler_receipt_sha256": SEALS["compiler"],
            "runtime_sha256": build.RUNTIME_SHA, "files": files, "status": report["status"],
            "closure_result": str(output / "result.json"),
        })
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        try:
            verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
            verify_tree(build.BOOTSTRAP, build.BOOTSTRAP_RECEIPT)
        finally:
            write_json(output / "result.json", report)
    print(json.dumps({"package": package, "status": report["status"],
                      "stage": str(root / "stage"), "manifest_sha256": digest(root / "stage.inventory.json")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=PATCHES)
    main(parser.parse_args().package)
