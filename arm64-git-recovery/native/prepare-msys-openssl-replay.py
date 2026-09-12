"""Prepare an immutable-binary test copy using the maintained native test transport."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from openssl_contracts import require_msys_build
from openssl_test_patches import TEST_FILES, adapt_test
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "stage-receipt", "prefix", "compiler-receipt", "bootstrap", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A fresh MSYS OpenSSL replay copy is required")
    stage = args.build / "stage"
    verify_tree(stage, args.stage_receipt)
    verify_tree(args.prefix, args.compiler_receipt)
    receipt = json.loads(args.stage_receipt.read_text())
    compiler = json.loads(args.compiler_receipt.read_text())
    require_msys_build(receipt)
    if (receipt["compiler_receipt_sha256"] != digest(args.compiler_receipt) or
            Path(compiler["prefix"]).resolve() != args.prefix.resolve() or
            compiler["source_target"]["Profile"] != "MSYS"):
        raise ContractError("Expected the exact native MSYS crypto/compiler pair")
    source = args.build / "source"
    before = inventory(source)
    for relative, installed in (("apps/openssl.exe", "bin/openssl.exe"),
                                ("msys-crypto-3.dll", "bin/msys-crypto-3.dll"),
                                ("msys-ssl-3.dll", "bin/msys-ssl-3.dll")):
        if before[relative] != receipt["files"][installed]:
            raise ContractError("OpenSSL replay source is not the installed producer output")
    shutil.copytree(source, args.output)
    patch = Path(__file__).parent / "patches/openssl-native-test-transport.patch"
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env["PATH"] = str(args.bootstrap / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    result = subprocess.run([str(args.bootstrap / "usr/bin/patch.exe"), "--batch", "--forward", "--fuzz=0",
                             "--no-backup-if-mismatch", "-p1", "-i", patch.resolve().as_posix()],
                            cwd=args.output, env=env, capture_output=True, timeout=30)
    args.output.with_name(args.output.name + ".patch.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise ContractError("OpenSSL native test-driver patch failed")
    for name in TEST_FILES:
        path = args.output / name
        path.write_text(adapt_test(name, path.read_text()), newline="\n")
    shutil.copyfile(args.prefix / "bin/msys-2.0.dll", args.output / "msys-2.0.dll")
    after = inventory(args.output)
    changed = sorted(name for name in after.keys() | before.keys() if after.get(name) != before.get(name))
    if changed != sorted(["msys-2.0.dll", "util/perl/OpenSSL/Test.pm", *TEST_FILES]):
        raise ContractError(f"Unexpected replay preparation changes: {changed}")
    if inventory(source) != before:
        raise ContractError("Original OpenSSL source/build changed")
    verify_tree(args.prefix, args.compiler_receipt)
    report = {"schema": 1, "scope": "Unchanged native test binaries; explicit driver transport and exact runtime",
              "stage_receipt_sha256": digest(args.stage_receipt),
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "patch_sha256": digest(patch), "changed_files": changed, "files": after}
    report["test_adaptation_sha256"] = digest(Path(__file__).with_name("openssl_test_patches.py"))
    report["test_scope"] = "Actual PE exports; private test CA directory/config. Installed package defaults and compiled binary bytes are unchanged."
    args.output.with_name(args.output.name + ".manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Prepared {len(after)} files for native MSYS OpenSSL test replay")


if __name__ == "__main__":
    main()
