"""Copy the newly approved host generators and exact MSYS-aware libtool input."""

import importlib
import json
import os
from pathlib import Path
import shutil
import sys

from bash_chain_inputs import ROOT, fresh
from readline_chain_inputs import sealed
from sources import ContractError, digest, inventory, verify_tree
from ssh_bootstrap import directory_names, require_memory, write_json

terminal = importlib.import_module("build-readline-chain")
SOURCE = Path(r"C:\ag-e138920f\tcl-bootstrap-01\msys64\msys64")
MANIFEST = Path(r"C:\ag-e138920f\tcl-bootstrap-01\host-generators-01.json")
MANIFEST_SHA = "e087cd54f265eb5fbc2442878d0bf7063e1b770cdcd6c9c4a4db9868bdd551b1"
LIBTOOL = Path(r"C:\Users\crutkasLocal\.copilot\session-state\f6ea7713-2cec-41d5-b3f9-b4373e60fa33\files\resume-20260907\libtool-generator-01")
LIBTOOL_MANIFEST = LIBTOOL.with_name(LIBTOOL.name + ".copy.json")
LIBTOOL_SHA = "f9880d4da0e9fd8b8fe7e041cf4950224ce38358342d7b2bee26823259f8f3d7"


def main():
    output = ROOT / "host-bootstrap-02"
    fresh(output)
    print(json.dumps({"pid": os.getpid(), "creation_filetime": terminal.current_birth(),
                      "command": [sys.executable, *sys.argv]}), flush=True)
    sealed(MANIFEST, MANIFEST_SHA)
    record = json.loads(MANIFEST.read_text())
    if (record["status"] != "private-bootstrap-with-signature-verified-host-generators"
            or record["install"]["signature_policy"] != "Required"
            or record["install"]["raw_exit"] != 0
            or record["signature_verification"]["raw_exit"] != 0
            or record["signature_verification"]["valid_signatures"] != 6
            or len(record["files"]) != 19559):
        raise ContractError("Unexpected approved host-generator package boundary")
    for row in record["packages"]:
        sealed(row["path"], row["sha256"])
        sealed(row["signature"]["path"], row["signature"]["sha256"])
    for row in record["evidence"]:
        sealed(row["path"], row["sha256"])
    verify_tree(SOURCE, MANIFEST)
    before, directories = inventory(SOURCE), directory_names(SOURCE)
    memory = [require_memory()]
    output.mkdir()
    write_json(output / "before.json", {"files": before, "directories": directories})
    shutil.copyfile(MANIFEST, output / "parent-host-generators.json")
    packages = output / "parent-packages"
    packages.mkdir()
    for row in record["packages"]:
        for item in (row, row["signature"]):
            path = Path(item["path"])
            shutil.copyfile(path, packages / path.name)
            sealed(packages / path.name, item["sha256"])
    for row in record["evidence"]:
        path = Path(row["path"])
        if path.suffix == ".log":
            shutil.copyfile(path, output / path.name)
    target = output / "msys64"
    target.mkdir()
    for name in directories:
        (target / name).mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(before):
        if "symlink" in before[name]:
            raise ContractError("Host copy does not silently transform source links")
        shutil.copy2(SOURCE / name, target / name)
        if index % 256 == 0:
            memory.append(require_memory())
    copied, after = inventory(target), inventory(SOURCE)
    write_json(output / "copied.json", {"files": copied, "directories": directory_names(target)})
    write_json(output / "parent-after.json", {"files": after, "directories": directory_names(SOURCE)})
    if (copied != before or after != before or directory_names(target) != directories
            or directory_names(SOURCE) != directories):
        raise ContractError("Host19559 before/copy/after equality failed")
    sealed(MANIFEST, MANIFEST_SHA)
    receipt = {"schema": 1, "status": "byte-identical-new-qualified-host-generator-copy",
               "prefix": str(target), "source": str(SOURCE), "source_manifest_sha256": MANIFEST_SHA,
               "files": copied, "directories": directories, "complete_inventory_equality": True,
               "source_unchanged": True, "minimum_free_gib": min(memory),
               "scope": "Only explicit x64/emulated host generation/build/test drivers; no target-library qualification"}
    write_json(output / "msys64.copy.json", receipt)
    sealed(LIBTOOL_MANIFEST, LIBTOOL_SHA)
    verify_tree(LIBTOOL, LIBTOOL_MANIFEST)
    libtool_target = output / "msys-libtool"
    shutil.copytree(LIBTOOL, libtool_target, symlinks=True)
    verify_tree(libtool_target, LIBTOOL_MANIFEST)
    verify_tree(LIBTOOL, LIBTOOL_MANIFEST)
    shutil.copyfile(LIBTOOL_MANIFEST, output / "msys-libtool.copy.json")
    write_json(output / "result.json", {
        "status": "host-and-msys-aware-libtool-copies-closed",
        "host": str(target), "host_receipt_sha256": digest(output / "msys64.copy.json"),
        "libtool": str(libtool_target), "libtool_manifest_sha256": LIBTOOL_SHA,
        "files": len(copied), "native_payload_jobs_launched": 0})
    print((output / "result.json").read_text(), flush=True)


if __name__ == "__main__":
    main()
