"""Compile genuine static libedit objects using the existing configured upstream rules."""

import importlib
import json
import os
import re
import shutil
import sys

from native_job_runner import run_observed
from readline_chain_inputs import ROOT, HERE, SEALS, fresh, sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import require_memory, write_json

build = importlib.import_module("build-readline-chain")
export = importlib.import_module("export-readline-chain")


def main():
    root = ROOT / "libedit-01"
    output = ROOT / "libedit-static-01"
    print(json.dumps({"pid": os.getpid(), "creation_filetime": build.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    fresh(output)
    manifest = root / "stage.inventory.json"
    verify_tree(root / "stage", manifest)
    original = json.loads(manifest.read_text())
    if original["compiler_receipt_sha256"] != SEALS["compiler"]:
        raise ContractError("Wrong native libedit stage cohort")
    source_manifest = root / "working-source.inventory.json"
    verify_tree(root / "source", source_manifest)
    sealed(build.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
    libtool = (root / "build/libtool").read_text()
    flags = re.findall(r'^lt_ar_flags="([a-z]+)"$', libtool, flags=re.M)
    if len(flags) != 1 or 'AR_FLAGS=${ARFLAGS-"$lt_ar_flags"}' not in libtool:
        raise ContractError("Expected one actual configured libtool archiver flag set")
    before = inventory(root / "build/src/.libs")
    output.mkdir()
    for name in ("objects", "home", "temp", "cache", "native-exits", "recipes"):
        (output / name).mkdir()
    script = HERE / "build-libedit-static.sh"
    for file in (script, HERE / "libedit-static.mk", HERE / "build-libedit-static.py", root / "build/src/Makefile"):
        shutil.copyfile(file, output / "recipes" / file.name)
    command = [build.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc",
               script.as_posix(), root, output, flags[0]]
    report = {
        "schema": 1, "status": "launched", "package": "libedit", "jobs": 1,
        "pid": os.getpid(), "creation_filetime": build.current_birth(), "command": list(map(str, command)),
        "minimum_free_gib": require_memory(), "compiler_receipt_sha256": SEALS["compiler"],
        "input_stage_manifest_sha256": digest(manifest), "working_source_manifest_sha256": digest(source_manifest),
        "scope": "Original configured COMPILE and object list plus NCURSES_STATIC for genuine static dependency linkage; no shared/C provider rebuild",
        "recipes": inventory(output / "recipes"),
    }
    write_json(output / "launch.json", report)
    try:
        report["process"] = run_observed(command, cwd=output, env=build.environment(output, 1),
                                         log_path=output / "observed.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=1800, driver_prefix=build.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native true-static libedit compilation failed")
        archive = output / "objects/libedit.a"
        report["archive_members"] = export.coff_archive(archive.read_bytes())
        if len(report["archive_members"]) != len(list((output / "objects").glob("*.o"))):
            raise ContractError("Static libedit archive member set is incomplete")
        if inventory(root / "build/src/.libs") != before:
            raise ContractError("Previously compiled shared libedit objects changed")
        shutil.copytree(root / "stage", output / "stage", symlinks=True)
        replaced = "usr/lib/libedit.a"
        shutil.copyfile(archive, output / "stage" / replaced)
        files = inventory(output / "stage")
        changed = sorted(name for name in files.keys() | original["files"].keys()
                         if files.get(name) != original["files"].get(name))
        if changed != [replaced]:
            raise ContractError(f"Unexpected static libedit delta: {changed}")
        write_json(output / "stage.inventory.json", {
            **{key: value for key, value in original.items() if key != "files"},
            "files": files, "static_library_delta": {
                "base_manifest": str(manifest), "base_manifest_sha256": digest(manifest),
                "changed_files": changed, "result": str(output / "result.json"),
            },
        })
        report.update(status="native-static-libedit-built-api-proof-pending",
                      stage_manifest_sha256=digest(output / "stage.inventory.json"))
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        verify_tree(root / "stage", manifest)
        verify_tree(root / "source", source_manifest)
        verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "stage": str(output / "stage"),
                      "manifest_sha256": report["stage_manifest_sha256"]}), flush=True)


if __name__ == "__main__":
    main()
