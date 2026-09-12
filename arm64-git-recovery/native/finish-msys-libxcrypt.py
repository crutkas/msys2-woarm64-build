"""Replay and install the existing native crypt binaries in a fresh, explicitly retargeted build copy."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from bounded_process import run
from compiler_tools import require_msys_jump_receipt, verify_support
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "prefix", "compiler-receipt", "bootstrap", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A new libxcrypt replay/install root is required")
    original_receipt = args.build.with_name(args.build.name + ".result.json")
    previous = json.loads(original_receipt.read_text())
    if (previous.get("status") != "failed" or previous.get("package") != "libxcrypt" or
            previous["compiler_receipt_sha256"] != digest(args.compiler_receipt)):
        raise ContractError("Expected this producer's existing failed libxcrypt build")
    verify_tree(args.prefix, args.compiler_receipt)
    producer = json.loads(args.compiler_receipt.read_text())
    require_msys_jump_receipt(producer)
    if Path(producer["prefix"]).resolve() != args.prefix.resolve():
        raise ContractError("The compiler receipt identifies a different prefix")
    original = inventory(args.build)
    bootstrap = inventory(args.bootstrap / "usr")
    compiled = {name: row for name, row in inventory(args.build / "build").items()
                if Path(name).suffix.lower() in (".o", ".obj", ".a", ".dll", ".exe")}
    if ".libs/msys-crypt-2.dll" not in compiled:
        raise ContractError("A real already-built shared MSYS crypt library is required")
    args.output.mkdir(parents=True)
    for name in ("source", "build"):
        shutil.copytree(args.build / name, args.output / name)
    for name in ("stage", "temp", "home"):
        (args.output / name).mkdir()
    patch = Path(__file__).parent / "patches/libxcrypt-coff-private-refptr-test.patch"
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (args.prefix / "bin", args.bootstrap / "usr/bin",
                                           Path(os.environ["SystemRoot"]) / "System32")))
    env["HOME"] = str(args.output / "home")
    env["TMP"] = env["TEMP"] = str(args.output / "temp")
    script = Path(__file__).with_suffix(".sh")
    report = {"status": "failed", "original_receipt_sha256": digest(original_receipt),
              "compiler_receipt_sha256": digest(args.compiler_receipt),
              "patch_sha256": digest(patch), "driver_sha256": digest(script),
              "scope": "Original native library/test objects; explicit DLL closure and private COFF-reference test handling; no skipped tests"}
    try:
        result = subprocess.run([str(args.bootstrap / "usr/bin/patch.exe"), "--batch", "--forward", "--fuzz=0",
                                 "--no-backup-if-mismatch", "-p1", "-i", patch.resolve().as_posix()],
                                cwd=args.output / "source", env=env, capture_output=True, timeout=30)
        (args.output / "patch.log").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise ContractError("Libxcrypt test adaptation failed")
        with (args.output / "replay.log").open("xb") as log:
            report["process"] = run([args.bootstrap / "usr/bin/bash.exe", "--noprofile", "--norc",
                                     script.resolve().as_posix(), args.output, args.prefix, str(args.jobs)],
                                    cwd=args.output, env=env, log=log, timeout=1800)
        if not report["process"]["passed"]:
            raise ContractError("Native libxcrypt replay/install failed")
        after = {name: row for name, row in inventory(args.output / "build").items()
                 if Path(name).suffix.lower() in (".o", ".obj", ".a", ".dll", ".exe")}
        if after != compiled:
            raise ContractError("Replay or installation changed compiled libxcrypt/test inputs")
        if inventory(args.build) != original or inventory(args.bootstrap / "usr") != bootstrap:
            raise ContractError("An original build or bootstrap changed")
        verify_tree(args.prefix, args.compiler_receipt)
        verify_support(previous["support"], args.prefix / "bin/gcc.exe", args.prefix, env)
        files = inventory(args.output / "stage")
        for name in ("usr/bin/msys-crypt-2.dll", "usr/include/crypt.h", "usr/lib/libcrypt.a", "usr/lib/libcrypt.dll.a"):
            if name not in files:
                raise ContractError(f"Missing real crypt development payload: {name}")
        report.update({"status": "native-msys-libxcrypt-checked-restaged", "files": files,
                       "compiled_inputs": compiled, "upstream_summary_sha256": digest(args.output / "build/test-suite.log"),
                       "pending": ["Native installed DLL consumer/PE closure", "Final package admission"]})
    finally:
        report["original_build_unchanged"] = inventory(args.build) == original
        report["bootstrap_unchanged"] = inventory(args.bootstrap / "usr") == bootstrap
        report["compiler_unchanged"] = inventory(args.prefix) == producer["files"]
        report["compiled_inputs_unchanged"] = {
            name: row for name, row in inventory(args.output / "build").items()
            if Path(name).suffix.lower() in (".o", ".obj", ".a", ".dll", ".exe")
        } == compiled
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        if not all(report[name] for name in ("original_build_unchanged", "bootstrap_unchanged",
                                            "compiler_unchanged", "compiled_inputs_unchanged")):
            raise ContractError("Replay input integrity changed; failure evidence retained")
    print(report["status"])


if __name__ == "__main__":
    main()
