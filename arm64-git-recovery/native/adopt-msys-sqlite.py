"""Adopt complete sealed SQLite inputs into one fresh private work area."""

import json
import os
from pathlib import Path
import shutil
import sys

from sources import ContractError, digest, inventory
from ssh_bootstrap import require_memory


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def verified_copy(source, destination, expected):
    before = inventory(source)
    if before != expected:
        changed = [p for p in before.keys() | expected.keys() if before.get(p) != expected.get(p)]
        raise ContractError(f"Input differs: {source}: {changed[:20]}")
    require_memory()
    shutil.copytree(source, destination, symlinks=True)
    if inventory(destination) != before or inventory(source) != before:
        raise ContractError(f"Copy or source changed: {source}")
    return before


def main():
    lock_path = Path(__file__).with_name("sqlite-inputs.json")
    lock = json.loads(lock_path.read_text())
    if os.name != "nt" or digest(sys.executable) != lock["python_sha256"]:
        raise ContractError("Exact native ARM64 Python required")
    root = Path(lock["root"])
    root.mkdir(exist_ok=False)
    write_json(root / "adopt-launch.json", {"pid": os.getpid(), "command": sys.orig_argv,
                                          "free_gib": require_memory()})
    report = {"schema": 1, "status": "failed", "lock_sha256": digest(lock_path),
              "full_cpp_qualified": False, "inputs": {}, "input_trees_unchanged": False}
    try:
        for name, row in lock["inputs"].items():
            print(f"Adopting {name}", flush=True)
            manifest = Path(row["manifest"])
            if digest(manifest) != row["sha256"]:
                raise ContractError(f"Manifest seal differs: {name}")
            record = json.loads(manifest.read_text())
            src, dst = Path(row["root"]), root / name
            if name == "prepared":
                if record["status"] != "prepared-msys-sqlite-full-source-and-docs":
                    raise ContractError("Expected full prepared source and docs")
                dst.mkdir()
                for sub, key in (("source", "files"), ("docs", "docs_files")):
                    verified_copy(src / sub, dst / sub, record[key])
                assets = {p: {"sha256": sha, "size": (src / "recipe" / p).stat().st_size}
                          for p, sha in record["recipe_inputs"].items()}
                verified_copy(src / "recipe", dst / "recipe", assets)
                files = inventory(dst)
            else:
                files = verified_copy(src, dst, record[row.get("inventory_key", "files")])
            if digest(manifest) != row["sha256"]:
                raise ContractError(f"Manifest changed during copy: {name}")
            shutil.copyfile(manifest, root / f"{name}.upstream.json")
            if name == "observer":
                shutil.copyfile(manifest, root / "observer.manifest.json")
            write_json(root / f"{name}.inventory.json", {"schema": 1, "upstream": row, "files": files})
            report["inputs"][name] = {"files": len(files), "upstream": row,
                                     "private_inventory_sha256": digest(root / f"{name}.inventory.json"),
                                     "source_before_after_equal": True}
        for name in ("home", "temp", "cache", "proof"):
            (root / name).mkdir()
        report.update(status="private-sqlite-inputs-byte-identical-not-executed",
                      input_trees_unchanged=True, free_gib_after=require_memory())
    finally:
        write_json(root / "adopt-result.json", report)
    print(report["status"], flush=True)


if __name__ == "__main__":
    main()
