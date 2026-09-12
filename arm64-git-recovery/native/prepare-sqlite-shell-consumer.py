"""Prepare a fresh native shell composition without launching any target code."""

import argparse
import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory
from sqlite_consumer_inputs import compose
from ssh_bootstrap import require_memory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(r"C:\ag-sqlite-resume-01")
    output = args.output.resolve()
    if (output == root or not output.is_relative_to(root) or output.exists()
            or any(p.is_symlink() or p.is_junction() for p in output.parents)):
        raise ContractError("Fresh owned shell-consumer composition required")
    lock_path = Path(__file__).with_name("sqlite-shell-candidate.json")
    lock = json.loads(lock_path.read_text())
    output.mkdir()
    report = {"schema": 1, "status": "failed", "native_processes_launched": 0,
              "lock_sha256": digest(lock_path), "input_lock": lock, "free_ram_gib": require_memory()}
    try:
        report["runtime"] = compose(lock, output / "runtime")
        (output / "runtime/tmp").mkdir()
        report["required_runtime_directories"] = ["tmp"]
        for name in ("inputs", "work", "temp", "home", "native-exits"):
            (output / name).mkdir()
        baseline = Path(lock["baseline"]["root"])
        for name in ("shell5-import.sql", "sqlite-tdbc-consumer.tcl", "sqlite-shell-pipe.c"):
            shutil.copyfile(baseline / "inputs" / name, output / "inputs" / name)
        shutil.copyfile(baseline / "sqlite-shell-pipe.exe", output / "runtime/usr/bin/sqlite-shell-pipe.exe")
        shutil.copyfile(Path(__file__).with_name("fixtures") / "sqlite-shell-consumer.sh",
                        output / "inputs/sqlite-shell-consumer.sh")
        report["runtime"]["files"] = inventory(output / "runtime")
        report["fixture_files"] = inventory(output / "inputs")
        report["status"] = "private-native-sqlite-shell-consumer-prepared-not-executed"
    finally:
        (output / "prepare.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "manifest": str(output / "prepare.json"),
                      "sha256": digest(output / "prepare.json")}))


if __name__ == "__main__":
    main()
