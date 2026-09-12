"""Combine verified POSIX stages and explicitly regenerate their Info index."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from sources import ContractError, digest, inventory, verify_tree


def combine(builds, output, install_info):
    output = Path(output).resolve()
    if output.exists():
        raise ContractError("New combined stage required")
    entries, inputs = {}, []
    for root in map(Path, builds):
        report = root / "build-evidence.json"
        verify_tree(root / "stage", report)
        data = json.loads(report.read_text())
        if data["status"] != "built-not-run":
            raise ContractError("Expected complete installed build evidence")
        inputs.append({"root": str(root), "report_sha256": digest(report), "input": data})
        for rel, record in data["files"].items():
            if rel == "usr/share/info/dir":
                continue
            if rel in entries and entries[rel]["record"] != record:
                raise ContractError(f"Conflicting POSIX payload: {rel}")
            entries[rel] = {"path": root / "stage" / rel, "record": record}
    payload = output / "payload"
    payload.mkdir(parents=True)
    runtime_directories = ("tmp", "var/tmp", "etc")
    for rel in runtime_directories:
        (payload / rel).mkdir(parents=True, exist_ok=True)
    for rel, entry in entries.items():
        path = payload / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry["path"], path)
        if digest(path) != entry["record"]["sha256"]:
            raise ContractError("Stage changed during copy")
    info_dir = payload / "usr/share/info"
    if info_dir.is_dir():
        for info in sorted(info_dir.glob("*.info")):
            subprocess.run([str(install_info), "--dir-file=" + str(info_dir / "dir"), str(info)], check=True)
    result = {"schema": 1, "classification": "bootstrap", "scope": "Combined complete selected POSIX stages, not full Git",
              "inputs": inputs, "info_index_generator": {"path": str(install_info), "sha256": digest(install_info)},
              "required_directories": list(runtime_directories),
              "files": inventory(payload)}
    with (output / "manifest.json").open("x") as dest:
        json.dump(result, dest, indent=2)
        dest.write("\n")
    print(f"Combined {len(result['files'])} files")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", action="append", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--install-info", type=Path, required=True)
    a = p.parse_args()
    combine(a.build, a.output, a.install_info)


if __name__ == "__main__":
    main()
