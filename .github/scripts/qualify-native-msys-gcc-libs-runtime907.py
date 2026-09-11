#!/usr/bin/env python3
"""Qualify the pinned native MSYS GCC runtime package against runtime 907."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess


RUNTIME_SHA256 = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
PACKAGE_SHA256 = "a4aa671c13fe09cb4dabb2a1528dee458b4960bb3d956808d1bba9443c878b6d"
PRODUCER_HANDOFF_SHA256 = "c403bee2810970a13f9f058e5cd60f5b86db14593be726d9c755b16d1ea6d48b"
CPP_TOOLCHAIN_RECEIPT_SHA256 = (
    "ed4fa0a4844ee05deca009dc9346320d701ae93cd9f299dc0185a5358001d41c"
)
DLL_SHA256 = {
    "msys-atomic-1.dll": "18a2a1cca534d4efb423049f2b358923c46388538ad0a9b3e67873181ca509be",
    "msys-gcc_s-seh-1.dll": "f6557576e81a261797104e1826d62aadd84e5492e5bc8f18f17a5a793b0cd8e6",
    "msys-gomp-1.dll": "a4e8c582d54345a043f506806ca1bac3988425e6fa1561cad39b9f7d984d410f",
    "msys-stdc++-6.dll": "ae65b3f8e92dd47a8851dcc675285b73cc0d84a98f7e5d8b56fedf2809684dac",
}


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


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


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


def imports(objdump: Path, image: Path) -> list[str]:
    return re.findall(r"DLL Name:\s*(\S+)", run([str(objdump), "-p", str(image)]).stdout)


def package_info(tar: Path, package: Path) -> dict[str, list[str]]:
    text = run([str(tar), "-xOf", str(package), ".PKGINFO"]).stdout
    values: dict[str, list[str]] = {}
    for line in text.splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            values.setdefault(key, []).append(value)
    return values


def decode_mtree_path(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def verify_mtree(extraction: Path) -> int:
    count = 0
    with gzip.open(extraction / ".MTREE", "rt", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line.startswith("./") or " sha256digest=" not in line:
                continue
            tokens = line.split()
            relative = decode_mtree_path(tokens[0][2:])
            fields = dict(token.split("=", 1) for token in tokens[1:] if "=" in token)
            path = extraction / relative
            if not path.is_file():
                raise RuntimeError(f"MTREE file is missing: {relative}")
            if int(fields["size"]) != path.stat().st_size:
                raise RuntimeError(f"MTREE size mismatch: {relative}")
            if fields["sha256digest"] != digest(path):
                raise RuntimeError(f"MTREE digest mismatch: {relative}")
            count += 1
    if not count:
        raise RuntimeError("MTREE did not contain file checksums")
    return count


def write_sources(output: Path) -> dict[str, Path]:
    sources = {
        "c": output / "consumer-c.c",
        "cxx": output / "consumer-cxx.cc",
        "openmp": output / "consumer-openmp.c",
        "atomic": output / "consumer-atomic.c",
    }
    sources["c"].write_text(
        """
#include <stdio.h>
int main(void) {
  volatile char guarded[64] = {0};
  volatile __int128 numerator = ((__int128)1 << 100) + 17;
  volatile __int128 denominator = 9;
  volatile __int128 quotient = numerator / denominator;
  guarded[0] = 7;
  if (guarded[0] != 7 || quotient == 0)
    return 2;
  puts("native-msys-runtime907-gcc-c-ok");
  return 0;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    sources["cxx"].write_text(
        """
#include <stdexcept>
#include <thread>
#include <vector>
#include <iostream>
int main() {
  volatile char guarded[64] = {0};
  int value = 0;
  std::thread worker([&] {
    try { throw std::runtime_error("runtime907"); }
    catch (const std::runtime_error&) { value = 42; }
  });
  worker.join();
  guarded[0] = static_cast<char>(value);
  if (guarded[0] != 42)
    return 2;
  std::cout << "native-msys-runtime907-gcc-cpp-ok\\n";
  return 0;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    sources["openmp"].write_text(
        """
#include <omp.h>
#include <stdio.h>
int main(void) {
  int sum = 0;
  #pragma omp parallel for reduction(+:sum)
  for (int i = 0; i < 100; ++i)
    sum += i;
  printf("native-msys-runtime907-gomp-sum=%d\\n", sum);
  return sum == 4950 ? 0 : 2;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    sources["atomic"].write_text(
        """
#include <stdio.h>
int main(void) {
  __int128 value = 1;
  __int128 old = __atomic_fetch_add(&value, 2, __ATOMIC_SEQ_CST);
  printf("native-msys-runtime907-atomic=%lld,%lld\\n",
         (long long)old, (long long)value);
  return old == 1 && value == 3 ? 0 : 2;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    return sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "package",
        "producer-handoff",
        "runtime",
        "toolchain",
        "toolchain-receipt",
        "bootstrap",
        "output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("A fresh output root is required")
    output.mkdir(parents=True)
    for directory in ("packages", "readback", "relocated-root", "home"):
        (output / directory).mkdir()

    require_digest(args.package, PACKAGE_SHA256, "Pinned gcc-libs package")
    require_digest(args.producer_handoff, PRODUCER_HANDOFF_SHA256, "Producer handoff")
    require_digest(args.runtime, RUNTIME_SHA256, "Runtime 907")
    require_digest(
        args.toolchain_receipt, CPP_TOOLCHAIN_RECEIPT_SHA256, "C++ toolchain receipt"
    )

    package = output / "packages" / args.package.name
    shutil.copy2(args.package, package)
    if digest(package) != PACKAGE_SHA256:
        raise RuntimeError("Copied package bytes changed")
    tar = args.bootstrap / "usr/bin/bsdtar.exe"
    readback = output / "readback"
    run([str(tar), "-xf", str(package), "-C", str(readback)])
    info = package_info(tar, package)
    expected_info = {
        "pkgname": ["gcc-libs"],
        "pkgver": ["15.0.1-1"],
        "arch": ["aarch64"],
        "license": [
            "spdx:LGPL-3.0-or-later AND GPL-3.0-or-later WITH GCC-exception-3.1"
        ],
    }
    for key, expected in expected_info.items():
        if info.get(key) != expected:
            raise RuntimeError(f"Unexpected PKGINFO {key}: {info.get(key)}")
    mtree_checks = verify_mtree(readback)
    markers = (
        b".copilot",
        b"session-state",
        b"c:/users",
        b"/mnt/c/users",
        b"c:/agtc-",
        b"/root/arm64-",
    )
    files = []
    for path in sorted(readback.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(readback).as_posix()
        if relative != ".MTREE":
            data = path.read_bytes().lower()
            utf16 = tuple(marker.decode("ascii").encode("utf-16le") for marker in markers)
            if any(marker in data for marker in markers + utf16):
                raise RuntimeError(f"Private producer path marker in {relative}")
        record = {"path": relative, "size": path.stat().st_size, "sha256": digest(path)}
        if path.suffix.lower() in (".dll", ".exe"):
            record["machine"] = pe_machine(path)
            if record["machine"] != "0xAA64":
                raise RuntimeError(f"Non-AA64 image in package: {relative}")
        files.append(record)
    for name, expected in DLL_SHA256.items():
        require_digest(readback / "usr/bin" / name, expected, name)

    root = output / "relocated-root"
    run([str(tar), "-xf", str(package), "-C", str(root)])
    bin_dir = root / "usr/bin"
    shutil.copy2(args.runtime, bin_dir / "msys-2.0.dll")
    sources = write_sources(output)
    executables = {
        "c": bin_dir / "gcc-libs-c.exe",
        "cxx": bin_dir / "gcc-libs-cxx.exe",
        "openmp": bin_dir / "gcc-libs-openmp.exe",
        "atomic": bin_dir / "gcc-libs-atomic.exe",
    }
    commands = {
        "c": [
            str(args.toolchain / "bin/gcc.exe"),
            "-O2",
            "-fstack-protector-strong",
            "-o",
            str(executables["c"]),
            str(sources["c"]),
        ],
        "cxx": [
            str(args.toolchain / "bin/g++.exe"),
            "-O2",
            "-fstack-protector-strong",
            "-pthread",
            "-o",
            str(executables["cxx"]),
            str(sources["cxx"]),
        ],
        "openmp": [
            str(args.toolchain / "bin/gcc.exe"),
            "-O2",
            "-fopenmp",
            "-o",
            str(executables["openmp"]),
            str(sources["openmp"]),
        ],
        "atomic": [
            str(args.toolchain / "bin/gcc.exe"),
            "-O2",
            "-o",
            str(executables["atomic"]),
            str(sources["atomic"]),
            "-latomic",
        ],
    }
    compile_results = {name: run(command) for name, command in commands.items()}
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    env["PATH"] = os.pathsep.join(
        (str(bin_dir), str(Path(os.environ["SystemRoot"]) / "System32"))
    )
    env["HOME"] = env["USERPROFILE"] = str(output / "home")
    run_results = {name: run([str(path)], env=env) for name, path in executables.items()}
    expected_outputs = {
        "c": "native-msys-runtime907-gcc-c-ok",
        "cxx": "native-msys-runtime907-gcc-cpp-ok",
        "openmp": "native-msys-runtime907-gomp-sum=4950",
        "atomic": "native-msys-runtime907-atomic=1,3",
    }
    for name, expected in expected_outputs.items():
        if expected not in run_results[name].stdout:
            raise RuntimeError(f"Unexpected {name} control output")

    objdump = args.toolchain / "bin/objdump.exe"
    controls = {}
    for name, executable in executables.items():
        controls[name] = {
            "compile_exit": compile_results[name].returncode,
            "run_exit": run_results[name].returncode,
            "stdout": run_results[name].stdout.strip(),
            "machine": pe_machine(executable),
            "sha256": digest(executable),
            "imports": imports(objdump, executable),
        }
    required_imports = {
        "c": {"msys-2.0.dll", "msys-gcc_s-seh-1.dll"},
        "cxx": {"msys-2.0.dll", "msys-gcc_s-seh-1.dll", "msys-stdc++-6.dll"},
        "openmp": {"msys-2.0.dll", "msys-gomp-1.dll"},
        "atomic": {"msys-2.0.dll", "msys-atomic-1.dll"},
    }
    for name, required in required_imports.items():
        missing = required.difference(controls[name]["imports"])
        if missing:
            raise RuntimeError(f"{name} control omitted expected imports: {sorted(missing)}")

    handoff = {
        "schema": 1,
        "status": "native-msys-gcc-libs-runtime907-qualified",
        "provider": "native-msys-gcc-libs",
        "version": "15.0.1-1",
        "package": {
            "path": str(package),
            "sha256": digest(package),
            "bytesUnchangedFromPriorPackage": True,
            "pkginfo": info,
            "mtreeFileChecks": mtree_checks,
            "files": files,
        },
        "runtimeCohort": {
            "path": str(args.runtime.resolve()),
            "sha256": RUNTIME_SHA256,
            "ownership": "external; not packaged",
        },
        "controls": controls,
        "pathScope": "relocated package bin plus Windows System32 only",
        "sourceEvidence": {
            "producerHandoff": {
                "path": str(args.producer_handoff.resolve()),
                "sha256": PRODUCER_HANDOFF_SHA256,
            },
            "qualifiedCppToolchainReceipt": {
                "path": str(args.toolchain_receipt.resolve()),
                "sha256": CPP_TOOLCHAIN_RECEIPT_SHA256,
            },
            "sourceCommit": "5688a17320e775944bbe795010ebe7e89fc7a628",
            "recipeCommit": "dbd17835da05daa9e70a0e16d01e97892928a157",
            "recipeSha256": (
                "55b022218c2519bfa1ca50224a2cd7e03dec0f9feada54c19354f8ef3408a1c8"
            ),
        },
        "limitations": [
            "This qualifies the unchanged GCC runtime-library package against runtime 907.",
            "It does not admit or transfer ownership of runtime 907 or the compiler SDK.",
            "Unsupported upstream libquadmath and libvtv remain excluded as recorded by the producer.",
        ],
    }
    (output / "handoff.json").write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    export = {
        "schema": 1,
        "provider": "native-msys-gcc-libs",
        "version": "15.0.1-1",
        "packages": [
            {"name": "gcc-libs", "path": str(package), "sha256": digest(package)}
        ],
        "proof": {
            "path": str(output / "handoff.json"),
            "sha256": digest(output / "handoff.json"),
        },
        "externalDependencies": {"msys2-runtime": RUNTIME_SHA256},
    }
    (output / "export.json").write_text(
        json.dumps(export, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "export": str(output / "export.json"),
                "export_sha256": digest(output / "export.json"),
                "handoff": str(output / "handoff.json"),
                "handoff_sha256": digest(output / "handoff.json"),
                "package": str(package),
                "package_sha256": digest(package),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
