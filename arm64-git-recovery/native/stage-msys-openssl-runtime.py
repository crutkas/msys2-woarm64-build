"""Copy the native MSYS crypto stage and its explicitly bound runtime into a fresh consumer root."""

import argparse
import json
from pathlib import Path
import shutil

from openssl_contracts import require_msys_build
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stage", "manifest", "prefix", "compiler-receipt", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A fresh MSYS crypto runtime root is required")
    verify_tree(args.stage, args.manifest)
    verify_tree(args.prefix, args.compiler_receipt)
    receipt = json.loads(args.manifest.read_text())
    compiler = json.loads(args.compiler_receipt.read_text())
    require_msys_build(receipt)
    if (receipt["compiler_receipt_sha256"] != digest(args.compiler_receipt) or
            compiler["source_target"].get("Profile") != "MSYS" or
            Path(compiler["prefix"]).resolve() != args.prefix.resolve()):
        raise ContractError("Expected the exact MSYS crypto producer and runtime cohort")
    original = inventory(args.stage)
    if "bin/msys-2.0.dll" in original:
        raise ContractError("Do not replace an existing crypto runtime silently")
    shutil.copytree(args.stage, args.output)
    shutil.copyfile(args.prefix / "bin/msys-2.0.dll", args.output / "bin/msys-2.0.dll")
    expected = {**original, "bin/msys-2.0.dll": compiler["files"]["bin/msys-2.0.dll"]}
    if inventory(args.output) != expected:
        raise ContractError("MSYS crypto consumer copy differs")
    verify_tree(args.stage, args.manifest)
    verify_tree(args.prefix, args.compiler_receipt)
    report = {"schema": 1, "scope": "Native MSYS crypto/runtime consumer root, not upstream-test or distribution admission",
              "source_receipt_sha256": digest(args.manifest),
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "files": expected}
    args.output.with_name(args.output.name + ".manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Staged {len(expected)} files with the compiler cohort's exact MSYS runtime")


if __name__ == "__main__":
    main()
