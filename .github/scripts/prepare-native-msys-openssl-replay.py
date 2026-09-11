"""Prepare a test-only OpenSSL tree without changing the compiled binaries."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inventory(root):
    return {
        path.relative_to(root).as_posix(): {
            "sha256": digest(path),
            "size": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--runtime-dll", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--test-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    build = args.build.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing existing output: {output}")

    source = build / "source"
    installed = build / "stage/usr/bin"
    for source_name, installed_name in (
        ("apps/openssl.exe", "openssl.exe"),
        ("msys-crypto-3.dll", "msys-crypto-3.dll"),
        ("msys-ssl-3.dll", "msys-ssl-3.dll"),
    ):
        if digest(source / source_name) != digest(installed / installed_name):
            raise SystemExit(f"Installed binary differs from build output: {installed_name}")

    before = inventory(source)
    shutil.copytree(source, output)

    patch_path = args.test_tools / "patches/openssl-native-test-transport.patch"
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    env["PATH"] = os.pathsep.join(
        (str(args.bootstrap / "usr/bin"), str(Path(os.environ["SystemRoot"]) / "System32"))
    )
    result = subprocess.run(
        [
            str(args.bootstrap / "usr/bin/patch.exe"),
            "--batch",
            "--forward",
            "--fuzz=0",
            "--no-backup-if-mismatch",
            "-p1",
            "-i",
            patch_path.resolve().as_posix(),
        ],
        cwd=output,
        env=env,
        capture_output=True,
        timeout=30,
    )
    output.with_name(output.name + ".patch.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit("OpenSSL native test transport patch failed")

    adaptations_path = args.test_tools / "openssl_test_patches.py"
    sys.path.insert(0, str(args.test_tools.resolve()))
    spec = importlib.util.spec_from_file_location("openssl_test_patches", adaptations_path)
    adaptations = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adaptations)
    for name in adaptations.TEST_FILES:
        path = output / name
        path.write_text(adaptations.adapt_test(name, path.read_text()), newline="\n")

    shutil.copyfile(args.runtime_dll, output / "msys-2.0.dll")
    after = inventory(output)
    changed = sorted(
        name for name in after.keys() | before.keys() if after.get(name) != before.get(name)
    )
    expected = sorted(
        [
            "msys-2.0.dll",
            "util/perl/OpenSSL/Test.pm",
            *adaptations.TEST_FILES,
        ]
    )
    if changed != expected:
        raise SystemExit(f"Unexpected replay changes: {changed}")
    if inventory(source) != before:
        raise SystemExit("Original OpenSSL build tree changed")

    manifest = {
        "schema": 1,
        "status": "native-msys-openssl-test-replay-prepared",
        "scope": "Compiled binaries unchanged; bounded test-driver adaptations only",
        "runtime_dll": {
            "path": str(args.runtime_dll.resolve()),
            "sha256": digest(args.runtime_dll),
        },
        "transport_patch_sha256": digest(patch_path),
        "test_adaptation_sha256": digest(adaptations_path),
        "changed_files": changed,
        "files": after,
    }
    output.with_name(output.name + ".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
