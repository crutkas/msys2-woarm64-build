"""Close upstream checks and installation on the already-built owned ncurses tree."""

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


def main():
    root = ROOT / "ncurses-01"
    output = root / "check-06"
    fresh(output)
    output.mkdir()
    for name in ("home", "temp", "cache", "native-exits"):
        (output / name).mkdir()
    old = json.loads((root / "result.json").read_text())
    observation = json.loads((root / "native-job.json").read_text())
    install_failure = json.loads((root / "check-05/native-job.json").read_text())
    if (install_failure["parent_raw_exit"] != 2 or not install_failure["observation_count_matches"]
            or install_failure["unrelayed_high_exits"] or install_failure["timed_out"]):
        raise ContractError("Unexpected partially installed ncurses boundary")
    if (old["status"] != "failed" or old["compiler_receipt_sha256"] != SEALS["compiler"]
            or observation["parent_raw_exit"] != 2 or observation["timed_out"]
            or not observation["observation_count_matches"] or observation["unrelayed_high_exits"]):
        raise ContractError("Unexpected initial ncurses failure boundary")
    sealed(build.COMPILER_RECEIPT, SEALS["compiler"])
    verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
    verify_tree(build.BOOTSTRAP, build.BOOTSTRAP_RECEIPT)
    verify_tree(ROOT / "sources/ncurses/source", ROOT / "sources/ncurses/source.prepare.json")
    before = inventory(root / "build/lib")
    script = HERE / "finish-ncurses-chain.sh"
    patch = HERE / "patches/ncurses-6.6-debug-test-trace.patch"
    recipes = output / "recipes"
    recipes.mkdir()
    for file in (script, HERE / "finish-ncurses-chain.py", *sorted((HERE / "patches").glob("ncurses-*.patch"))):
        shutil.copyfile(file, recipes / file.name)
    if b"\r" in script.read_bytes() or b"\r" in patch.read_bytes():
        raise ContractError("Native shell/patch files require LF")
    env = build.environment(output, 2)
    command = [build.BOOTSTRAP / "usr/bin/bash.exe", "--noprofile", "--norc", script.as_posix(), root, "2", "remaining"]
    report = {
        "schema": 1, "status": "launched", "package": "ncurses", "jobs": 2,
        "pid": os.getpid(), "creation_filetime": build.current_birth(), "command": list(map(str, command)),
        "launcher_command": [sys.executable, *sys.argv],
        "compiler_receipt_sha256": SEALS["compiler"], "runtime_sha256": build.RUNTIME_SHA,
        "preserved_failure": {"path": str(root / "result.json"), "sha256": digest(root / "result.json")},
        "libraries_before": before, "minimum_free_gib": require_memory(),
        "test_patch": {"path": str(patch), "sha256": digest(patch)},
        "header_test_patch": {"path": str(HERE / "patches/ncurses-6.6-out-of-tree-header-test.patch"),
                              "sha256": digest(HERE / "patches/ncurses-6.6-out-of-tree-header-test.patch")},
        "source_fix_scope": "Only SCROLLDEBUG/HASHDEBUG standalone algorithm test macro; no production feature/test removal",
        "test_link_fix": "Retain all configured test libraries and add actual libticw for split-ticlib state",
        "script_sha256": digest(script),
        "recipe_snapshot": inventory(recipes),
        "retained_partial_stage": inventory(root / "stage"),
        "installation_continuation": "Retain successful man/include/ncurses/progs/panel/menu/form install; execute test/misc/c++ and every package tail",
    }
    write_json(output / "launch.json", report)
    print(json.dumps({key: report[key] for key in ("pid", "creation_filetime", "command", "minimum_free_gib")}), flush=True)
    try:
        report["process"] = run_observed(command, cwd=root, env=env,
                                         log_path=output / "observed.log", result_path=output / "native-job.json",
                                         relay_records=output / "native-exits", timeout=3600, driver_prefix=build.OBSERVER)
        if not report["process"]["passed"]:
            raise ContractError("Native ncurses full upstream check/install continuation failed")
        files = inventory(root / "stage")
        if any(files.get(name) != identity for name, identity in report["retained_partial_stage"].items()):
            raise ContractError("Previously completed ncurses install payload changed")
        missing = [name for name in build.required_files("ncurses") if name not in files]
        if missing:
            raise ContractError(f"Missing full native ncurses payload: {missing}")
        report["libraries_after"] = inventory(root / "build/lib")
        report["status"] = "native-built-upstream-checks-not-yet-api-pty-admitted"
        write_json(root / "stage.inventory.json", {
            "schema": 1, "package": "ncurses", "compiler_receipt_sha256": SEALS["compiler"],
            "runtime_sha256": build.RUNTIME_SHA, "files": files,
            "status": report["status"], "closure_result": str(output / "result.json"),
        })
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        verify_tree(build.COMPILER, build.COMPILER_RECEIPT)
        verify_tree(build.BOOTSTRAP, build.BOOTSTRAP_RECEIPT)
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "stage": str(root / "stage")}), flush=True)


if __name__ == "__main__":
    main()
