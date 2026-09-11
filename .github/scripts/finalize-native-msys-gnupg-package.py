#!/usr/bin/env python3
"""Seal, read back, and relocate a native MSYS GnuPG dependency package."""

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
import tempfile


SOURCE_DATE_EPOCH = "1789148170"
RUNTIME_SHA256 = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
ICONV_SHA256 = "86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215"
INTL_SHA256 = "44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c"
PROFILES = {
    "libgpg-error": {
        "version": "1.61-1",
        "provider": "native-msys-libgpg-error",
        "status": "native-msys-libgpg-error-package-qualified",
        "packages": {
            "libgpg-error": {
                "depends": ["sh", "libiconv", "libintl"],
                "required": [
                    "usr/bin/gpg-error.exe",
                    "usr/bin/msys-gpg-error-0.dll",
                    "usr/share/libgpg-error/errorref.txt",
                ],
            },
            "libgpg-error-devel": {
                "depends": ["libiconv-devel", "gettext-devel"],
                "required": [
                    "usr/include/gpg-error.h",
                    "usr/lib/libgpg-error.a",
                    "usr/lib/libgpg-error.dll.a",
                    "usr/lib/pkgconfig/gpg-error.pc",
                ],
            },
        },
        "upstream_tests": {"passed": 14, "skipped": 1, "failed": 0},
    },
    "npth": {
        "version": "1.8-1",
        "provider": "native-msys-npth",
        "status": "native-msys-npth-package-qualified",
        "packages": {
            "libnpth": {
                "depends": ["gcc-libs"],
                "required": ["usr/bin/msys-npth-0.dll"],
            },
            "libnpth-devel": {
                "depends": ["libnpth=1.8"],
                "required": [
                    "usr/include/npth.h",
                    "usr/lib/libnpth.a",
                    "usr/lib/libnpth.dll.a",
                    "usr/lib/pkgconfig/npth.pc",
                ],
            },
        },
        "upstream_tests": {
            "status": "not-run",
            "reason": "The exact pinned MSYS2 recipe comments out make check.",
        },
    },
    "gmp": {
        "version": "6.3.0-1",
        "provider": "native-msys-gmp",
        "status": "native-msys-gmp-package-qualified",
        "packages": {
            "gmp": {
                "depends": [],
                "required": [
                    "usr/bin/msys-gmp-10.dll",
                    "usr/bin/msys-gmpxx-4.dll",
                    "usr/share/info/gmp.info.gz",
                ],
            },
            "gmp-devel": {
                "depends": ["gmp=6.3.0"],
                "required": [
                    "usr/include/gmp.h",
                    "usr/include/gmpxx.h",
                    "usr/lib/libgmp.dll.a",
                    "usr/lib/libgmpxx.dll.a",
                    "usr/lib/pkgconfig/gmp.pc",
                    "usr/lib/pkgconfig/gmpxx.pc",
                ],
            },
        },
        "upstream_tests": {"passed": 199, "skipped": 1, "failed": 0},
    },
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


def run(command: list[str], *, env: dict[str, str] | None = None,
        cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def cygpath(bootstrap: Path, path: Path) -> str:
    return run([str(bootstrap / "usr/bin/cygpath.exe"), "-u", str(path)]).stdout.strip()


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


def package_info(tar: Path, package: Path) -> dict[str, list[str]]:
    text = run([str(tar), "-xOf", str(package), ".PKGINFO"]).stdout
    values: dict[str, list[str]] = {}
    for line in text.splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            values.setdefault(key, []).append(value)
    return values


def sanitize_package(
    bootstrap: Path, tar: Path, package: Path, output: Path, profile_name: str
) -> dict:
    extraction = output / "work" / f"{package.name}.root"
    extraction.mkdir(parents=True)
    run([str(tar), "-xf", str(package), "-C", str(extraction)])
    buildinfo = extraction / ".BUILDINFO"
    original = buildinfo.read_text(encoding="utf-8")
    lines = []
    for line in original.splitlines():
        if line.startswith("builddir ="):
            line = "builddir = /usr/src/packages/build"
        elif line.startswith("startdir ="):
            line = "startdir = /usr/src/packages/recipe"
        lines.append(line)
    buildinfo.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (extraction / ".MTREE").unlink()
    payload_changes = []
    if profile_name == "gmp" and package.name.startswith("gmp-devel-"):
        header = extraction / "usr/include/gmp.h"
        original_header_sha256 = digest(header)
        header_text = header.read_text(encoding="utf-8")
        header_text, substitutions = re.subn(
            r'^#define __GMP_CFLAGS ".*"$',
            (
                '#define __GMP_CFLAGS "-O2 -g -std=gnu17 '
                '-fstack-protector-strong -Wno-attributes"'
            ),
            header_text,
            count=1,
            flags=re.MULTILINE,
        )
        if substitutions != 1:
            raise RuntimeError("Could not canonicalize generated GMP compiler flags")
        header.write_text(header_text, encoding="utf-8", newline="\n")
        payload_changes.append(
            {
                "path": "usr/include/gmp.h",
                "original_sha256": original_header_sha256,
                "sealed_sha256": digest(header),
                "change": (
                    "Canonicalized generated __GMP_CFLAGS provenance to the exact "
                    "effective public flags while removing private prefix-map roots."
                ),
            }
        )

    sealed = output / "packages" / package.name
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    env.update(
        {
            "PACKAGE_ROOT": str(extraction),
            "PACKAGE_OUTPUT": str(sealed),
            "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
        }
    )
    command = [
        str(bootstrap / "usr/bin/bash.exe"),
        "--noprofile",
        "--norc",
        "-lc",
        (
            "set -euo pipefail; export PATH=/usr/bin; "
            'cd "$(cygpath -u "$PACKAGE_ROOT")"; '
            'find . -exec touch -h -d @"$SOURCE_DATE_EPOCH" {} +; '
            "export LC_COLLATE=C; shopt -s dotglob globstar; "
            "printf '%s\\0' **/* | LANG=C bsdtar -cnf - --format=mtree "
            "--options='!all,use-set,type,uid,gid,mode,time,size,sha256,link' "
            "--null --files-from - --exclude .MTREE | gzip -c -f -n > .MTREE; "
            'touch -d @"$SOURCE_DATE_EPOCH" .MTREE; '
            "printf '%s\\0' **/* | LANG=C bsdtar --no-fflags --no-read-sparse "
            "--no-xattrs --uid 1 --uname root --gid 1 --gname root "
            '-cnf - --null --files-from - | zstd -c -T1 -z -q - > '
            '"$(cygpath -u "$PACKAGE_OUTPUT")"'
        ),
    ]
    run(command, env=env)
    return {
        "name": package.name,
        "original_sha256": digest(package),
        "sealed_sha256": digest(sealed),
        "change": (
            ".BUILDINFO builddir/startdir were canonicalized; .MTREE and the "
            "package container were regenerated."
        ),
        "payload_changes": payload_changes,
    }


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
        raise RuntimeError("MTREE did not contain any file checksums")
    return count


def inspect_package(
    tar: Path,
    package: Path,
    output: Path,
    private_markers: list[tuple[str, bytes, bytes]],
    profile: dict,
) -> dict:
    info = package_info(tar, package)
    name = info["pkgname"][0]
    expected = profile["packages"]
    if name not in expected:
        raise RuntimeError(f"Unexpected package: {name}")
    if info.get("pkgver") != [profile["version"]] or info.get("arch") != ["aarch64"]:
        raise RuntimeError(f"Unexpected package identity: {name}")
    if info.get("depend", []) != expected[name]["depends"]:
        raise RuntimeError(f"Unexpected dependencies for {name}: {info.get('depend', [])}")

    extraction = output / "readback" / package.name
    extraction.mkdir(parents=True)
    run([str(tar), "-xf", str(package), "-C", str(extraction)])
    mtree_files = verify_mtree(extraction)
    files = []
    for path in sorted(extraction.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(extraction).as_posix()
        if relative != ".MTREE":
            lowered = path.read_bytes().lower()
            hits = [
                label
                for label, ascii_marker, utf16_marker in private_markers
                if ascii_marker in lowered or utf16_marker in lowered
            ]
            if hits:
                raise RuntimeError(f"Private path marker in {name}:{relative}: {hits}")
        record = {"path": relative, "size": path.stat().st_size, "sha256": digest(path)}
        if path.suffix.lower() in (".exe", ".dll"):
            record["machine"] = pe_machine(path)
            if record["machine"] != "0xAA64":
                raise RuntimeError(f"Non-AA64 image in {name}:{relative}")
        files.append(record)
    for required in expected[name]["required"]:
        if not (extraction / required).is_file():
            raise RuntimeError(f"{name} omitted required file: {required}")
    if (extraction / "usr/bin/msys-2.0.dll").exists():
        raise RuntimeError("Package stole MSYS runtime ownership")
    return {
        "name": name,
        "path": f"packages/{package.name}",
        "sha256": digest(package),
        "pkginfo": info,
        "mtree_file_checks": mtree_files,
        "files": files,
    }


def imports(objdump: Path, image: Path) -> list[str]:
    text = run([str(objdump), "-p", str(image)]).stdout
    return re.findall(r"DLL Name:\s*(\S+)", text)


def libgpg_error_relocated_control(
    args: argparse.Namespace, packages: list[Path], output: Path
) -> dict:
    root = output / "relocated-root"
    root.mkdir()
    tar = args.bootstrap / "usr/bin/bsdtar.exe"
    for package in packages:
        run([str(tar), "-xf", str(package), "-C", str(root)])
    bin_dir = root / "usr/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for source, name, expected in (
        (args.runtime, "msys-2.0.dll", RUNTIME_SHA256),
        (args.iconv, "msys-iconv-2.dll", ICONV_SHA256),
        (args.intl, "msys-intl-8.dll", INTL_SHA256),
    ):
        require_digest(source, expected, name)
        shutil.copy2(source, bin_dir / name)

    source = output / "consumer.c"
    source.write_text(
        """
#include <gpg-error.h>
#include <windows.h>
#include <stdio.h>

int main(void) {
  HMODULE module;
  char module_path[32768];
  char *sysconf_path;
  const char *version = gpg_error_check_version(NULL);
  if (!version)
    return 2;
  module = GetModuleHandleA("msys-gpg-error-0.dll");
  if (!module || !GetModuleFileNameA(module, module_path, sizeof(module_path)))
    return 3;
  sysconf_path = gpgrt_fconcat(GPGRT_FCONCAT_SYSCONF, "provider-control.conf", NULL);
  if (!sysconf_path)
    return 4;
  printf("version=%s\\nerror=%s\\ndll=%s\\nsysconf=%s\\n",
         version, gpg_strerror(GPG_ERR_GENERAL), module_path, sysconf_path);
  gpgrt_free(sysconf_path);
  return 0;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    consumer = root / "usr/bin/libgpg-error-consumer.exe"
    compile_result = run(
        [
            str(args.toolchain / "bin/gcc.exe"),
            "-O2",
            "-o",
            str(consumer),
            str(source),
            f"-I{root / 'usr/include'}",
            f"-L{root / 'usr/lib'}",
            "-lgpg-error",
        ],
        timeout=600,
    )
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    env["PATH"] = os.pathsep.join((str(bin_dir), str(Path(os.environ["SystemRoot"]) / "System32")))
    env["HOME"] = env["USERPROFILE"] = str(output / "home")
    Path(env["HOME"]).mkdir()
    version = run([str(bin_dir / "gpg-error.exe"), "--version"], env=env)
    consumer_result = run([str(consumer)], env=env)
    loaded = re.search(r"^dll=(.+)$", consumer_result.stdout, flags=re.MULTILINE)
    if not loaded or Path(loaded.group(1)).resolve() != (bin_dir / "msys-gpg-error-0.dll").resolve():
        raise RuntimeError("Consumer did not load the relocated libgpg-error DLL")
    sysconf = re.search(r"^sysconf=(.+)$", consumer_result.stdout, flags=re.MULTILINE)
    if not sysconf or sysconf.group(1) != "/usr/etc/provider-control.conf":
        raise RuntimeError("Consumer did not resolve the canonical /usr/etc sysconf path")

    errorref = root / "usr/share/libgpg-error/errorref.txt"
    desc_present = run(
        [str(bin_dir / "gpg-error.exe"), "--desc", "GPG_ERR_BAD_SIGNATURE"], env=env
    )
    errorref_hidden = errorref.with_suffix(".txt.provider-control-hidden")
    errorref.rename(errorref_hidden)
    try:
        desc_absent = run(
            [str(bin_dir / "gpg-error.exe"), "--desc", "GPG_ERR_BAD_SIGNATURE"], env=env
        )
    finally:
        errorref_hidden.rename(errorref)
    if desc_present.stdout.strip() == desc_absent.stdout.strip():
        raise RuntimeError("gpg-error did not consume the relocated errorref.txt")

    locale_env = env.copy()
    locale_env.update({"LANG": "de_DE.UTF-8", "LC_ALL": "de_DE.UTF-8", "LANGUAGE": "de"})
    catalog = root / "usr/share/locale/de/LC_MESSAGES/libgpg-error.mo"
    locale_present = run([str(bin_dir / "gpg-error.exe"), "--help"], env=locale_env)
    catalog_hidden = catalog.with_suffix(".mo.provider-control-hidden")
    catalog.rename(catalog_hidden)
    try:
        locale_absent = run([str(bin_dir / "gpg-error.exe"), "--help"], env=locale_env)
    finally:
        catalog_hidden.rename(catalog)
    if locale_present.stdout.strip() == locale_absent.stdout.strip():
        raise RuntimeError("gpg-error did not consume the relocated locale catalog")
    return {
        "compile_exit": compile_result.returncode,
        "consumer_exit": consumer_result.returncode,
        "consumer_stdout": consumer_result.stdout.strip(),
        "gpg_error_version_exit": version.returncode,
        "gpg_error_version_stdout": version.stdout.strip(),
        "errorref_control": {
            "present_exit": desc_present.returncode,
            "present_stdout": desc_present.stdout.strip(),
            "absent_exit": desc_absent.returncode,
            "absent_stdout": desc_absent.stdout.strip(),
            "outputs_differ": True,
        },
        "locale_control": {
            "locale": "de_DE.UTF-8",
            "present_exit": locale_present.returncode,
            "absent_exit": locale_absent.returncode,
            "present_stdout_sha256": hashlib.sha256(
                locale_present.stdout.encode("utf-8")
            ).hexdigest(),
            "absent_stdout_sha256": hashlib.sha256(
                locale_absent.stdout.encode("utf-8")
            ).hexdigest(),
            "outputs_differ": True,
        },
        "consumer_machine": pe_machine(consumer),
        "consumer_sha256": digest(consumer),
        "imports": {
            "msys-gpg-error-0.dll": imports(args.toolchain / "bin/objdump.exe",
                                             bin_dir / "msys-gpg-error-0.dll"),
            "gpg-error.exe": imports(args.toolchain / "bin/objdump.exe",
                                     bin_dir / "gpg-error.exe"),
            "consumer": imports(args.toolchain / "bin/objdump.exe", consumer),
        },
        "runtime_dependencies": {
            name: digest(bin_dir / name)
            for name in ("msys-2.0.dll", "msys-iconv-2.dll", "msys-intl-8.dll")
        },
    }


def npth_relocated_control(
    args: argparse.Namespace, packages: list[Path], output: Path
) -> dict:
    root = output / "relocated-root"
    root.mkdir()
    tar = args.bootstrap / "usr/bin/bsdtar.exe"
    for package in packages:
        run([str(tar), "-xf", str(package), "-C", str(root)])
    bin_dir = root / "usr/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    require_digest(args.runtime, RUNTIME_SHA256, "msys-2.0.dll")
    shutil.copy2(args.runtime, bin_dir / "msys-2.0.dll")

    source = output / "consumer.c"
    source.write_text(
        """
#include <npth.h>
#include <windows.h>
#include <stdio.h>

int main(void) {
  HMODULE module;
  char module_path[32768];
  npth_mutex_t mutex = NPTH_MUTEX_INITIALIZER;
  int rc = npth_init();
  if (rc)
    return 2;
  rc = npth_mutex_lock(&mutex);
  if (rc)
    return 3;
  rc = npth_mutex_unlock(&mutex);
  if (rc)
    return 4;
  module = GetModuleHandleA("msys-npth-0.dll");
  if (!module || !GetModuleFileNameA(module, module_path, sizeof(module_path)))
    return 5;
  printf("mutex=passed\\ndll=%s\\n", module_path);
  return 0;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    consumer = root / "usr/bin/npth-consumer.exe"
    compile_result = run(
        [
            str(args.toolchain / "bin/gcc.exe"),
            "-O2",
            "-o",
            str(consumer),
            str(source),
            f"-I{root / 'usr/include'}",
            f"-L{root / 'usr/lib'}",
            "-lnpth",
        ],
        timeout=600,
    )
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    env["PATH"] = os.pathsep.join(
        (str(bin_dir), str(Path(os.environ["SystemRoot"]) / "System32"))
    )
    env["HOME"] = env["USERPROFILE"] = str(output / "home")
    Path(env["HOME"]).mkdir()
    consumer_result = run([str(consumer)], env=env)
    loaded = re.search(r"^dll=(.+)$", consumer_result.stdout, flags=re.MULTILINE)
    if not loaded or Path(loaded.group(1)).resolve() != (bin_dir / "msys-npth-0.dll").resolve():
        raise RuntimeError("Consumer did not load the relocated npth DLL")
    return {
        "compile_exit": compile_result.returncode,
        "consumer_exit": consumer_result.returncode,
        "consumer_stdout": consumer_result.stdout.strip(),
        "consumer_machine": pe_machine(consumer),
        "consumer_sha256": digest(consumer),
        "imports": {
            "msys-npth-0.dll": imports(
                args.toolchain / "bin/objdump.exe", bin_dir / "msys-npth-0.dll"
            ),
            "consumer": imports(args.toolchain / "bin/objdump.exe", consumer),
        },
        "runtime_dependencies": {"msys-2.0.dll": digest(bin_dir / "msys-2.0.dll")},
    }


def gmp_relocated_control(
    args: argparse.Namespace, packages: list[Path], output: Path
) -> dict:
    root = output / "relocated-root"
    root.mkdir()
    tar = args.bootstrap / "usr/bin/bsdtar.exe"
    for package in packages:
        run([str(tar), "-xf", str(package), "-C", str(root)])
    bin_dir = root / "usr/bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    require_digest(args.runtime, RUNTIME_SHA256, "msys-2.0.dll")
    shutil.copy2(args.runtime, bin_dir / "msys-2.0.dll")

    c_source = output / "consumer.c"
    c_source.write_text(
        """
#include <gmp.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {
  HMODULE module;
  char module_path[32768];
  mpz_t left, right, product;
  char *value;
  mpz_inits(left, right, product, NULL);
  mpz_set_str(left, "12345678901234567890", 10);
  mpz_set_ui(right, 9);
  mpz_mul(product, left, right);
  value = mpz_get_str(NULL, 10, product);
  module = GetModuleHandleA("msys-gmp-10.dll");
  if (!module || !GetModuleFileNameA(module, module_path, sizeof(module_path)))
    return 2;
  printf("product=%s\\ndll=%s\\n", value, module_path);
  free(value);
  mpz_clears(left, right, product, NULL);
  return 0;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    cxx_source = output / "consumer.cc"
    cxx_source.write_text(
        """
#include <gmpxx.h>
#include <windows.h>
#include <iostream>

int main() {
  char gmp_path[32768];
  char gmpxx_path[32768];
  mpz_class left("12345678901234567890");
  mpz_class product = left * 9;
  HMODULE gmp = GetModuleHandleA("msys-gmp-10.dll");
  HMODULE gmpxx = GetModuleHandleA("msys-gmpxx-4.dll");
  if (!gmp || !gmpxx
      || !GetModuleFileNameA(gmp, gmp_path, sizeof(gmp_path))
      || !GetModuleFileNameA(gmpxx, gmpxx_path, sizeof(gmpxx_path)))
    return 2;
  std::cout << "product=" << product << "\\ngmp=" << gmp_path
            << "\\ngmpxx=" << gmpxx_path << "\\n";
  return 0;
}
""".lstrip(),
        encoding="utf-8",
        newline="\n",
    )
    c_consumer = bin_dir / "gmp-c-consumer.exe"
    cxx_consumer = bin_dir / "gmp-cxx-consumer.exe"
    c_compile = run(
        [
            str(args.toolchain / "bin/gcc.exe"),
            "-O2",
            "-fstack-protector-strong",
            "-o",
            str(c_consumer),
            str(c_source),
            f"-I{root / 'usr/include'}",
            f"-L{root / 'usr/lib'}",
            "-lgmp",
        ],
        timeout=600,
    )
    cxx_compile = run(
        [
            str(args.toolchain / "bin/g++.exe"),
            "-O2",
            "-fstack-protector-strong",
            "-static-libgcc",
            "-static-libstdc++",
            "-o",
            str(cxx_consumer),
            str(cxx_source),
            f"-I{root / 'usr/include'}",
            f"-L{root / 'usr/lib'}",
            "-lgmpxx",
            "-lgmp",
        ],
        timeout=600,
    )
    env = {
        key: os.environ[key]
        for key in ("SystemRoot", "WINDIR", "COMSPEC")
        if key in os.environ
    }
    env["PATH"] = os.pathsep.join(
        (str(bin_dir), str(Path(os.environ["SystemRoot"]) / "System32"))
    )
    env["HOME"] = env["USERPROFILE"] = str(output / "home")
    Path(env["HOME"]).mkdir()
    c_result = run([str(c_consumer)], env=env)
    cxx_result = run([str(cxx_consumer)], env=env)
    expected_product = "111111110111111111010"
    if f"product={expected_product}" not in c_result.stdout:
        raise RuntimeError("Relocated GMP C consumer returned the wrong product")
    if f"product={expected_product}" not in cxx_result.stdout:
        raise RuntimeError("Relocated GMP C++ consumer returned the wrong product")
    for output_text, label, library in (
        (c_result.stdout, "dll", "msys-gmp-10.dll"),
        (cxx_result.stdout, "gmp", "msys-gmp-10.dll"),
        (cxx_result.stdout, "gmpxx", "msys-gmpxx-4.dll"),
    ):
        loaded = re.search(rf"^{label}=(.+)$", output_text, flags=re.MULTILINE)
        if not loaded or Path(loaded.group(1)).resolve() != (bin_dir / library).resolve():
            raise RuntimeError(f"Consumer did not load relocated {library}")
    objdump = args.toolchain / "bin/objdump.exe"
    return {
        "c_compile_exit": c_compile.returncode,
        "c_consumer_exit": c_result.returncode,
        "c_consumer_stdout": c_result.stdout.strip(),
        "cxx_compile_exit": cxx_compile.returncode,
        "cxx_consumer_exit": cxx_result.returncode,
        "cxx_consumer_stdout": cxx_result.stdout.strip(),
        "machines": {
            "c_consumer": pe_machine(c_consumer),
            "cxx_consumer": pe_machine(cxx_consumer),
        },
        "sha256": {
            "c_consumer": digest(c_consumer),
            "cxx_consumer": digest(cxx_consumer),
        },
        "imports": {
            "msys-gmp-10.dll": imports(objdump, bin_dir / "msys-gmp-10.dll"),
            "msys-gmpxx-4.dll": imports(objdump, bin_dir / "msys-gmpxx-4.dll"),
            "c_consumer": imports(objdump, c_consumer),
            "cxx_consumer": imports(objdump, cxx_consumer),
        },
        "runtime_dependencies": {"msys-2.0.dll": digest(bin_dir / "msys-2.0.dll")},
        "path_scope": "relocated package bin plus Windows System32 only",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="libgpg-error")
    for name in ("build-root", "output", "bootstrap", "toolchain", "runtime", "iconv", "intl"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = PROFILES[args.profile]
    build_root = args.build_root.resolve()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("A fresh final provider output is required")
    output.mkdir(parents=True)
    (output / "packages").mkdir()
    (output / "work").mkdir()
    (output / "readback").mkdir()
    build_result_path = build_root / (
        "build-result-qualified.json" if args.profile == "gmp" else "build-result.json"
    )
    build_result = json.loads(build_result_path.read_text(encoding="utf-8"))
    if build_result.get("status") != "passed":
        raise RuntimeError("The source build/check result is not passed")
    original_packages = sorted((build_root / "packages").glob("*.pkg.tar.zst"))
    if len(original_packages) != len(profile["packages"]):
        raise RuntimeError(
            f"Expected exactly {len(profile['packages'])} {args.profile} split packages"
        )
    tar = args.bootstrap / "usr/bin/bsdtar.exe"
    sanitization = [
        sanitize_package(args.bootstrap, tar, package, output, args.profile)
        for package in original_packages
    ]
    sealed_packages = sorted((output / "packages").glob("*.pkg.tar.zst"))
    marker_values = (
        ".copilot",
        "session-state",
        "c:/users",
        "/mnt/c/users",
        "c:/ap13-dcb",
        str(args.bootstrap.resolve()).replace("\\", "/").lower(),
        str(args.toolchain.resolve()).replace("\\", "/").lower(),
        str(build_root).replace("\\", "/").lower(),
        cygpath(args.bootstrap, args.bootstrap.resolve()).lower(),
        cygpath(args.bootstrap, args.toolchain.resolve()).lower(),
        cygpath(args.bootstrap, build_root).lower(),
    )
    private_markers = [
        (marker, marker.encode("ascii"), marker.encode("utf-16le"))
        for marker in dict.fromkeys(marker_values)
        if len(marker) > 3 and marker not in ("/", "\\")
    ]
    package_records = [
        inspect_package(tar, package, output, private_markers, profile)
        for package in sealed_packages
    ]
    if args.profile == "libgpg-error":
        control = libgpg_error_relocated_control(args, sealed_packages, output)
    elif args.profile == "npth":
        control = npth_relocated_control(args, sealed_packages, output)
    elif args.profile == "gmp":
        control = gmp_relocated_control(args, sealed_packages, output)
    else:
        raise RuntimeError(f"No relocated control for profile: {args.profile}")
    evidence = {
        "schema": 1,
        "status": profile["status"],
        "source_build": {
            "build_result": str(build_result_path),
            "build_result_sha256": digest(build_result_path),
            "native_job": str(build_root / "native-job.json"),
            "native_job_sha256": digest(build_root / "native-job.json"),
            "build_log": str(build_root / "build.log"),
            "build_log_sha256": digest(build_root / "build.log"),
            "adaptation": str(build_root / "adaptation.json"),
            "adaptation_sha256": digest(build_root / "adaptation.json"),
            "upstream_tests": profile["upstream_tests"],
        },
        "container_sanitization": sanitization,
        "packages": package_records,
        "relocated_control": control,
        "ownership": {"runtime_907": "external, not packaged"},
    }
    if args.profile == "libgpg-error":
        evidence["ownership"].update(
            {
                "libiconv": "external, not packaged",
                "libintl": "external, not packaged",
            }
        )
    elif args.profile == "npth":
        evidence["ownership"]["gcc-libs"] = {
            "status": "unsupplied-unqualified-for-runtime-907-cohort",
            "declaredByPkginfo": True,
            "packagedHere": False,
            "knownD70ScopedExport": {
                "path": r"C:\ap11-native-provider-intake\gcc-libs-v1\export.json",
                "sha256": "2e7f2b7c8432344c8faa650e7a6a89903947719da75e938ed7d2802ec81a5bbc",
                "packageSha256": (
                    "a4aa671c13fe09cb4dabb2a1528dee458b4960bb3d956808d1bba9443c878b6d"
                ),
                "runtimeSha256": (
                    "d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d"
                ),
                "consumptionAllowedForThisRuntime907Provider": False,
            },
        }
    (output / "handoff.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    export = {
        "schema": 1,
        "provider": profile["provider"],
        "version": profile["version"],
        "packages": [
            {"name": record["name"], "path": str(output / record["path"]),
             "sha256": record["sha256"]}
            for record in package_records
        ],
        "proof": {
            "path": str(output / "handoff.json"),
            "sha256": digest(output / "handoff.json"),
        },
        "externalDependencies": {
            "msys2-runtime": RUNTIME_SHA256,
        },
    }
    if args.profile == "libgpg-error":
        export["externalDependencies"].update(
            {"libiconv": ICONV_SHA256, "libintl": INTL_SHA256}
        )
    elif args.profile == "npth":
        export["externalDependencies"]["gcc-libs"] = {
            "status": "unsupplied-unqualified-for-runtime-907-cohort",
            "knownD70ScopedExportSha256": (
                "2e7f2b7c8432344c8faa650e7a6a89903947719da75e938ed7d2802ec81a5bbc"
            ),
            "consumptionAllowed": False,
            "note": (
                "The exact PKGINFO dependency is retained. The DLL import set does "
                "not establish cross-runtime compatibility."
            ),
        }
    (output / "export.json").write_text(
        json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    shutil.rmtree(output / "work")
    print(json.dumps({
        "export": str(output / "export.json"),
        "export_sha256": digest(output / "export.json"),
        "handoff": str(output / "handoff.json"),
        "handoff_sha256": digest(output / "handoff.json"),
        "packages": export["packages"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
