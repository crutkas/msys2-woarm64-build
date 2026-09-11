"""Package and verify the marker-clean native MSYS libxcrypt successor."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from typing import Any


RUNTIME_SHA256 = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
OPENSSH_PACKAGE_SHA256 = "8579eb15dd2048a6a728a6d2d41f1a267a7d4c972a1dd5b2b50660036900b432"
OPENSSH_SHA256 = "9a6eb24cc5667ceadbe73877c97e075587ccec2c34b26fa862e5f7b1ca37d051"
OLD_LIBXCRYPT_SHA256 = "ce687271a36f2281ee65991b6cb18efbc3eb3bb45b4f9169a31d3d7d23d45dbe"
OLD_PACKAGE_SHA256 = "47bf08ac989f20e0574a1728f511327bf1cb8b17d9fb628953e7138b6c033f65"
OLD_DEVEL_PACKAGE_SHA256 = "eb8c494af45079cc6e06c54d254132170cb7ffdddef521aac177da33b7e1d37f"
ADMITTED_SIX_EXPORT_SHA256 = "d7898516a5562d195097c65ac24e500e8fafd662fe898bc3e9873dc9795078d1"
REJECTION_SCAN_SHA256 = "ded247b910e80fbc1d220419a8a8f50f4914eb15f16752f25f810b590b5cae5f"
REJECTION_VERDICT_SHA256 = "b8926e215949688f48c7b418636dfec715eda9733ea52309cde2fd514ae33b60"
SOURCE_MANIFEST_SHA256 = "52c89e7429bbaf2425ae9d58ce95b3a67be6ec7b36cd54dcb45d26db9b68d51d"
SOURCE_ARCHIVE_SHA256 = "71513a31c01a428bccd5367a32fd95f115d6dac50fb5b60c779d5c7942aec071"
SOURCE_SIGNATURE_SHA256 = "11df2b889929d4923eed6298ba44c6e746c9ca5b9de41bd9b1b1a694a2aea65e"
SOURCE_KEY_SHA256 = "d52010dc79210e9b00c114b25afdf57823343952c3a334266d8681cf18de3da2"
SOURCE_RECIPE_SHA256 = "bc4971d32ad680d097d3d3248def2f3454331de428829325d41afb342de28436"
SOURCE_FINGERPRINT = "678CE3FEE430311596DB8C16F52E98007594C21D"
SOURCE_RECIPE_COMMIT = "5b84e2f8c4ea1783e03d6a43b32b94c2692291a6"
SOURCE_RECIPE_BLOB = "fbe0e4c6652b11cb33cc39517617df5cd17cbc23"
PREFIX_PATCH_SHA256 = "88134c56a7620bf1effb15a08e7df675c853bc65ee2d1874485b7b860c605957"
ORIGINAL_DRIVER_SHA256 = "3ce04eb751b4d909ba103d6d86ecdfd6da6d961f2c5e21b334bd99b644fdf929"
MODIFIED_DRIVER_SHA256 = "bbf7057a372547531cfb0f0f956e6d437ddf7bb2cc8b2e7ad143a678c6ef686a"

PRIVATE_MARKERS = (
    b".copilot",
    b"session-state",
    b"c:/users",
    b"c:\\users",
    b"/mnt/c/users",
    b"c:/ag-e138920f",
    b"c:\\ag-e138920f",
    b"/c/ag-e138920f",
    b"c:/ap13-dcb",
    b"c:\\ap13-dcb",
    b"/c/ap13-dcb",
)
CANONICAL_SOURCE = b"/usr/src/debug/libxcrypt-4.5.2"
TOOLCHAIN_PROVENANCE = b"/root/arm64-vnext"
RUNTIME_VISIBLE_SECTIONS = {
    ".text",
    ".data",
    ".rdata",
    ".pdata",
    ".xdata",
    ".bss",
    ".edata",
    ".idata",
    ".reloc",
}

LIBXCRYPT_PKGBUILD = r"""pkgbase=libxcrypt
pkgname=('libxcrypt' 'libxcrypt-devel')
pkgver=4.5.2
pkgrel=3
pkgdesc='Modern library for one-way hashing of passwords'
arch=('aarch64')
url='https://github.com/besser82/libxcrypt/'
license=('spdx:LGPL-2.1-or-later')
options=('!strip' '!debug' '!lto' '!ccache' '!purge' '!zipman' 'staticlibs' 'libtool')
source=()

package_libxcrypt() {
  depends=('msys2-runtime')
  install -dm755 "$pkgdir/usr/bin"
  cp -f "$startdir/payload/usr/bin/"*.dll "$pkgdir/usr/bin/"
}

package_libxcrypt-devel() {
  depends=("libxcrypt=${pkgver}")
  conflicts=('libcrypt-devel')
  provides=('libcrypt-devel')
  replaces=('libcrypt-devel')
  install -dm755 "$pkgdir/usr"
  cp -a "$startdir/payload/usr/include" "$startdir/payload/usr/lib" \
    "$startdir/payload/usr/share" "$pkgdir/usr/"
}
"""

CONSUMER_SOURCE = r"""#include <crypt.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <windows.h>

static int exercise(const char *prefix, unsigned long count)
{
    static const char random_bytes[] = "0123456789abcdef";
    char setting[CRYPT_GENSALT_OUTPUT_SIZE];
    char first[CRYPT_OUTPUT_SIZE];
    struct crypt_data data = {0};
    char *hash;

    if (!crypt_gensalt_rn(prefix, count, random_bytes, sizeof(random_bytes) - 1,
                          setting, sizeof(setting))) {
        return 10;
    }
    if (crypt_checksalt(setting) == CRYPT_SALT_INVALID) {
        return 11;
    }
    hash = crypt_r("native-msys-libxcrypt", setting, &data);
    if (!hash || strlen(hash) >= sizeof(first)) {
        return 12;
    }
    strcpy(first, hash);
    memset(&data, 0, sizeof(data));
    hash = crypt_r("native-msys-libxcrypt", first, &data);
    if (!hash || strcmp(hash, first) != 0) {
        return 13;
    }
    return 0;
}

int main(void)
{
    wchar_t module_path[32768];
    HMODULE module;
    const char *preferred = crypt_preferred_method();
    int status;

    if (!preferred || (status = exercise(preferred, 0)) != 0) {
        return status ? status : 20;
    }
    if ((status = exercise("$6$", 5000)) != 0) {
        return status;
    }
    module = GetModuleHandleW(L"msys-crypt-2.dll");
    if (!module || !GetModuleFileNameW(module, module_path, 32768)) {
        return 21;
    }
    wprintf(L"preferred=%hs\nloaded=%ls\n", preferred, module_path);
    return 0;
}
"""


def load_cohort_module() -> Any:
    path = Path(__file__).with_name("package-native-msys-crypto-cohort.py")
    spec = importlib.util.spec_from_file_location("native_msys_crypto_cohort", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_sha256(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {path}: expected {expected}, observed {actual}")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def copy_proof(source: Path, target: Path, root: Path) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "path": target.relative_to(root).as_posix(),
        "sha256": sha256(target),
    }


def resolve_section_name(
    encoded: bytes,
    data: bytes,
    symbol_table_offset: int,
    symbol_count: int,
) -> str:
    text = encoded.rstrip(b"\0").decode("ascii", errors="replace")
    if not text.startswith("/") or not text[1:].isdigit() or not symbol_table_offset:
        return text
    string_table = symbol_table_offset + symbol_count * 18
    offset = string_table + int(text[1:])
    end = data.find(b"\0", offset)
    if end < 0:
        end = len(data)
    return data[offset:end].decode("ascii", errors="replace")


def pe_sections(path: Path) -> list[dict[str, int | str]]:
    data = path.read_bytes()
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise RuntimeError(f"not a PE image: {path}")
    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    symbol_table_offset = struct.unpack_from("<I", data, pe_offset + 12)[0]
    symbol_count = struct.unpack_from("<I", data, pe_offset + 16)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    table = pe_offset + 24 + optional_size
    sections = []
    for index in range(section_count):
        offset = table + index * 40
        encoded = data[offset:offset + 8]
        name = resolve_section_name(encoded, data, symbol_table_offset, symbol_count)
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", data, offset + 8)
        characteristics = struct.unpack_from("<I", data, offset + 36)[0]
        sections.append(
            {
                "name": name,
                "encoded_name": encoded.rstrip(b"\0").decode("ascii", errors="replace"),
                "virtual_size": virtual_size,
                "rva": rva,
                "raw_size": raw_size,
                "raw_offset": raw_offset,
                "characteristics": characteristics,
            }
        )
    return sections


def marker_scan(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    sections = pe_sections(path)

    def section_for(offset: int) -> dict[str, int | str] | None:
        for section in sections:
            start = int(section["raw_offset"])
            end = start + int(section["raw_size"])
            if start <= offset < end:
                return section
        return None

    def occurrences(marker: bytes) -> list[dict[str, object]]:
        records = []
        lower = data.lower()
        start = 0
        while True:
            offset = lower.find(marker.lower(), start)
            if offset < 0:
                break
            section = section_for(offset)
            value_start = offset
            while value_start > 0 and 0x20 <= data[value_start - 1] <= 0x7E:
                value_start -= 1
            value_end = offset + len(marker)
            while value_end < len(data) and 0x20 <= data[value_end] <= 0x7E:
                value_end += 1
            record: dict[str, object] = {
                "file_offset": f"0x{offset:08x}",
                "value": data[value_start:value_end].decode("ascii", errors="replace"),
                "section": section["name"] if section else None,
            }
            if section:
                record.update(
                    {
                        "encoded_section_name": section["encoded_name"],
                        "section_characteristics": f"0x{int(section['characteristics']):08x}",
                        "rva": f"0x{int(section['rva']) + offset - int(section['raw_offset']):08x}",
                    }
                )
            records.append(record)
            start = offset + len(marker)
        return records

    private = []
    for marker in PRIVATE_MARKERS:
        for record in occurrences(marker):
            record["marker"] = marker.decode("ascii")
            private.append(record)
        utf16 = marker.decode("ascii").encode("utf-16le")
        lower_utf16 = data.lower()
        start = 0
        while True:
            offset = lower_utf16.find(utf16.lower(), start)
            if offset < 0:
                break
            section = section_for(offset)
            private.append(
                {
                    "marker": marker.decode("ascii"),
                    "encoding": "utf-16le",
                    "file_offset": f"0x{offset:08x}",
                    "section": section["name"] if section else None,
                }
            )
            start = offset + len(utf16)
    canonical = occurrences(CANONICAL_SOURCE)
    toolchain = occurrences(TOOLCHAIN_PROVENANCE)
    toolchain_runtime = [
        record for record in toolchain if record.get("section") in RUNTIME_VISIBLE_SECTIONS
    ]
    if private:
        raise RuntimeError(f"private producer markers remain in {path}: {private[:5]}")
    if not canonical:
        raise RuntimeError("canonical libxcrypt source mapping is absent from the rebuilt DLL")
    if sum(record.get("section") == ".rdata" for record in canonical) < 6:
        raise RuntimeError("the six runtime-visible source strings were not mapped into the canonical source root")
    if toolchain_runtime:
        raise RuntimeError(f"toolchain provenance leaked into runtime-visible PE sections: {toolchain_runtime}")
    return {
        "schema": 1,
        "file": str(path),
        "file_sha256": sha256(path),
        "machine": "0xAA64",
        "private_marker_occurrences": private,
        "private_marker_count": len(private),
        "canonical_source": CANONICAL_SOURCE.decode("ascii"),
        "canonical_source_occurrences": canonical,
        "canonical_source_counts_by_section": dict(
            sorted(Counter(str(row["section"]) for row in canonical).items())
        ),
        "toolchain_provenance_marker": TOOLCHAIN_PROVENANCE.decode("ascii"),
        "toolchain_provenance_counts_by_section": dict(
            sorted(Counter(str(row["section"]) for row in toolchain).items())
        ),
        "toolchain_provenance_runtime_visible_occurrences": toolchain_runtime,
        "limitations": [
            "The retained /root/arm64-vnext strings are confined to debug sections from the sealed compiler/runtime cohort.",
            "Static development archives are disclosed separately and are not claimed to contain zero debug provenance strings.",
        ],
    }


def symbol_names(nm: Path, image: Path) -> list[str]:
    result = subprocess.run(
        [str(nm), "-g", "--defined-only", str(image)],
        capture_output=True,
        text=True,
        check=True,
    )
    names = set()
    for line in result.stdout.splitlines():
        match = re.match(r"^\S+\s+\S\s+(.+)$", line)
        if match:
            names.add(match.group(1))
    return sorted(names)


def imported_dlls(objdump: Path, image: Path) -> list[str]:
    result = subprocess.run(
        [str(objdump), "-p", str(image)],
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(set(re.findall(r"^\s*DLL Name:\s*(\S+)", result.stdout, re.MULTILINE)))


def abi_comparison(
    nm: Path,
    objdump: Path,
    old_stage: Path,
    new_stage: Path,
) -> dict[str, object]:
    old_dll = old_stage / "usr/bin/msys-crypt-2.dll"
    new_dll = new_stage / "usr/bin/msys-crypt-2.dll"
    old_symbols = symbol_names(nm, old_dll)
    new_symbols = symbol_names(nm, new_dll)
    old_imports = imported_dlls(objdump, old_dll)
    new_imports = imported_dlls(objdump, new_dll)
    exact_files = (
        "usr/include/crypt.h",
        "usr/lib/libcrypt.la",
        "usr/lib/pkgconfig/libcrypt.pc",
        "usr/lib/pkgconfig/libxcrypt.pc",
        "usr/share/licenses/libxcrypt/COPYING.LIB",
        "usr/share/licenses/libxcrypt/LICENSING",
    )
    exact_records = []
    for relative in exact_files:
        old = old_stage / relative
        new = new_stage / relative
        exact_records.append(
            {
                "path": relative,
                "old_sha256": sha256(old),
                "new_sha256": sha256(new),
                "identical": sha256(old) == sha256(new),
            }
        )
    if old_symbols != new_symbols:
        raise RuntimeError("libxcrypt public/global symbol names changed")
    if old_imports != new_imports:
        raise RuntimeError("libxcrypt imported DLL closure changed")
    if not all(record["identical"] for record in exact_records):
        raise RuntimeError("libxcrypt public header/config/license surface changed")
    old_config = old_stage.parent / "build/config.h"
    new_config = new_stage.parent / "build/config.h"
    if sha256(old_config) != sha256(new_config):
        raise RuntimeError("libxcrypt configured feature surface changed")
    return {
        "schema": 1,
        "passed": True,
        "old_dll": {"sha256": sha256(old_dll), "size": old_dll.stat().st_size},
        "new_dll": {"sha256": sha256(new_dll), "size": new_dll.stat().st_size},
        "global_defined_symbols": {
            "old_count": len(old_symbols),
            "new_count": len(new_symbols),
            "identical_names": True,
            "sha256": hashlib.sha256(("\n".join(new_symbols) + "\n").encode()).hexdigest(),
        },
        "imported_dlls": {"old": old_imports, "new": new_imports, "identical": True},
        "exact_unchanged_files": exact_records,
        "configuration": {
            "old_config_h_sha256": sha256(old_config),
            "new_config_h_sha256": sha256(new_config),
            "identical": True,
        },
        "changed_build_artifacts": {
            "reason": "compile-origin file/debug/macro prefix mapping only",
            "static_archive_sha256": sha256(new_stage / "usr/lib/libcrypt.a"),
            "import_library_sha256": sha256(new_stage / "usr/lib/libcrypt.dll.a"),
        },
    }


def verify_source(
    cohort: Any,
    bootstrap: Path,
    source_inputs: Path,
    evidence: Path,
    logs: Path,
) -> dict[str, object]:
    target = evidence / "source-inputs"
    target.mkdir()
    names = (
        "libxcrypt-4.5.2.tar.xz",
        "libxcrypt-4.5.2.tar.xz.asc",
        f"libxcrypt-{SOURCE_FINGERPRINT}.asc",
        "libxcrypt-PKGBUILD",
    )
    for name in names:
        shutil.copy2(source_inputs / name, target / name)
    require_sha256(target / names[0], SOURCE_ARCHIVE_SHA256)
    require_sha256(target / names[1], SOURCE_SIGNATURE_SHA256)
    require_sha256(target / names[2], SOURCE_KEY_SHA256)
    require_sha256(target / names[3], SOURCE_RECIPE_SHA256)
    gpg_home = evidence / "gnupg"
    gpg_home.mkdir()
    gpg = bootstrap / "usr/bin/gpg.exe"
    home = cohort.cygpath(bootstrap, gpg_home)
    env = os.environ.copy()
    env.pop("GNUPGHOME", None)
    imported = cohort.run(
        [
            str(gpg),
            "--batch",
            "--homedir",
            home,
            "--import",
            cohort.cygpath(bootstrap, target / names[2]),
        ],
        env=env,
        log=logs / "gpg-import-libxcrypt.log",
    )
    verified = cohort.run(
        [
            str(gpg),
            "--batch",
            "--homedir",
            home,
            "--status-fd",
            "1",
            "--verify",
            cohort.cygpath(bootstrap, target / names[1]),
            cohort.cygpath(bootstrap, target / names[0]),
        ],
        env=env,
        log=logs / "gpg-verify-libxcrypt.log",
    )
    valid = re.findall(r"^\[GNUPG:\] VALIDSIG (.+)$", verified.stdout, re.MULTILINE)
    if SOURCE_FINGERPRINT not in {token for line in valid for token in line.split()}:
        raise RuntimeError("libxcrypt source signature did not bind the expected fingerprint")
    return {
        "name": "libxcrypt",
        "version": "4.5.2",
        "archive": {
            "path": f"evidence/source-inputs/{names[0]}",
            "sha256": SOURCE_ARCHIVE_SHA256,
            "url": "https://github.com/besser82/libxcrypt/releases/download/v4.5.2/libxcrypt-4.5.2.tar.xz",
        },
        "signature": {
            "path": f"evidence/source-inputs/{names[1]}",
            "sha256": SOURCE_SIGNATURE_SHA256,
            "valid_signer_fingerprint": SOURCE_FINGERPRINT,
        },
        "public_key": {
            "path": f"evidence/source-inputs/{names[2]}",
            "sha256": SOURCE_KEY_SHA256,
        },
        "msys2_recipe": {
            "path": f"evidence/source-inputs/{names[3]}",
            "sha256": SOURCE_RECIPE_SHA256,
            "commit": SOURCE_RECIPE_COMMIT,
            "git_blob": SOURCE_RECIPE_BLOB,
        },
        "gpg_import_output": imported.stderr.strip(),
    }


def read_existing_source_verification(
    source_inputs: Path,
    logs: Path,
) -> dict[str, object]:
    names = (
        "libxcrypt-4.5.2.tar.xz",
        "libxcrypt-4.5.2.tar.xz.asc",
        f"libxcrypt-{SOURCE_FINGERPRINT}.asc",
        "libxcrypt-PKGBUILD",
    )
    require_sha256(source_inputs / names[0], SOURCE_ARCHIVE_SHA256)
    require_sha256(source_inputs / names[1], SOURCE_SIGNATURE_SHA256)
    require_sha256(source_inputs / names[2], SOURCE_KEY_SHA256)
    require_sha256(source_inputs / names[3], SOURCE_RECIPE_SHA256)
    verify_log = logs / "gpg-verify-libxcrypt.log"
    verify_text = verify_log.read_text(encoding="utf-8")
    if "VALIDSIG " + SOURCE_FINGERPRINT not in verify_text:
        raise RuntimeError("existing libxcrypt GPG verification log is incomplete")
    return {
        "name": "libxcrypt",
        "version": "4.5.2",
        "archive": {
            "path": f"evidence/source-inputs/{names[0]}",
            "sha256": SOURCE_ARCHIVE_SHA256,
            "url": "https://github.com/besser82/libxcrypt/releases/download/v4.5.2/libxcrypt-4.5.2.tar.xz",
        },
        "signature": {
            "path": f"evidence/source-inputs/{names[1]}",
            "sha256": SOURCE_SIGNATURE_SHA256,
            "valid_signer_fingerprint": SOURCE_FINGERPRINT,
        },
        "public_key": {
            "path": f"evidence/source-inputs/{names[2]}",
            "sha256": SOURCE_KEY_SHA256,
        },
        "msys2_recipe": {
            "path": f"evidence/source-inputs/{names[3]}",
            "sha256": SOURCE_RECIPE_SHA256,
            "commit": SOURCE_RECIPE_COMMIT,
            "git_blob": SOURCE_RECIPE_BLOB,
        },
        "gpg_verification_log": {
            "path": "logs/gpg-verify-libxcrypt.log",
            "sha256": sha256(verify_log),
        },
    }


def parse_pkginfo(text: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in text.splitlines():
        if " = " in line and not line.startswith("#"):
            key, value = line.split(" = ", 1)
            values.setdefault(key, []).append(value)
    return values


def require_package_metadata(records: list[dict[str, object]], root: Path) -> None:
    by_name = {str(record["name"]): record for record in records}
    if set(by_name) != {"libxcrypt", "libxcrypt-devel"}:
        raise RuntimeError(f"unexpected package set: {sorted(by_name)}")
    expected = {
        "libxcrypt": {
            "pkgver": ["4.5.2-3"],
            "arch": ["aarch64"],
            "license": ["spdx:LGPL-2.1-or-later"],
            "depend": ["msys2-runtime"],
        },
        "libxcrypt-devel": {
            "pkgver": ["4.5.2-3"],
            "arch": ["aarch64"],
            "license": ["spdx:LGPL-2.1-or-later"],
            "depend": ["libxcrypt=4.5.2"],
            "replaces": ["libcrypt-devel"],
            "conflict": ["libcrypt-devel"],
            "provides": ["libcrypt-devel"],
        },
    }
    for name, fields in expected.items():
        record = by_name[name]
        info = parse_pkginfo((root / str(record["pkginfo"])).read_text(encoding="utf-8"))
        for key, value in fields.items():
            if info.get(key) != value:
                raise RuntimeError(f"unexpected {name} {key}: {info.get(key)}")


def static_archive_disclosure(stage: Path) -> dict[str, object]:
    records = []
    for relative in ("usr/lib/libcrypt.a", "usr/lib/libcrypt.dll.a"):
        path = stage / relative
        lowered = path.read_bytes().lower()
        records.append(
            {
                "path": relative,
                "sha256": sha256(path),
                "private_marker_counts": {
                    marker.decode("ascii"): lowered.count(marker)
                    for marker in PRIVATE_MARKERS
                    if lowered.count(marker)
                },
                "canonical_source_count": lowered.count(CANONICAL_SOURCE),
                "toolchain_provenance_count": lowered.count(TOOLCHAIN_PROVENANCE),
                "shipping_role": "development-link input; not runtime-loaded executable data",
            }
        )
    return {
        "schema": 1,
        "zero_strings_claim": False,
        "records": records,
    }


def run_direct_consumer(
    cohort: Any,
    compiler: Path,
    objdump: Path,
    stage: Path,
    relocated: Path,
    output: Path,
    new_dll_sha256: str,
) -> dict[str, object]:
    source = output / "libxcrypt-consumer.c"
    executable = output / "libxcrypt-consumer.exe"
    stdout = output / "libxcrypt-consumer.stdout"
    stderr = output / "libxcrypt-consumer.stderr"
    source.write_text(CONSUMER_SOURCE, encoding="ascii")
    compile_result = cohort.run(
        [
            str(compiler),
            "-O2",
            "-g0",
            "-Werror",
            "-o",
            str(executable),
            str(source),
            f"-I{stage / 'usr/include'}",
            str(stage / "usr/lib/libcrypt.dll.a"),
            "-Wl,--no-insert-timestamp",
        ],
        log=output / "libxcrypt-consumer-build.log",
    )
    del compile_result
    if cohort.pe_machine(executable) != "0xAA64":
        raise RuntimeError("direct libxcrypt consumer is not AA64")
    imports = imported_dlls(objdump, executable)
    if "msys-crypt-2.dll" not in imports:
        raise RuntimeError("direct consumer did not dynamically import msys-crypt-2.dll")
    env = {
        name: os.environ[name]
        for name in ("SystemRoot", "WINDIR", "COMSPEC", "USERNAME", "USERDOMAIN")
        if name in os.environ
    }
    env["PATH"] = str(relocated / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["HOME"] = env["USERPROFILE"] = str(output / "consumer-home")
    Path(env["HOME"]).mkdir()
    result = subprocess.run(
        [str(executable)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    stdout.write_text(result.stdout, encoding="utf-8")
    stderr.write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"direct libxcrypt consumer failed: {result.returncode}: {result.stderr}")
    loaded_line = next(
        (line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("loaded=")),
        None,
    )
    if loaded_line is None:
        raise RuntimeError("direct consumer did not report its loaded libxcrypt module")
    loaded = Path(loaded_line).resolve()
    expected = (relocated / "usr/bin/msys-crypt-2.dll").resolve()
    if os.path.normcase(str(loaded)) != os.path.normcase(str(expected)):
        raise RuntimeError(f"direct consumer loaded unexpected libxcrypt: {loaded}")
    require_sha256(loaded, new_dll_sha256)
    return {
        "schema": 1,
        "passed": True,
        "executable": {
            "path": executable.name,
            "sha256": sha256(executable),
            "machine": "0xAA64",
            "imports": imports,
        },
        "algorithms": ["preferred-method", "sha512crypt"],
        "loaded_module": {"path": str(loaded), "sha256": sha256(loaded)},
        "exit": result.returncode,
        "stdout_sha256": sha256(stdout),
        "stderr_sha256": sha256(stderr),
    }


def read_existing_relocation(
    cohort: Any,
    output: Path,
    new_dll_sha256: str,
) -> dict[str, object]:
    relocated = output / "relocated-root"
    required = {
        relocated / "usr/bin/msys-2.0.dll": RUNTIME_SHA256,
        relocated / "usr/bin/msys-crypto-3.dll": cohort.OPENSSL_CRYPTO_SHA256,
        relocated / "usr/bin/msys-ssl-3.dll": cohort.OPENSSL_SSL_SHA256,
        relocated / "usr/bin/msys-z.dll": cohort.ZLIB_SHA256,
        relocated / "usr/bin/msys-crypt-2.dll": new_dll_sha256,
        relocated / "usr/bin/ssh.exe": OPENSSH_SHA256,
    }
    for path, expected in required.items():
        require_sha256(path, expected)
        if cohort.pe_machine(path) != "0xAA64":
            raise RuntimeError(f"existing relocated image is not AA64: {path}")
    log_expectations = {
        "version": ("openssl-version.log", "OpenSSL 3.6.4"),
        "configdir": ("openssl-configdir.log", "/usr/ssl"),
        "enginesdir": ("openssl-enginesdir.log", "/usr/lib/openssl/engines-3"),
        "modulesdir": ("openssl-modulesdir.log", "/usr/lib/ossl-modules"),
        "legacy_provider": ("openssl-legacy_provider.log", "legacy"),
        "dasync_engine": ("openssl-dasync_engine.log", "dasync"),
        "default_config_request": ("openssl-default-config-request.log", "req"),
    }
    openssl = {}
    for name, (filename, expected) in log_expectations.items():
        path = output / filename
        text = path.read_text(encoding="utf-8")
        if expected.lower() not in text.lower():
            raise RuntimeError(f"existing relocated OpenSSL control is incomplete: {name}")
        openssl[name] = {
            "log": filename,
            "sha256": sha256(path),
            "expected_observed": expected,
        }
    handshake = output / "controlled-ssh/result.json"
    handshake_result = json.loads(handshake.read_text(encoding="utf-8"))
    exits = [case.get("raw_exit") for case in handshake_result.get("cases", [])]
    if not handshake_result.get("passed") or exits != [0, 255]:
        raise RuntimeError("existing OpenSSH relocation control is incomplete")
    csr = output / "relocation.csr"
    key = output / "relocation.key"
    return {
        "schema": 1,
        "passed": True,
        "continued_from_completed_pre_consumer_controls": True,
        "relocated_root": str(relocated),
        "runtime_test_only": {
            "path": str(relocated / "usr/bin/msys-2.0.dll"),
            "sha256": RUNTIME_SHA256,
            "packaged": False,
        },
        "required_images": [
            {
                "path": path.relative_to(relocated).as_posix(),
                "sha256": sha256(path),
                "machine": cohort.pe_machine(path),
            }
            for path in required
        ],
        "openssl": openssl,
        "default_config_artifacts": {
            "csr_sha256": sha256(csr),
            "key_sha256": sha256(key),
        },
        "controlled_ssh": {
            "result": "controlled-ssh/result.json",
            "sha256": sha256(handshake),
            "passed": True,
            "positive_exit": 0,
            "wrong_host_exit": 255,
        },
        "real_credentials_or_global_settings_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--libxcrypt-stage", type=Path, required=True)
    parser.add_argument("--old-libxcrypt-stage", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--openssh-package", type=Path, required=True)
    parser.add_argument("--admitted-six-root", type=Path, required=True)
    parser.add_argument("--admitted-six-export", type=Path, required=True)
    parser.add_argument("--native-python", type=Path, required=True)
    parser.add_argument("--fixture-script", type=Path, required=True)
    parser.add_argument("--fixture-driver", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    parser.add_argument("--tar", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--nm", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--source-inputs", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--native-job", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--launch-inputs", type=Path, required=True)
    parser.add_argument("--prefix-patch", type=Path, required=True)
    parser.add_argument("--original-driver", type=Path, required=True)
    parser.add_argument("--modified-driver", type=Path, required=True)
    parser.add_argument("--rejection-scan", type=Path, required=True)
    parser.add_argument("--rejection-verdict", type=Path, required=True)
    parser.add_argument("--prior-export", type=Path, required=True)
    parser.add_argument("--prior-handoff", type=Path, required=True)
    parser.add_argument("--resume-existing", action="store_true")
    args = parser.parse_args()

    cohort = load_cohort_module()
    output = args.output.resolve()
    if output.exists() and not args.resume_existing:
        raise SystemExit(f"refusing existing output root: {output}")
    if not output.exists():
        output.mkdir(parents=True)
    work = output / "work"
    logs = output / "logs"
    evidence = output / "evidence"
    package_build = output / "package-build"
    if args.resume_existing:
        for path in (work, logs, evidence, package_build):
            if not path.is_dir():
                raise RuntimeError(f"incomplete resume root: {path}")
    else:
        for path in (work, logs, evidence, package_build):
            path.mkdir()

    require_sha256(args.runtime, RUNTIME_SHA256)
    require_sha256(args.openssh_package, OPENSSH_PACKAGE_SHA256)
    require_sha256(args.admitted_six_export, ADMITTED_SIX_EXPORT_SHA256)
    require_sha256(args.source_manifest, SOURCE_MANIFEST_SHA256)
    require_sha256(args.prefix_patch, PREFIX_PATCH_SHA256)
    require_sha256(args.original_driver, ORIGINAL_DRIVER_SHA256)
    require_sha256(args.modified_driver, MODIFIED_DRIVER_SHA256)
    require_sha256(args.rejection_scan, REJECTION_SCAN_SHA256)
    require_sha256(args.rejection_verdict, REJECTION_VERDICT_SHA256)

    new_dll = args.libxcrypt_stage / "usr/bin/msys-crypt-2.dll"
    old_dll = args.old_libxcrypt_stage / "usr/bin/msys-crypt-2.dll"
    require_sha256(old_dll, OLD_LIBXCRYPT_SHA256)
    new_dll_sha256 = sha256(new_dll)
    if new_dll_sha256 == OLD_LIBXCRYPT_SHA256:
        raise RuntimeError("the successor did not replace the rejected libxcrypt bytes")
    if cohort.pe_machine(new_dll) != "0xAA64":
        raise RuntimeError("replacement libxcrypt DLL is not AA64")

    build_receipt = json.loads(args.build_receipt.read_text(encoding="utf-8"))
    tests = build_receipt.get("upstream_tests", {}).get("counts", {})
    if tests != {
        "TOTAL": 54,
        "PASS": 53,
        "SKIP": 1,
        "XFAIL": 0,
        "FAIL": 0,
        "XPASS": 0,
        "ERROR": 0,
    }:
        raise RuntimeError(f"unexpected upstream test result: {tests}")
    process = build_receipt.get("process", {})
    if not process.get("passed") or process.get("created_processes") != process.get("observed_processes"):
        raise RuntimeError("native libxcrypt process observation is incomplete")
    if build_receipt.get("driver_sha256") != MODIFIED_DRIVER_SHA256:
        raise RuntimeError("build receipt does not bind the prefix-mapped driver")

    final_packages = output / "packages"
    if args.resume_existing:
        source_verification = read_existing_source_verification(
            evidence / "source-inputs",
            logs,
        )
        scan = json.loads(
            (output / "libxcrypt-private-path-scan.json").read_text(encoding="utf-8")
        )
        abi = json.loads((output / "abi-comparison.json").read_text(encoding="utf-8"))
        static_disclosure = json.loads(
            (output / "static-archive-provenance.json").read_text(encoding="utf-8")
        )
        del static_disclosure
        packages = sorted(final_packages.glob("*.pkg.tar.zst"))
        package_records = json.loads(
            (output / "package-readback.json").read_text(encoding="utf-8")
        )["packages"]
        require_package_metadata(package_records, output)
    else:
        source_verification = verify_source(
            cohort,
            args.bootstrap,
            args.source_inputs,
            evidence,
            logs,
        )
        scan = marker_scan(new_dll)
        write_json(output / "libxcrypt-private-path-scan.json", scan)
        abi = abi_comparison(args.nm, args.objdump, args.old_libxcrypt_stage, args.libxcrypt_stage)
        write_json(output / "abi-comparison.json", abi)
        static_disclosure = static_archive_disclosure(args.libxcrypt_stage)
        write_json(output / "static-archive-provenance.json", static_disclosure)

        built = cohort.make_package(
            args.bootstrap,
            package_build,
            "libxcrypt",
            LIBXCRYPT_PKGBUILD,
            {"payload": args.libxcrypt_stage},
            logs,
        )
        if len(built) != 2:
            raise RuntimeError(f"expected two libxcrypt split packages, observed {len(built)}")
        built = cohort.sanitize_package_metadata(args.bootstrap, args.tar, built, work, logs)
        final_packages.mkdir()
        packages = []
        for package in built:
            target = final_packages / package.name
            shutil.copy2(package, target)
            packages.append(target)
        package_records = cohort.inspect_packages(args.tar, packages, output)
        require_package_metadata(package_records, output)
        write_json(output / "package-readback.json", {"schema": 1, "packages": package_records})
    package_map = {str(record["name"]): record for record in package_records}
    runtime_files = {
        str(row["path"]): row for row in package_map["libxcrypt"]["files"]
    }
    if runtime_files.get("usr/bin/msys-crypt-2.dll", {}).get("sha256") != new_dll_sha256:
        raise RuntimeError("runtime package did not preserve the rebuilt DLL bytes")
    admitted_six = sorted(
        package
        for package in args.admitted_six_root.glob("*.pkg.tar.zst")
        if not package.name.startswith(("libxcrypt-", "libxcrypt-devel-"))
    )
    if len(admitted_six) != 6:
        raise RuntimeError(f"expected six admitted OpenSSL/zlib packages, observed {len(admitted_six)}")
    if args.resume_existing:
        relocation = read_existing_relocation(cohort, output, new_dll_sha256)
    else:
        cohort.LIBXCRYPT_SHA256 = new_dll_sha256
        relocation = cohort.relocated_controls(
            args.tar,
            [*admitted_six, *packages],
            args.openssh_package,
            args.runtime,
            args.native_python,
            args.fixture_script,
            args.fixture_driver,
            args.pwsh,
            output,
        )
    direct = run_direct_consumer(
        cohort,
        args.compiler,
        args.objdump,
        args.libxcrypt_stage,
        Path(str(relocation["relocated_root"])),
        output,
        new_dll_sha256,
    )
    relocation["libxcrypt_direct_consumer"] = direct
    write_json(output / "relocation-result.json", relocation)

    proof_inputs = {
        "libxcrypt/source-prepare.json": args.source_manifest,
        "libxcrypt/build-receipt.json": args.build_receipt,
        "libxcrypt/native-job.json": args.native_job,
        "libxcrypt/build.log": args.build_log,
        "libxcrypt/launch-inputs.json": args.launch_inputs,
        "libxcrypt/prefix-map.patch": args.prefix_patch,
        "libxcrypt/original-build-driver.sh": args.original_driver,
        "libxcrypt/prefix-mapped-build-driver.sh": args.modified_driver,
        "intake/rejected-private-path-scan.json": args.rejection_scan,
        "intake/rejection-verdict.json": args.rejection_verdict,
        "intake/admitted-openssl-zlib-export.json": args.admitted_six_export,
        "prior-cohort/export.json": args.prior_export,
        "prior-cohort/handoff.json": args.prior_handoff,
        "packaging/successor-packager.py": Path(__file__).resolve(),
    }
    proof_references = []
    for relative, source in proof_inputs.items():
        record = copy_proof(source, evidence / relative, output)
        record["name"] = relative
        proof_references.append(record)
    sanitization = copy_proof(
        work / "package-container-sanitization.json",
        evidence / "packaging/package-container-sanitization.json",
        output,
    )
    sanitization["name"] = "packaging/package-container-sanitization.json"
    proof_references.append(sanitization)

    package_exports = [
        {
            "name": str(record["name"]),
            "path": str(record["path"]),
            "sha256": str(record["sha256"]),
        }
        for record in sorted(package_records, key=lambda row: str(row["name"]))
    ]
    admitted_dependency_packages = [
        {"path": str(path), "sha256": sha256(path), "exported": False}
        for path in admitted_six
    ]
    handoff = {
        "schema": 1,
        "status": "sealed-native-msys-libxcrypt-successor-pending-independent-intake",
        "scope": (
            "Source-origin prefix-mapped native ARM64 MSYS libxcrypt 4.5.2 "
            "runtime/development successor packages only."
        ),
        "packages": package_exports,
        "supersedes": [
            {"name": "libxcrypt", "sha256": OLD_PACKAGE_SHA256},
            {"name": "libxcrypt-devel", "sha256": OLD_DEVEL_PACKAGE_SHA256},
        ],
        "pkgrel": {
            "value": 3,
            "reason": (
                "New binary identity after source-origin path remediation; pkgrel 2 remains "
                "reserved by the separately revoked header package and is not reactivated."
            ),
        },
        "dependency_bindings": {
            "msys-crypt-2.dll": new_dll_sha256,
            "msys2-runtime": RUNTIME_SHA256,
            "openssh-package": OPENSSH_PACKAGE_SHA256,
            "ssh.exe": OPENSSH_SHA256,
            "admitted-openssl-zlib-export": ADMITTED_SIX_EXPORT_SHA256,
        },
        "runtime": {
            "name": "msys2-runtime",
            "sha256": RUNTIME_SHA256,
            "packaged": False,
            "ownership": "external runtime-907 provider",
        },
        "source_verification": source_verification,
        "build": {
            "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
            "build_receipt_sha256": sha256(args.build_receipt),
            "native_job_sha256": sha256(args.native_job),
            "build_log_sha256": sha256(args.build_log),
            "original_driver_sha256": ORIGINAL_DRIVER_SHA256,
            "prefix_map_patch_sha256": PREFIX_PATCH_SHA256,
            "modified_driver_sha256": MODIFIED_DRIVER_SHA256,
            "flags_preserved": ["-O2", "-g", "-fstack-protector-strong"],
            "prefix_maps": [
                "-ffile-prefix-map",
                "-fdebug-prefix-map",
                "-fmacro-prefix-map",
            ],
            "tests": tests,
            "created_processes": process["created_processes"],
            "observed_processes": process["observed_processes"],
        },
        "abi": {
            "path": "abi-comparison.json",
            "sha256": sha256(output / "abi-comparison.json"),
            "unchanged": True,
        },
        "private_path_scan": {
            "path": "libxcrypt-private-path-scan.json",
            "sha256": sha256(output / "libxcrypt-private-path-scan.json"),
            "private_marker_count": 0,
            "runtime_visible_private_source_paths": 0,
            "canonical_source_counts_by_section": scan["canonical_source_counts_by_section"],
        },
        "static_archive_provenance": {
            "path": "static-archive-provenance.json",
            "sha256": sha256(output / "static-archive-provenance.json"),
            "zero_strings_claim": False,
        },
        "package_readback": {
            "path": "package-readback.json",
            "sha256": sha256(output / "package-readback.json"),
        },
        "relocation": {
            "path": "relocation-result.json",
            "sha256": sha256(output / "relocation-result.json"),
            "libxcrypt_direct_consumer": True,
            "loaded_libxcrypt_sha256": new_dll_sha256,
            "openssl_default_paths": True,
            "client_positive_exit": 0,
            "client_wrong_host_exit": 255,
        },
        "admitted_test_dependencies": admitted_dependency_packages,
        "proof_references": proof_references,
        "shipping_policy": {
            "binary_patched": False,
            "stripped_to_remove_private_paths": False,
            "machine_private_receipts_in_packages": False,
            "woarm64_package_provenance_directory_in_packages": False,
            "runtime_dll_repackaged": False,
            "unchanged_openssl_zlib_packages_reexported": False,
            "unchanged_openssh_package_reexported": False,
        },
        "limitations": [
            "Runtime-907 admission and Bash/runtime compatibility remain separate provider-owner work.",
            "OpenSSH remains client-only with its admitted feature and hardening limitations.",
            "The admitted OpenSSL/zlib packages and OpenSSH package were consumed only for focused relocation tests and are not re-exported.",
            "Static development archives retain nonoperational debug/toolchain provenance and have no zero-strings claim.",
            "The sealed toolchain contributes /root/arm64-vnext strings only in PE debug sections; none occur in runtime-visible sections.",
        ],
    }
    write_json(output / "handoff.json", handoff)
    export = {
        "schema": 1,
        "status": handoff["status"],
        "packages": package_exports,
        "handoff": {"path": "handoff.json", "sha256": sha256(output / "handoff.json")},
        "external_proofs": proof_references,
        "package_readback": handoff["package_readback"],
        "relocation": handoff["relocation"],
        "private_path_scan": handoff["private_path_scan"],
        "abi": handoff["abi"],
        "runtime_external_sha256": RUNTIME_SHA256,
        "exact_dependency_bindings": handoff["dependency_bindings"],
        "supersedes": handoff["supersedes"],
    }
    write_json(output / "export.json", export)
    print(
        json.dumps(
            {
                "export": str(output / "export.json"),
                "export_sha256": sha256(output / "export.json"),
                "handoff": str(output / "handoff.json"),
                "handoff_sha256": sha256(output / "handoff.json"),
                "packages": package_exports,
                "msys_crypt_2_dll_sha256": new_dll_sha256,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
