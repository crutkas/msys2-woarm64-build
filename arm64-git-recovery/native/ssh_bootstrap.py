"""Copy an explicitly approved quiescent SSH build driver without executing it."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import sys

from sources import ContractError, digest, inventory, relative_path


def require_memory():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in
                      ("total_physical", "available_physical", "total_page", "available_page",
                       "total_virtual", "available_virtual", "extended_virtual")]]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ContractError("Cannot verify the SSH bootstrap RAM floor")
    gib = status.available_physical / 1024 ** 3
    if gib <= 8:
        raise ContractError(f"SSH bootstrap copy requires more than 8 GiB free RAM; observed {gib:.2f}")
    return gib


def producer_files(rows):
    if not isinstance(rows, list) or not rows:
        raise ContractError("Expected a nonempty approved bootstrap file inventory")
    files, folded = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"Path", "SHA256"}:
            raise ContractError("Unexpected approved bootstrap inventory row")
        name = row["Path"].replace("\\", "/")
        relative_path(name)
        if name.casefold() in folded or not re.fullmatch("[0-9a-f]{64}", row["SHA256"]):
            raise ContractError("Duplicate bootstrap inventory path or invalid SHA")
        files[name] = row["SHA256"]
        folded.add(name.casefold())
    return files


def directory_names(root):
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir())


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def snapshot_bootstrap(descriptor, expected_sha256, output):
    descriptor, output = Path(descriptor), Path(output)
    if not re.fullmatch("[0-9a-f]{64}", expected_sha256) or digest(descriptor) != expected_sha256:
        raise ContractError("Approved SSH bootstrap descriptor seal differs")
    record = json.loads(descriptor.read_text(encoding="utf-8-sig"))
    if (record.get("Status") != "quiescent-preserved-bootstrap-source-currently-verified" or
            record.get("Consumers") != 0 or not isinstance(record.get("Files"), int)):
        raise ContractError("The bootstrap descriptor does not approve a quiescent preserved source")
    source = Path(record["Source"])
    forbidden = Path(record["NoReadOfActivePrefix"])
    forbidden_absolute = Path(os.path.abspath(forbidden))
    if (Path(os.path.abspath(source)).is_relative_to(forbidden_absolute) or
            Path(os.path.abspath(output)).is_relative_to(forbidden_absolute)):
        raise ContractError("Descriptor points at the expressly forbidden active prefix")
    if (output.exists() or output.is_symlink() or
            output.resolve().is_relative_to(source.resolve()) or
            source.resolve().is_relative_to(output.resolve())):
        raise ContractError("A fresh, disjoint SSH-private bootstrap output is required")
    if any(parent.is_symlink() or parent.is_junction() for parent in output.parents):
        raise ContractError("SSH bootstrap output may not traverse a link or junction")
    producer_inventory = Path(record["Inventory"])
    if digest(producer_inventory) != record["InventorySHA256"]:
        raise ContractError("Approved bootstrap inventory seal differs")
    expected = producer_files(json.loads(producer_inventory.read_text(encoding="utf-8-sig")))
    if len(expected) != record["Files"]:
        raise ContractError("Approved bootstrap inventory count differs")
    memory = [require_memory()]
    before = inventory(source)
    if (any("symlink" in row for row in before.values()) or
            {name: row.get("sha256") for name, row in before.items()} != expected):
        raise ContractError("Frozen bootstrap differs from its approved inventory or contains links")
    directories = directory_names(source)
    memory.append(require_memory())
    output.mkdir(parents=True)
    payload = output / "msys64"
    report = {
        "schema": 1, "status": "failed", "prefix": str(payload.resolve()),
        "source": str(source.resolve()), "descriptor_sha256": expected_sha256,
        "producer_inventory_sha256": record["InventorySHA256"],
        "copier_sha256": digest(Path(__file__)),
        "pid": os.getpid(), "command": [sys.executable, *sys.argv],
        "scope": "Byte-identical private build driver only; not target payload or native qualification",
        "target_or_bootstrap_processes_launched": 0,
    }
    print(json.dumps({"pid": os.getpid(), "phase": "approved-inventory-verified",
                      "files": len(before), "output": str(output.resolve())}), flush=True)
    try:
        write_json(output / "before.json", {"files": before, "directories": directories})
        shutil.copyfile(descriptor, output / "bootstrap-source.json")
        shutil.copyfile(producer_inventory, output / "producer-inventory.json")
        payload.mkdir()
        for name in directories:
            (payload / name).mkdir(parents=True, exist_ok=True)
        for index, name in enumerate(before):
            path = source / name
            if path.is_symlink() or path.is_junction() or not path.is_file():
                raise ContractError(f"Bootstrap source file changed type during copy: {name}")
            target = payload / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if index % 256 == 0:
                memory.append(require_memory())
        copied = inventory(payload)
        copied_directories = directory_names(payload)
        write_json(output / "copied-inventory.json", {"files": copied, "directories": copied_directories})
        memory.append(require_memory())
        after = inventory(source)
        after_directories = directory_names(source)
        write_json(output / "source-after.json", {"files": after, "directories": after_directories})
        if copied != before or after != before or copied_directories != directories or after_directories != directories:
            raise ContractError("Full before/copy/after SSH bootstrap inventories differ")
        if (digest(descriptor) != expected_sha256 or
                digest(output / "bootstrap-source.json") != expected_sha256 or
                digest(producer_inventory) != record["InventorySHA256"] or
                digest(output / "producer-inventory.json") != record["InventorySHA256"]):
            raise ContractError("Bootstrap descriptor or producer inventory changed during copy")
        report.update(status="private-ssh-bootstrap-byte-identical-not-executed",
                      files=copied, directories=directories, source_unchanged=True,
                      complete_inventory_equality=True, minimum_observed_free_gib=min(memory))
        write_json(output / "msys64.copy.json", report)
    finally:
        write_json(output / "result.json", report)
    print(json.dumps({"status": report["status"], "prefix": str(payload.resolve()),
                      "files": len(copied), "minimum_free_gib": min(memory)}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--descriptor-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot_bootstrap(args.descriptor, args.descriptor_sha256, args.output)


if __name__ == "__main__":
    main()
