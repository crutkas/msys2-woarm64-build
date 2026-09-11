#!/usr/bin/env python3
"""Run a pinned MSYS GnuPG-stack PKGBUILD with the qualified ARM64 toolchain."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys


RUNTIME_907_SHA256 = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
APPROVED_CC1_SHA256 = "b8046275497c4e8f4d056530ef2e956d1b7672a0e5eb15ad56fde5bf44e76b0a"
APPROVED_CC1PLUS_SHA256 = "f003aec1b083e8d54ab93b6d1d0d901cd659708f5fc95279dad4f0f24feb3c6c"
OBSERVER_MANIFEST_SHA256 = "1f5384459cc239e0b373b05f42e60ef06ec580d45046e1484a4ba4d46de5b3fa"
DISPATCHER_SHA256 = "8617991c49f77b106237e87c453cfa06b7eb64303cd3e8e20625e5df9fbdc63d"
GETTEXT_ARCHIVE_SHA256 = "f778817d4936f46c0538d012d43391122542796b85941cfe5fff9d906d69d5f1"
MIN_FREE_BYTES = 8 * 1024**3


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def require_digest(path: Path, expected: str, label: str) -> None:
    actual = digest(path)
    if actual != expected:
        raise RuntimeError(f"{label} changed: expected {expected}, got {actual}")


def pe_machine(path: Path) -> str:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise RuntimeError(f"Not a PE image: {path}")
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0":
            raise RuntimeError(f"Invalid PE signature: {path}")
        return f"0x{struct.unpack('<H', stream.read(2))[0]:04X}"


def cygpath(bootstrap: Path, path: Path) -> str:
    result = subprocess.run(
        [str(bootstrap / "usr/bin/cygpath.exe"), "-u", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "output",
        "bootstrap",
        "toolchain",
        "sdk",
        "gpg-home",
        "native-runner-root",
        "native-driver",
        "dispatcher",
        "gettext-data",
    ):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--jobs", required=True, choices=(1,), type=int)
    parser.add_argument("--timeout", default=7200, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    recipe = output / "recipe"
    config = output / "makepkg.conf"
    if not recipe.is_dir() or not config.is_file():
        raise RuntimeError("The prepared recipe and makepkg.conf are required")
    if any((output / name).exists() for name in ("native-job.json", "build-result.json")):
        raise RuntimeError("Refusing to overwrite an observed build result")
    if shutil.disk_usage(output).free < MIN_FREE_BYTES:
        raise RuntimeError("At least 8 GiB of free disk is required")

    require_digest(args.sdk / "usr/bin/msys-2.0.dll", RUNTIME_907_SHA256, "Runtime 907")
    require_digest(args.toolchain / "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1.exe",
                   APPROVED_CC1_SHA256, "Approved compiler cc1")
    require_digest(args.toolchain / "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1plus.exe",
                   APPROVED_CC1PLUS_SHA256, "Approved compiler cc1plus")
    require_digest(args.native_driver.with_name(args.native_driver.name + ".manifest.json"),
                   OBSERVER_MANIFEST_SHA256, "Native observer manifest")
    require_digest(args.dispatcher, DISPATCHER_SHA256, "Native test dispatcher")
    require_digest(args.gettext_data / "archive.dir.tar.xz", GETTEXT_ARCHIVE_SHA256,
                   "Gettext autopoint infrastructure")

    sys.path.insert(0, str(args.native_runner_root.resolve()))
    native_job_runner = importlib.import_module("native_job_runner")

    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    env["PATH"] = os.pathsep.join(
        (
            str(args.toolchain.resolve() / "bin"),
            str(args.bootstrap.resolve() / "usr/bin"),
            str(Path(os.environ["SystemRoot"]) / "System32"),
        )
    )
    env.update(
        {
            "HOME": str(output / "home"),
            "USERPROFILE": str(output / "home"),
            "GNUPGHOME": str(args.gpg_home.resolve()),
            "TMP": str(output / "temp"),
            "TEMP": str(output / "temp"),
            "TMPDIR": str(output / "temp"),
            "XDG_CACHE_HOME": str(output / "cache"),
            "CCACHE_DISABLE": "1",
            "MAKEFLAGS": "-j1",
            "MFLAGS": "-j1",
            "OMP_NUM_THREADS": "1",
            "CMAKE_BUILD_PARALLEL_LEVEL": "1",
            "WOARM64_NATIVE_ARG_CONVERSION": "none",
            "WOARM64_NATIVE_TEST_ROOT": str(output),
            "WOARM64_NATIVE_EXIT_DIR": str(output / "native-exits"),
            "WOARM64_NATIVE_DRIVER_ROOT": str(args.native_driver.resolve()),
            "WOARM64_TEST_DISPATCHER": cygpath(args.bootstrap, args.dispatcher.resolve()),
        }
    )
    for directory in ("cache", "home", "native-exits", "temp"):
        (output / directory).mkdir(exist_ok=True)

    sdk = cygpath(args.bootstrap, args.sdk.resolve())
    toolchain = cygpath(args.bootstrap, args.toolchain.resolve())
    recipe_posix = cygpath(args.bootstrap, recipe)
    config_posix = cygpath(args.bootstrap, config)
    gpg_home = cygpath(args.bootstrap, args.gpg_home.resolve())
    gettext_data = cygpath(args.bootstrap, args.gettext_data.resolve())
    command_text = f"""
set -euo pipefail
export PATH='{sdk}/usr/bin:{toolchain}/bin:/usr/bin'
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm STRIP=strip OBJDUMP=objdump
export GNUPGHOME='{gpg_home}'
export gettext_datadir='{gettext_data}'
export MSYSTEM=MSYS CHERE_INVOKING=1 MSYS2_PATH_TYPE=minimal
export MSYS2_ARG_CONV_EXCL='-D;-ffile-prefix-map=;-fdebug-prefix-map=;-fmacro-prefix-map='
export PKG_CONFIG_PATH='{sdk}/usr/lib/pkgconfig'
export CPATH='{sdk}/usr/include'
export LIBRARY_PATH='{sdk}/usr/lib'
test "$(gcc -dumpmachine)" = aarch64-pc-cygwin
cd '{recipe_posix}'
/usr/bin/makepkg --config '{config_posix}' --verifysource --nodeps --noconfirm
exec /usr/bin/makepkg --config '{config_posix}' --cleanbuild --force --nodeps --noconfirm
"""
    command = [
        str(args.bootstrap.resolve() / "usr/bin/bash.exe"),
        "--noprofile",
        "--norc",
        "-lc",
        command_text,
    ]
    process = native_job_runner.run_observed(
        command,
        cwd=output,
        env=env,
        log_path=output / "build.log",
        result_path=output / "native-job.json",
        relay_records=output / "native-exits",
        timeout=args.timeout,
        driver_prefix=args.native_driver.resolve(),
    )
    packages = sorted((output / "packages").glob("*.pkg.tar.zst"))
    result = {
        "schema": 1,
        "status": "passed" if process["passed"] and packages else "failed",
        "jobs": args.jobs,
        "runtime": {
            "path": str(args.sdk.resolve() / "usr/bin/msys-2.0.dll"),
            "sha256": RUNTIME_907_SHA256,
            "ownership": "external build/test dependency; not packaged here",
        },
        "compiler": {
            "target": "aarch64-pc-cygwin",
            "cc1_sha256": APPROVED_CC1_SHA256,
            "cc1plus_sha256": APPROVED_CC1PLUS_SHA256,
            "build_host_runtime_note": (
                "The qualified compiler's own runtime is separate from the runtime-907 "
                "target execution root."
            ),
        },
        "process": process,
        "packages": [
            {"name": path.name, "path": str(path), "sha256": digest(path)}
            for path in packages
        ],
        "pe_images": [],
    }
    for path in sorted((output / "build").rglob("*")):
        if path.is_file() and path.suffix.lower() in (".exe", ".dll"):
            machine = pe_machine(path)
            result["pe_images"].append(
                {
                    "path": str(path.relative_to(output)).replace("\\", "/"),
                    "machine": machine,
                    "sha256": digest(path),
                }
            )
            if machine != "0xAA64":
                result["status"] = "failed"
    (output / "build-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if result["status"] != "passed":
        raise RuntimeError("Native package build or target identity validation failed")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
