"""Repeat only installation from a completed POSIX build into a new, independently inventoried stage."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from package_posix import finish
from runtime_readiness import verify
from sources import ContractError, digest, inventory, verify_tree


def binary_inputs(root):
    return {str(path): digest(path) for path in root.rglob("*") if path.is_file() and
            path.suffix in (".o", ".a", ".exe", ".dll")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("Fresh installation output required")
    record = json.loads((args.build / "build-inputs.json").read_text())
    receipt = record["runtime_receipt"]
    if verify(receipt["path"], args.prefix) != receipt["sha256"]:
        raise ContractError("Runtime receipt changed")
    source = Path(record["prepared_source"]["path"])
    verify_tree(source, source.with_name(source.name + ".prepare.json"))
    for row in record["tools"].values():
        if digest(row["path"]) != row["sha256"]:
            raise ContractError("Original build tools changed")
    before = binary_inputs(args.build)
    if not before:
        raise ContractError("There are no completed build binaries to install")
    args.output.mkdir(parents=True)
    stage = args.output / "stage"
    command = ["make", "-j1", f"DESTDIR={stage}", "install"]
    with (args.output / "install.log").open("x") as log:
        subprocess.run(command, cwd=record["build_directory"], stdout=log, stderr=subprocess.STDOUT, check=True)
    if binary_inputs(args.build) != before:
        raise ContractError("Installation changed a compiled input instead of only restaging")
    finish(record["package"], args.build / "source", stage, record["build_directory"])
    shutil.copyfile(args.prefix / "bin/msys-2.0.dll", stage / "usr/bin/msys-2.0.dll")
    verify(receipt["path"], args.prefix)
    record.update({"status": "built-not-run", "restaged_from": str(args.build),
                   "original_build_inputs_sha256": digest(args.build / "build-inputs.json"),
                   "install_command": command, "compiled_inputs_unchanged": True,
                   "files": inventory(stage), "source": {"id": record["package"], "scope": "Existing source build; restaged only"},
                   "limitations": ["Original build profile and pending native behavior remain unchanged"]})
    (args.output / "build-evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Restaged {len(record['files'])} files without changing compiled inputs")


if __name__ == "__main__":
    main()
