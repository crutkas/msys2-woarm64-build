"""Build only the missing genuine normal-mode C++ archive, retaining the closed stage."""

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
export = importlib.import_module("export-readline-chain")


def main():
    root = ROOT / "ncurses-01"
    stage = root / "stage"
    manifest = root / "stage.inventory.json"
    output = ROOT / "ncurses-static-cxx-01"
    print(json.dumps({"pid": os.getpid(), "creation_filetime": build.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    fresh(output)
    verify_tree(stage, manifest)
    original = json.loads(manifest.read_text())
    if original["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Wrong native C++ input cohort")
    sealed(build.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
    source_manifest = json.loads((ROOT / "sources/ncurses/source.prepare.json").read_text())
    for file in (root / "source/c++").iterdir():
        if file.is_file():
            sealed(file, source_manifest["files"]["c++/" + file.name]["sha256"])
    before = inventory(root / "build/lib")
    output.mkdir()
    for name in ("objects", "home", "temp", "cache", "native-exits", "recipes"):
        (output / name).mkdir()
    script = HERE / "build-ncurses-static-cxx.sh"
    for file in (script, HERE / "ncurses-static-cxx.mk", HERE / "build-ncurses-static-cxx.py",
                 root / "build/c++/Makefile"):
        shutil.copyfile(file, output / "recipes" / file.name)
    command = [build.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(), root, output]
    report = {
        "schema": 1, "status": "launched", "package": "ncurses", "jobs": 1,
        "pid": os.getpid(), "creation_filetime": build.current_birth(), "command": list(map(str, command)),
        "minimum_free_gib": require_memory(), "compiler_receipt_sha256": SEALS["compiler"],
        "input_stage_manifest_sha256": digest(manifest), "libraries_before": before,
        "recipes": inventory(output / "recipes"),
        "scope": "Only eight C++ normal-mode objects using unmodified upstream CFLAGS_NORMAL and archiver flags; all original stage and shared/C libraries retained",
    }
    write_json(output / "launch.json", report)
    try:
        report["process"] = run_observed(command, cwd=output, env=build.environment(output, 1),
                                         log_path=output / "observed.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=900, driver_prefix=build.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native normal-mode C++ archive build failed")
        archive = output / "objects/libncurses++w.a"
        report["archive_members"] = export.coff_archive(archive.read_bytes())
        if len(report["archive_members"]) != 8:
            raise ContractError("Unexpected normal-mode C++ object count")
        if inventory(root / "build/lib") != before:
            raise ContractError("A closed native library was modified")
        verify_tree(stage, manifest)
        shutil.copytree(stage, output / "stage", symlinks=True)
        replaced = "usr/lib/libncurses++w.a"
        shutil.copyfile(archive, output / "stage" / replaced)
        files = inventory(output / "stage")
        changed = sorted(name for name in files.keys() | original["files"].keys()
                         if files.get(name) != original["files"].get(name))
        if changed != [replaced]:
            raise ContractError(f"Static C++ stage delta was not surgical: {changed}")
        write_json(output / "stage.inventory.json", {
            **{key: value for key, value in original.items() if key != "files"},
            "files": files, "static_cpp_delta": {
                "base_manifest": str(manifest), "base_manifest_sha256": digest(manifest),
                "changed_files": changed, "result": str(output / "result.json"),
            },
        })
        report.update(status="native-normal-cxx-archive-built-static-api-proof-pending",
                      stage_manifest_sha256=digest(output / "stage.inventory.json"))
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        verify_tree(stage, manifest)
        verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "stage": str(output / "stage"),
                      "manifest_sha256": report["stage_manifest_sha256"]}), flush=True)


if __name__ == "__main__":
    main()
