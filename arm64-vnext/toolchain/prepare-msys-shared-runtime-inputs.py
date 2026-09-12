#!/usr/bin/env python3
"""Stage a new native runtime-library build root from exact existing receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path, expected):
    if digest(path) != expected:
        raise ValueError(f"Receipt identity differs: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify(root, files):
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(files):
        raise ValueError(f"Inventory file set differs: {root}")
    for relative, spec in files.items():
        path = root.joinpath(*relative.split("/")).resolve(strict=True)
        if not path.is_relative_to(root) or digest(path) != spec["sha256"] or path.stat().st_size != spec["size"]:
            raise ValueError(f"Input payload differs: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-receipt", required=True, type=Path)
    parser.add_argument("--sdk-sha256", required=True)
    parser.add_argument("--bootstrap", required=True, type=Path)
    parser.add_argument("--bootstrap-manifest", required=True, type=Path)
    parser.add_argument("--bootstrap-sha256", required=True)
    parser.add_argument("--runtime-receipt", required=True, type=Path)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sdk = read(args.sdk_receipt, args.sdk_sha256)
    bootstrap = read(args.bootstrap_manifest, args.bootstrap_sha256)
    runtime = read(args.runtime_receipt, args.runtime_sha256)
    if sdk["source_target"]["Triple"] != "aarch64-pc-cygwin" or sdk["source_target"]["Profile"] != "MSYS":
        raise ValueError("This provider must use a native MSYS SDK")
    if runtime["status"] != "coherent-runtime-execvp-errno-qualified":
        raise ValueError("Expected the coherent execvp d70 runtime pair")
    old = Path(sdk["prefix"]).resolve(strict=True)
    old_bootstrap = args.bootstrap.resolve(strict=True)
    verify(old, sdk["files"])
    verify(old_bootstrap, bootstrap["files"])
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    shutil.copytree(old, out / "sdk")
    shutil.copytree(old_bootstrap, out / "bootstrap")
    receipts = out / "receipts"
    receipts.mkdir()
    for name, path in (("sdk.json", args.sdk_receipt), ("bootstrap.json", args.bootstrap_manifest),
                       ("runtime.json", args.runtime_receipt)):
        shutil.copy2(path, receipts / name)
    changes = []
    for name, relative in (("runtime", "bin/msys-2.0.dll"),
                           ("import_library", "aarch64-pc-cygwin/lib/libmsys-2.0.a"),
                           ("crt0", "aarch64-pc-cygwin/lib/crt0.o")):
        item = runtime["binaries"][name]
        source = Path(item["path"])
        if digest(source) != item["sha256"]:
            raise ValueError("Coherent runtime input changed")
        target = out / "sdk" / Path(relative)
        changes.append({"path": relative, "before": digest(target), "after": item["sha256"]})
        shutil.copy2(source, target)
    if digest(out / "bootstrap" / "usr" / "bin" / "msys-2.0.dll") != runtime["binaries"]["runtime"]["sha256"]:
        raise ValueError("Native build shell and SDK must share the d70 cohort")
    verify(old, sdk["files"])
    verify(old_bootstrap, bootstrap["files"])
    (out / "build").mkdir()
    (out / "logs").mkdir()
    (out / "tmp").mkdir()
    report = {"schema": 1, "status": "runtime-library-build-inputs-only",
              "sdk_receipt_sha256": args.sdk_sha256, "runtime_receipt_sha256": args.runtime_sha256,
              "bootstrap_manifest_sha256": args.bootstrap_sha256, "runtime_changes": changes,
              "sdk_files": {p.relative_to(out / "sdk").as_posix(): {"sha256": digest(p), "size": p.stat().st_size}
                            for p in (out / "sdk").rglob("*") if p.is_file()},
              "bootstrap_files": bootstrap["files"], "original_inputs_unchanged": True}
    (out / "inputs.json").write_text(json.dumps(report, indent=2) + "\n")
    print(out / "inputs.json")


if __name__ == "__main__":
    main()
