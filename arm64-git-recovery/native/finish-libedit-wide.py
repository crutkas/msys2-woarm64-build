"""Apply the reviewed mixed-width display-cell port and finish the real native build."""

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
PACKAGE_ROOT = ROOT / "libedit-01"
PATCH_SHA = "c013b66dd51b148c3647cd0af56a34ef0a755c5f7cb4b3aa071eaa66feae7b6f"
PROVENANCE = HERE / "patches/libedit-20240808-display-cells.provenance.json"
PATCH = HERE / "patches/libedit-20240808-display-cells.patch"


def working_source(after):
    sealed(PATCH, PATCH_SHA)
    source_record = json.loads((ROOT / "sources/libedit/source.prepare.json").read_text())
    expected = dict(source_record["files"])
    expected["src/read.c"] = {"sha256": "2c1020ac2860f3431d2b98611983bd019854feceb6eff1bf9f8b503fe35b0dc0",
                              "size": 13962}
    provenance = json.loads(PROVENANCE.read_text())
    if provenance["patch_sha256"] != PATCH_SHA:
        raise ContractError("Reviewed libedit display-cell provenance differs")
    for row in provenance["modified_source_files"]:
        name = row["path"].replace("\\", "/")
        sha = row["after_sha256_in_memory" if after else "before_sha256"]
        sealed(PACKAGE_ROOT / "source" / name, sha)
        expected[name] = {"sha256": sha, "size": (PACKAGE_ROOT / "source" / name).stat().st_size}
    if inventory(PACKAGE_ROOT / "source") != expected:
        raise ContractError("Libedit working tree changed outside the exact ioctl/display-cell patches")
    if after:
        manifest = PACKAGE_ROOT / "working-source.inventory.json"
        if manifest.exists():
            verify_tree(PACKAGE_ROOT / "source", manifest)
        else:
            write_json(manifest, {"schema": 1, "source": source_record["source"],
                                 "prepared_manifest_sha256": SEALS["libedit"],
                                 "display_cells_patch_sha256": PATCH_SHA,
                                 "display_cells_provenance_sha256": digest(PROVENANCE),
                                 "files": expected})


def main():
    print(json.dumps({"pid": os.getpid(), "creation_filetime": build.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    output = PACKAGE_ROOT / "finish-03"
    fresh(output)
    previous = json.loads((PACKAGE_ROOT / "finish-02/native-job.json").read_text())
    if (previous["parent_raw_exit"] != 2 or previous["timed_out"] or not previous["observation_count_matches"]
            or previous["unrelayed_high_exits"] or previous["unobserved_process_ids"]):
        raise ContractError("Unexpected previous libedit failure boundary")
    working_source(False)
    sealed(build.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
    verify_tree(build.BOOTSTRAP, build.BOOTSTRAP_RECEIPT)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits", "recipes"):
        (output / name).mkdir()
    script = HERE / "finish-libedit-wide.sh"
    for file in (script, HERE / "finish-libedit-wide.py", PATCH, PROVENANCE,
                 HERE / "patches/libedit-20240808-display-cells-regression.c"):
        shutil.copyfile(file, output / "recipes" / file.name)
    command = [build.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(), PACKAGE_ROOT, output]
    report = {
        "schema": 1, "status": "launched", "package": "libedit", "jobs": 2,
        "pid": os.getpid(), "creation_filetime": build.current_birth(), "command": list(map(str, command)),
        "compiler_receipt_sha256": SEALS["compiler"], "runtime_sha256": build.RUNTIME_SHA,
        "source_manifest_sha256": SEALS["libedit"], "display_cells_patch_sha256": PATCH_SHA,
        "preserved_failure": {"path": str(PACKAGE_ROOT / "finish-02/result.json"),
                              "sha256": digest(PACKAGE_ROOT / "finish-02/result.json")},
        "minimum_free_gib": require_memory(), "recipes": inventory(output / "recipes"),
        "scope": "Full wide/static/shared/examples and upstream checks; public wchar_t ABI unchanged, no feature/test/diagnostic removal",
    }
    write_json(output / "launch.json", report)
    try:
        report["process"] = run_observed(command, cwd=PACKAGE_ROOT, env=build.environment(output, 2),
                                         log_path=output / "observed.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=3600, driver_prefix=build.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native libedit mixed-width build/check/install failed")
        working_source(True)
        files = inventory(PACKAGE_ROOT / "stage")
        missing = [name for name in build.required_files("libedit") if name not in files]
        if missing:
            raise ContractError(f"Incomplete libedit native payload: {missing}")
        report["working_source_manifest_sha256"] = digest(PACKAGE_ROOT / "working-source.inventory.json")
        report["status"] = "native-built-upstream-checks-not-yet-api-pty-admitted"
        write_json(PACKAGE_ROOT / "stage.inventory.json", {
            "schema": 1, "package": "libedit", "compiler_receipt_sha256": SEALS["compiler"],
            "runtime_sha256": build.RUNTIME_SHA, "status": report["status"], "files": files,
            "closure_result": str(output / "result.json"),
            "working_source_manifest": str(PACKAGE_ROOT / "working-source.inventory.json"),
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
    print(json.dumps({"status": report["status"], "stage": str(PACKAGE_ROOT / "stage"),
                      "manifest_sha256": digest(PACKAGE_ROOT / "stage.inventory.json")}), flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--validate-working"]:
        working_source(True)
    elif sys.argv[1:]:
        raise ContractError("Unsupported libedit continuation arguments")
    else:
        main()
