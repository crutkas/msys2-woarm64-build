"""Package and relocate the qualified native MSYS OpenSSL dependency cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import urllib.request


RUNTIME_SHA256 = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
OPENSSL_CRYPTO_SHA256 = "1f849092ae4f5aa3df1b0a7360c626a7e841c9060e8413220df4e862160c4cb4"
OPENSSL_SSL_SHA256 = "5db603a6df4757055b5e6947cd6051956da311644ae5e9010cdaaf786693b374"
OPENSSL_TEST_EXECUTABLE_SHA256 = "b9486392d0ede8a8f2daa10c9f442fea5e956d4f0a5f28da3d1309771b5c99c8"
ZLIB_SHA256 = "edb3e9e04c03df58e2f45a416e73c966e4580fedc8b1a60b7630d3cf7815e9d4"
LIBXCRYPT_SHA256 = "ce687271a36f2281ee65991b6cb18efbc3eb3bb45b4f9169a31d3d7d23d45dbe"
OPENSSH_SHA256 = "9a6eb24cc5667ceadbe73877c97e075587ccec2c34b26fa862e5f7b1ca37d051"
OPENSSH_PACKAGE_SHA256 = "8579eb15dd2048a6a728a6d2d41f1a267a7d4c972a1dd5b2b50660036900b432"

FORBIDDEN = (
    b".copilot",
    b"session-state",
    b"c:/users",
    b"c:\\users",
    b"/mnt/c/users",
    b"/root/arm64-vnext",
    b"/c/ap13-dcb",
    b"c:/ap13-dcb",
)

SOURCES = {
    "openssl": {
        "version": "3.6.4",
        "archive": "openssl-3.6.4.tar.gz",
        "archive_url": (
            "https://github.com/openssl/openssl/releases/download/"
            "openssl-3.6.4/openssl-3.6.4.tar.gz"
        ),
        "sha256": "9bffaa1ad1e07b354c21bd3324ec02fa15579f45a7d0494b3e74bc449b7333ef",
        "signature_url": (
            "https://github.com/openssl/openssl/releases/download/"
            "openssl-3.6.4/openssl-3.6.4.tar.gz.asc"
        ),
        "fingerprint": "B146647E45A7B33947AB226B2A2C87D161692D40",
        "recipe_commit": "a37d139eda53b60df3ab3742dd59b86645e2f4a9",
        "recipe_blob": "1a4b97aab057ab154fcc3fc0c7048b7e004abbd5",
    },
    "zlib": {
        "version": "1.3.2",
        "archive": "zlib-1.3.2.tar.xz",
        "archive_url": (
            "https://github.com/madler/zlib/releases/download/v1.3.2/zlib-1.3.2.tar.xz"
        ),
        "sha256": "d7a0654783a4da529d1bb793b7ad9c3318020af77667bcae35f95d0e42a792f3",
        "signature_url": (
            "https://github.com/madler/zlib/releases/download/v1.3.2/zlib-1.3.2.tar.xz.asc"
        ),
        "fingerprint": "5ED46A6721D365587791E2AA783FCD8E58BCAFBA",
        "recipe_commit": "21bfc351a0c20d4f7dd2c564456d99ed69395a18",
        "recipe_blob": "f1dab35bc57e7463f6fe2ad8c3b62b86dc9a17a2",
    },
    "libxcrypt": {
        "version": "4.5.2",
        "archive": "libxcrypt-4.5.2.tar.xz",
        "archive_url": (
            "https://github.com/besser82/libxcrypt/releases/download/"
            "v4.5.2/libxcrypt-4.5.2.tar.xz"
        ),
        "sha256": "71513a31c01a428bccd5367a32fd95f115d6dac50fb5b60c779d5c7942aec071",
        "signature_url": (
            "https://github.com/besser82/libxcrypt/releases/download/"
            "v4.5.2/libxcrypt-4.5.2.tar.xz.asc"
        ),
        "fingerprint": "678CE3FEE430311596DB8C16F52E98007594C21D",
        "recipe_commit": "5b84e2f8c4ea1783e03d6a43b32b94c2692291a6",
        "recipe_blob": "fbe0e4c6652b11cb33cc39517617df5cd17cbc23",
    },
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def require_sha256(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {path}: expected {expected}, observed {actual}")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    log: Path | None = None,
    timeout: int = 1800,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if log is not None:
        log.write_text(
            "$ " + subprocess.list2cmdline(command) + "\n"
            + result.stdout
            + ("\n--- stderr ---\n" + result.stderr if result.stderr else ""),
            encoding="utf-8",
        )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {subprocess.list2cmdline(command)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def pe_machine(path: Path) -> str:
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise RuntimeError(f"not a PE image: {path}")
        offset = struct.unpack_from("<I", header, 60)[0]
        stream.seek(offset)
        pe = stream.read(26)
    if pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 24)[0] != 0x20B:
        raise RuntimeError(f"not an ordinary PE32+ image: {path}")
    return f"0x{struct.unpack_from('<H', pe, 4)[0]:04X}"


def copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, copy_function=shutil.copy2, symlinks=True)


def copy_evidence(source: Path, target: Path) -> dict[str, object]:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {"path": target.as_posix(), "sha256": sha256(target)}


def cygpath(bootstrap: Path, path: Path) -> str:
    result = run([str(bootstrap / "usr/bin/cygpath.exe"), "-u", str(path)])
    return result.stdout.strip()


def install_openssl_docs(bootstrap: Path, build_source: Path, work: Path, logs: Path) -> Path:
    copied = work / "openssl-doc-build"
    docs = work / "openssl-doc-stage"
    copy_tree(build_source, copied)
    env = os.environ.copy()
    env.update(
        {
            "MSYSTEM": "MSYS",
            "CHERE_INVOKING": "1",
            "MSYS2_PATH_TYPE": "minimal",
            "DOC_BUILD": str(copied),
            "DOC_STAGE": str(docs),
        }
    )
    command = [
        str(bootstrap / "usr/bin/bash.exe"),
        "--noprofile",
        "--norc",
        "-lc",
        (
            'export PATH=/usr/bin:/usr/bin/core_perl; '
            'cd "$(cygpath -u "$DOC_BUILD")"; '
            'make -j1 DESTDIR="$(cygpath -u "$DOC_STAGE")" '
            "MANDIR=/usr/share/man MANSUFFIX=ssl install_docs"
        ),
    ]
    run(command, env=env, log=logs / "openssl-install-docs.log", timeout=3600)
    for relative in (
        "usr/share/man/man1",
        "usr/share/man/man3",
        "usr/share/man/man5",
        "usr/share/man/man7",
        "usr/share/doc",
    ):
        if not (docs / relative).is_dir():
            raise RuntimeError(f"OpenSSL documentation install omitted {relative}")
    return docs


def makepkg_config(bootstrap: Path, root: Path) -> Path:
    config = root / "makepkg.conf"
    values = {
        "PKGDEST": root / "packages",
        "SRCDEST": root / "sources",
        "SRCPKGDEST": root / "source-packages",
        "LOGDEST": root / "logs",
        "BUILDDIR": root / "build",
    }
    for path in values.values():
        path.mkdir(parents=True, exist_ok=True)
    lines = [
        "source /etc/makepkg.conf",
        "CARCH=aarch64",
        "CHOST=aarch64-pc-cygwin",
        "PACKAGER='Git for Windows ARM64 Provider <native-provider@example.invalid>'",
        "PKGEXT='.pkg.tar.zst'",
        "COMPRESSZST=(zstd -c -T1 -z -q -)",
    ]
    for name, path in values.items():
        lines.append(f"{name}='{cygpath(bootstrap, path)}'")
    config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config


def make_package(
    bootstrap: Path,
    root: Path,
    name: str,
    pkgbuild: str,
    payloads: dict[str, Path],
    logs: Path,
) -> list[Path]:
    recipe = root / "recipes" / name
    recipe.mkdir(parents=True)
    (recipe / "PKGBUILD").write_bytes(pkgbuild.replace("\r\n", "\n").encode("utf-8"))
    for target_name, source in payloads.items():
        copy_tree(source, recipe / target_name)
    config = makepkg_config(bootstrap, root)
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith(("MSYS", "MINGW", "MAKEPKG", "PKGDEST", "SRCDEST", "BUILDDIR")):
            env.pop(key)
    env.update(
        {
            "MSYSTEM": "MSYS",
            "CHERE_INVOKING": "1",
            "MSYS2_PATH_TYPE": "minimal",
            "HOME": str(root / "home"),
            "RECIPE": str(recipe),
            "CONFIG": str(config),
            "SOURCE_DATE_EPOCH": "1789128000",
            "ZSTD_NBTHREADS": "1",
        }
    )
    (root / "home").mkdir(exist_ok=True)
    before = {path.name for path in (root / "packages").glob("*.pkg.tar.zst")}
    command = [
        str(bootstrap / "usr/bin/bash.exe"),
        "--noprofile",
        "--norc",
        "-lc",
        (
            'export PATH=/usr/bin; cd "$(cygpath -u "$RECIPE")"; '
            'exec makepkg --config "$(cygpath -u "$CONFIG")" '
            "--nodeps --cleanbuild --force --noconfirm"
        ),
    ]
    run(command, env=env, log=logs / f"makepkg-{name}.log", timeout=3600)
    packages = sorted(
        path
        for path in (root / "packages").glob("*.pkg.tar.zst")
        if path.name not in before
    )
    if not packages:
        raise RuntimeError(f"makepkg produced no packages for {name}")
    return packages


def sanitize_package_metadata(
    bootstrap: Path,
    tar: Path,
    packages: list[Path],
    work: Path,
    logs: Path,
) -> list[Path]:
    sanitized_root = work / "sanitized-packages"
    sanitized_root.mkdir()
    records = []
    outputs = []
    for package in packages:
        extraction = sanitized_root / f"{package.name}.root"
        extraction.mkdir()
        run([str(tar), "-xf", str(package), "-C", str(extraction)])
        buildinfo = extraction / ".BUILDINFO"
        text = buildinfo.read_text(encoding="utf-8")
        pkgname = next(
            line.split("=", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("pkgname =")
        )
        lines = []
        for line in text.splitlines():
            if line.startswith("builddir ="):
                line = "builddir = /usr/src/packages/build"
            elif line.startswith("startdir ="):
                line = f"startdir = /usr/src/packages/{pkgname}"
            lines.append(line)
        buildinfo.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        output = sanitized_root / package.name
        env = os.environ.copy()
        env.update(
            {
                "MSYSTEM": "MSYS",
                "CHERE_INVOKING": "1",
                "MSYS2_PATH_TYPE": "minimal",
                "PACKAGE_ROOT": str(extraction),
                "PACKAGE_OUTPUT": str(output),
                "SOURCE_DATE_EPOCH": "1789128000",
            }
        )
        command = [
            str(bootstrap / "usr/bin/bash.exe"),
            "--noprofile",
            "--norc",
            "-lc",
            (
                'set -euo pipefail; export PATH=/usr/bin; '
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
        run(command, env=env, log=logs / f"sanitize-{package.name}.log")
        records.append(
            {
                "name": package.name,
                "original_sha256": sha256(package),
                "sanitized_sha256": sha256(output),
                "change": (
                    "Only .BUILDINFO builddir/startdir were canonicalized; .MTREE and "
                    "the package container were regenerated."
                ),
            }
        )
        outputs.append(output)
    write_json(work / "package-container-sanitization.json", {"schema": 1, "packages": records})
    return outputs


OPENSSL_PKGBUILD = r"""pkgbase=openssl
pkgname=('openssl' 'libopenssl' 'openssl-devel' 'openssl-docs')
pkgver=3.6.4
pkgrel=1
pkgdesc='The Open Source toolkit for Secure Sockets Layer and Transport Layer Security'
arch=('aarch64')
url='https://openssl-library.org'
license=('spdx:Apache-2.0')
options=('!strip' '!debug' '!lto' '!ccache' '!purge' '!zipman' 'staticlibs' 'libtool')
source=()

package_openssl() {
  depends=('libopenssl')
  optdepends=('ca-certificates' 'perl')
  install -dm755 "$pkgdir/usr/bin" "$pkgdir/usr/share/man"
  cp -f "$startdir/payload/bin/openssl.exe" "$startdir/payload/bin/c_rehash" "$pkgdir/usr/bin/"
  cp -a "$startdir/docs/usr/share/man/man1" "$startdir/docs/usr/share/man/man5" "$pkgdir/usr/share/man/"
  cp -a "$startdir/payload/ssl" "$pkgdir/usr/"
}

package_openssl-docs() {
  install -dm755 "$pkgdir/usr/share/man"
  cp -a "$startdir/docs/usr/share/man/man3" "$startdir/docs/usr/share/man/man7" "$pkgdir/usr/share/man/"
  cp -a "$startdir/docs/usr/share/doc" "$pkgdir/usr/share/"
}

package_libopenssl() {
  depends=('msys2-runtime')
  groups=('libraries')
  install -dm755 "$pkgdir/usr/bin" "$pkgdir/usr/lib/openssl"
  cp -f "$startdir/payload/bin/"*.dll "$pkgdir/usr/bin/"
  cp -a "$startdir/payload/lib/openssl/engines-3" "$pkgdir/usr/lib/openssl/"
  chmod -R 755 "$pkgdir/usr/lib/openssl/engines-3"
  cp -a "$startdir/payload/lib/ossl-modules" "$pkgdir/usr/lib/"
  chmod -R 755 "$pkgdir/usr/lib/ossl-modules"
  install -D -m644 "$startdir/payload/share/licenses/openssl/LICENSE.txt" \
    "$pkgdir/usr/share/licenses/openssl/LICENSE.txt"
}

package_openssl-devel() {
  pkgdesc='Openssl headers and libraries'
  groups=('development')
  depends=("libopenssl=${pkgver}")
  install -dm755 "$pkgdir/usr/lib"
  cp -a "$startdir/payload/include" "$pkgdir/usr/"
  cp -a "$startdir/payload/lib/pkgconfig" "$pkgdir/usr/lib/"
  cp -f "$startdir/payload/lib/"*.a "$pkgdir/usr/lib/"
}
"""

ZLIB_PKGBUILD = r"""pkgbase=zlib
pkgname=('zlib' 'zlib-devel')
pkgver=1.3.2
pkgrel=1
pkgdesc='Compression library implementing the deflate compression method found in gzip and PKZIP'
arch=('aarch64')
groups=('libraries')
license=('spdx:Zlib')
url='https://www.zlib.net/'
options=('!strip' '!debug' '!lto' '!ccache' '!purge' '!zipman' 'staticlibs' 'libtool')
source=()

package_zlib() {
  depends=('gcc-libs' 'msys2-runtime')
  install -dm755 "$pkgdir/usr"
  cp -a "$startdir/payload/usr/bin" "$startdir/payload/usr/share" "$pkgdir/usr/"
}

package_zlib-devel() {
  pkgdesc='zlib headers and libraries'
  groups=('development')
  depends=("zlib=${pkgver}")
  install -dm755 "$pkgdir/usr"
  cp -a "$startdir/payload/usr/include" "$startdir/payload/usr/lib" "$pkgdir/usr/"
  sed -i 's/ -L${sharedlibdir}//g' "$pkgdir/usr/lib/pkgconfig/zlib.pc"
}
"""

LIBXCRYPT_PKGBUILD = r"""pkgbase=libxcrypt
pkgname=('libxcrypt' 'libxcrypt-devel')
pkgver=4.5.2
pkgrel=1
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


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "native-msys-provider-packager/1"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def source_verification(gpg: Path, evidence: Path, logs: Path) -> list[dict[str, object]]:
    source_root = evidence / "source-inputs"
    source_root.mkdir(parents=True)
    gpg_home = evidence / "gnupg"
    gpg_home.mkdir()
    bootstrap = gpg.parents[2]
    gpg_home_msys = cygpath(bootstrap, gpg_home)
    records = []
    for name, source in SOURCES.items():
        archive = source_root / str(source["archive"])
        signature = source_root / f"{source['archive']}.asc"
        key = source_root / f"{name}-{source['fingerprint']}.asc"
        recipe = source_root / f"{name}-PKGBUILD"
        download(str(source["archive_url"]), archive)
        download(str(source["signature_url"]), signature)
        key_urls = (
            (
                "https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x"
                f"{source['fingerprint']}"
            ),
            f"https://keys.openpgp.org/vks/v1/by-fingerprint/{source['fingerprint']}",
        )
        key_error = None
        for key_url in key_urls:
            try:
                download(key_url, key)
                if key.stat().st_size:
                    key_error = None
                    break
            except Exception as error:  # Network fallback is intentionally bounded to two public key URLs.
                key_error = error
        if key_error is not None:
            raise key_error
        recipe_url = (
            "https://raw.githubusercontent.com/msys2/MSYS2-packages/"
            f"{source['recipe_commit']}/{name}/PKGBUILD"
        )
        download(recipe_url, recipe)
        require_sha256(archive, str(source["sha256"]))
        env = os.environ.copy()
        env.pop("GNUPGHOME", None)
        import_result = run(
            [
                str(gpg),
                "--batch",
                "--homedir",
                gpg_home_msys,
                "--import",
                cygpath(bootstrap, key),
            ],
            env=env,
            log=logs / f"gpg-import-{name}.log",
        )
        verify = run(
            [
                str(gpg),
                "--batch",
                "--homedir",
                gpg_home_msys,
                "--status-fd",
                "1",
                "--verify",
                cygpath(bootstrap, signature),
                cygpath(bootstrap, archive),
            ],
            env=env,
            log=logs / f"gpg-verify-{name}.log",
        )
        valid = re.findall(r"^\[GNUPG:\] VALIDSIG (.+)$", verify.stdout, re.MULTILINE)
        valid_tokens = {token for line in valid for token in line.split()}
        if str(source["fingerprint"]) not in valid_tokens:
            raise RuntimeError(
                f"{name} signature did not bind the expected primary fingerprint: {valid}"
            )
        records.append(
            {
                "name": name,
                "version": source["version"],
                "archive": {
                    "path": archive.relative_to(evidence.parent).as_posix(),
                    "sha256": sha256(archive),
                    "url": source["archive_url"],
                },
                "signature": {
                    "path": signature.relative_to(evidence.parent).as_posix(),
                    "sha256": sha256(signature),
                    "url": source["signature_url"],
                    "valid_signer_fingerprint": source["fingerprint"],
                },
                "public_key": {
                    "path": key.relative_to(evidence.parent).as_posix(),
                    "sha256": sha256(key),
                },
                "msys2_recipe": {
                    "path": recipe.relative_to(evidence.parent).as_posix(),
                    "sha256": sha256(recipe),
                    "commit": source["recipe_commit"],
                    "git_blob": source["recipe_blob"],
                    "url": recipe_url,
                },
                "gpg_import_output": import_result.stderr.strip(),
            }
        )
    return records


def package_entries(tar: Path, package: Path) -> list[str]:
    return run([str(tar), "-tf", str(package)]).stdout.splitlines()


def package_info(tar: Path, package: Path) -> str:
    return run([str(tar), "-xOf", str(package), ".PKGINFO"]).stdout


def inspect_packages(tar: Path, packages: list[Path], root: Path) -> list[dict[str, object]]:
    readback = root / "package-readback"
    readback.mkdir()
    records = []
    for package in packages:
        entries = package_entries(tar, package)
        if any("woarm64-package-provenance" in entry for entry in entries):
            raise RuntimeError(f"private provenance payload leaked into {package}")
        pkginfo = package_info(tar, package)
        (readback / f"{package.name}.PKGINFO").write_text(pkginfo, encoding="utf-8")
        extract = readback / package.name
        extract.mkdir()
        run([str(tar), "-xf", str(package), "-C", str(extract)])
        files = []
        for path in sorted(extract.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            relative = path.relative_to(extract).as_posix()
            lowered = path.read_bytes().lower()
            is_pe = path.suffix.lower() in (".exe", ".dll")
            is_archive = path.suffix.lower() == ".a"
            hits = []
            if not is_archive:
                hits = [marker.decode(errors="replace") for marker in FORBIDDEN if marker in lowered]
            if is_pe and relative == "usr/bin/msys-crypt-2.dll":
                # This exact required DLL retains sealed runtime/toolchain debug provenance.
                # Its admitted consumer identity must not be changed by repackaging.
                hits = [
                    hit for hit in hits
                    if hit != "/root/arm64-vnext"
                ]
            if hits:
                raise RuntimeError(f"forbidden shipping marker in {package.name}:{relative}: {hits}")
            record = {"path": relative, "size": path.stat().st_size, "sha256": sha256(path)}
            if is_pe:
                record["machine"] = pe_machine(path)
                if record["machine"] != "0xAA64":
                    raise RuntimeError(f"non-AA64 image in {package.name}:{relative}")
            files.append(record)
        records.append(
            {
                "name": next(
                    line.split("=", 1)[1].strip()
                    for line in pkginfo.splitlines()
                    if line.startswith("pkgname =")
                ),
                "path": f"packages/{package.name}",
                "sha256": sha256(package),
                "entries": len(entries),
                "files": files,
                "pkginfo": f"package-readback/{package.name}.PKGINFO",
            }
        )
    return records


def merge_package(tar: Path, package: Path, extraction: Path, relocated: Path) -> None:
    target = extraction / package.name
    target.mkdir(parents=True)
    run([str(tar), "-xf", str(package), "-C", str(target)])
    for child in target.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir():
            shutil.copytree(child, relocated / child.name, dirs_exist_ok=True, copy_function=shutil.copy2)
        else:
            shutil.copy2(child, relocated / child.name)


def relocated_controls(
    tar: Path,
    packages: list[Path],
    openssh_package: Path,
    runtime: Path,
    native_python: Path,
    fixture_script: Path,
    fixture_driver: Path,
    pwsh: Path,
    output: Path,
) -> dict[str, object]:
    relocated = output / "relocated-root"
    extraction = output / "relocated-package-extractions"
    relocated.mkdir()
    extraction.mkdir()
    all_packages = [*packages, openssh_package]
    for package in all_packages:
        merge_package(tar, package, extraction, relocated)
    runtime_target = relocated / "usr/bin/msys-2.0.dll"
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime, runtime_target)

    required = {
        relocated / "usr/bin/msys-2.0.dll": RUNTIME_SHA256,
        relocated / "usr/bin/msys-crypto-3.dll": OPENSSL_CRYPTO_SHA256,
        relocated / "usr/bin/msys-ssl-3.dll": OPENSSL_SSL_SHA256,
        relocated / "usr/bin/msys-z.dll": ZLIB_SHA256,
        relocated / "usr/bin/msys-crypt-2.dll": LIBXCRYPT_SHA256,
        relocated / "usr/bin/ssh.exe": OPENSSH_SHA256,
    }
    for path, expected in required.items():
        require_sha256(path, expected)
        if pe_machine(path) != "0xAA64":
            raise RuntimeError(f"relocated image is not AA64: {path}")

    env = {
        name: os.environ[name]
        for name in ("SystemRoot", "WINDIR", "COMSPEC", "USERNAME", "USERDOMAIN", "PROGRAMDATA")
        if name in os.environ
    }
    env["PATH"] = str(relocated / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["HOME"] = env["USERPROFILE"] = str(output / "openssl-home")
    Path(env["HOME"]).mkdir()
    openssl = relocated / "usr/bin/openssl.exe"
    commands = {
        "version": [str(openssl), "version", "-a"],
        "configdir": [str(openssl), "info", "-configdir"],
        "enginesdir": [str(openssl), "info", "-enginesdir"],
        "modulesdir": [str(openssl), "info", "-modulesdir"],
        "legacy_provider": [str(openssl), "list", "-providers", "-provider", "legacy", "-verbose"],
        "dasync_engine": [str(openssl), "engine", "-t", "-c", "dasync"],
    }
    command_records = {}
    for name, command in commands.items():
        result = run(command, env=env, log=output / f"openssl-{name}.log", timeout=120)
        command_records[name] = {
            "argv": command,
            "exit": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    expected_paths = {
        "configdir": "/usr/ssl",
        "enginesdir": "/usr/lib/openssl/engines-3",
        "modulesdir": "/usr/lib/ossl-modules",
    }
    for name, expected in expected_paths.items():
        if expected not in command_records[name]["stdout"]:
            raise RuntimeError(f"relocated OpenSSL reported the wrong {name}")
    if "legacy" not in command_records["legacy_provider"]["stdout"].lower():
        raise RuntimeError("relocated OpenSSL did not load the legacy provider from its default module path")
    if "dasync" not in command_records["dasync_engine"]["stdout"].lower():
        raise RuntimeError("relocated OpenSSL did not load the dasync engine from its default engine path")

    csr = output / "relocation.csr"
    key = output / "relocation.key"
    req = [
        str(openssl),
        "req",
        "-new",
        "-newkey",
        "ed25519",
        "-nodes",
        "-batch",
        "-subj",
        "/CN=native-msys-package-relocation",
        "-keyout",
        str(key),
        "-out",
        str(csr),
    ]
    req_result = run(req, env=env, log=output / "openssl-default-config-request.log", timeout=120)
    command_records["default_config_request"] = {
        "argv": req,
        "exit": req_result.returncode,
        "csr_sha256": sha256(csr),
        "key_sha256": sha256(key),
    }

    handshake = output / "controlled-ssh"
    python_env = os.environ.copy()
    python_env["PATH"] = str(native_python.parent) + os.pathsep + python_env.get("PATH", "")
    run(
        [
            str(native_python),
            str(fixture_script),
            "--client",
            str(relocated / "usr/bin/ssh.exe"),
            "--test-driver",
            str(fixture_driver),
            "--output",
            str(handshake),
            "--pwsh",
            str(pwsh),
        ],
        env=python_env,
        log=output / "controlled-ssh-driver.log",
        timeout=180,
    )
    handshake_result = json.loads((handshake / "result.json").read_text(encoding="utf-8"))
    if not (
        handshake_result.get("passed")
        and [case.get("raw_exit") for case in handshake_result.get("cases", [])] == [0, 255]
    ):
        raise RuntimeError("relocated OpenSSH positive/wrong-host control failed")

    return {
        "schema": 1,
        "passed": True,
        "relocated_root": str(relocated),
        "runtime_test_only": {
            "path": str(runtime_target),
            "sha256": sha256(runtime_target),
            "packaged": False,
        },
        "required_images": [
            {
                "path": path.relative_to(relocated).as_posix(),
                "sha256": sha256(path),
                "machine": pe_machine(path),
            }
            for path in required
        ],
        "openssl": command_records,
        "controlled_ssh": {
            "result": "controlled-ssh/result.json",
            "sha256": sha256(handshake / "result.json"),
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
    parser.add_argument("--openssl-sdk", type=Path, required=True)
    parser.add_argument("--openssl-build-source", type=Path, required=True)
    parser.add_argument("--zlib-stage", type=Path, required=True)
    parser.add_argument("--libxcrypt-stage", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--openssh-package", type=Path, required=True)
    parser.add_argument("--native-python", type=Path, required=True)
    parser.add_argument("--fixture-script", type=Path, required=True)
    parser.add_argument("--fixture-driver", type=Path, required=True)
    parser.add_argument("--pwsh", type=Path, required=True)
    parser.add_argument("--openssl-source-manifest", type=Path, required=True)
    parser.add_argument("--openssl-suite", type=Path, required=True)
    parser.add_argument("--openssl-native-job", type=Path, required=True)
    parser.add_argument("--openssl-qualification", type=Path, required=True)
    parser.add_argument("--zlib-build-receipt", type=Path, required=True)
    parser.add_argument("--zlib-consumer-receipt", type=Path, required=True)
    parser.add_argument("--zlib-package-handoff", type=Path, required=True)
    parser.add_argument("--zlib-source-manifest", type=Path, required=True)
    parser.add_argument("--libxcrypt-source-manifest", type=Path, required=True)
    parser.add_argument("--libxcrypt-build-receipt", type=Path, required=True)
    parser.add_argument("--libxcrypt-native-job", type=Path, required=True)
    parser.add_argument("--libxcrypt-handoff", type=Path, required=True)
    parser.add_argument("--openssh-export", type=Path, required=True)
    parser.add_argument("--openssh-verdict", type=Path, required=True)
    parser.add_argument("--openssh-verification", type=Path, required=True)
    parser.add_argument("--gpg", type=Path, required=True)
    parser.add_argument("--tar", type=Path, required=True)
    parser.add_argument("--strip", type=Path, required=True)
    parser.add_argument(
        "--reuse-package-root",
        type=Path,
        help="Reuse already-created package archives from a failed validation root.",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing existing output root: {output}")
    output.mkdir(parents=True)
    work = output / "work"
    logs = output / "logs"
    evidence = output / "evidence"
    packages_root = output / "package-build"
    for path in (work, logs, evidence, packages_root):
        path.mkdir()

    require_sha256(args.openssl_sdk / "bin/msys-crypto-3.dll", OPENSSL_CRYPTO_SHA256)
    require_sha256(args.openssl_sdk / "bin/msys-ssl-3.dll", OPENSSL_SSL_SHA256)
    require_sha256(args.openssl_sdk / "bin/openssl.exe", OPENSSL_TEST_EXECUTABLE_SHA256)
    require_sha256(args.zlib_stage / "usr/bin/msys-z.dll", ZLIB_SHA256)
    require_sha256(args.libxcrypt_stage / "usr/bin/msys-crypt-2.dll", LIBXCRYPT_SHA256)
    require_sha256(args.runtime, RUNTIME_SHA256)
    require_sha256(args.openssh_package, OPENSSH_PACKAGE_SHA256)
    if (args.openssl_sdk / "bin/msys-2.0.dll").is_file():
        require_sha256(args.openssl_sdk / "bin/msys-2.0.dll", RUNTIME_SHA256)

    source_records = source_verification(args.gpg, evidence, logs)
    if args.reuse_package_root is not None:
        reuse_root = args.reuse_package_root.resolve()
        built_packages = sorted((reuse_root / "packages").glob("*.pkg.tar.zst"))
        reuse_evidence = evidence / "reused-package-build"
        reuse_evidence.mkdir()
        for name in (
            "makepkg-openssl.log",
            "makepkg-zlib.log",
            "makepkg-libxcrypt.log",
            "openssl-install-docs.log",
            "strip-package-openssl.log",
        ):
            source = reuse_root / "logs" / name
            if source.is_file():
                shutil.copy2(source, reuse_evidence / name)
    else:
        docs = install_openssl_docs(args.bootstrap, args.openssl_build_source, work, logs)

        openssl_payload = work / "openssl-payload"
        copy_tree(args.openssl_sdk, openssl_payload)
        (openssl_payload / "bin/msys-2.0.dll").unlink()
        package_openssl = openssl_payload / "bin/openssl.exe"
        run(
            [str(args.strip), "--strip-debug", "--preserve-dates", str(package_openssl)],
            log=logs / "strip-package-openssl.log",
        )
        if pe_machine(package_openssl) != "0xAA64":
            raise RuntimeError("release-stripped package openssl.exe is not AA64")
        package_openssl_lower = package_openssl.read_bytes().lower()
        package_openssl_hits = [
            marker.decode(errors="replace")
            for marker in FORBIDDEN
            if marker in package_openssl_lower
        ]
        if package_openssl_hits:
            raise RuntimeError(
                f"release-stripped package openssl.exe retains private markers: {package_openssl_hits}"
            )
        if any(path.name.lower() == "msys-2.0.dll" for path in openssl_payload.rglob("*")):
            raise RuntimeError("runtime ownership leaked into the OpenSSL package payload")

        built_packages = []
        built_packages += make_package(
            args.bootstrap,
            packages_root,
            "openssl",
            OPENSSL_PKGBUILD,
            {"payload": openssl_payload, "docs": docs},
            logs,
        )
        built_packages += make_package(
            args.bootstrap,
            packages_root,
            "zlib",
            ZLIB_PKGBUILD,
            {"payload": args.zlib_stage},
            logs,
        )
        built_packages += make_package(
            args.bootstrap,
            packages_root,
            "libxcrypt",
            LIBXCRYPT_PKGBUILD,
            {"payload": args.libxcrypt_stage},
            logs,
        )
    if len(built_packages) != 8:
        raise RuntimeError(f"expected eight split packages, observed {len(built_packages)}")
    built_packages = sanitize_package_metadata(
        args.bootstrap,
        args.tar,
        built_packages,
        work,
        logs,
    )

    final_packages = output / "packages"
    final_packages.mkdir()
    packages = []
    for package in built_packages:
        target = final_packages / package.name
        shutil.copy2(package, target)
        packages.append(target)

    package_records = inspect_packages(args.tar, packages, output)
    package_map = {record["name"]: record for record in package_records}
    required_names = {
        "openssl",
        "libopenssl",
        "openssl-devel",
        "openssl-docs",
        "zlib",
        "zlib-devel",
        "libxcrypt",
        "libxcrypt-devel",
    }
    if set(package_map) != required_names:
        raise RuntimeError(f"unexpected package set: {sorted(package_map)}")

    exact_payload = {
        ("libopenssl", "usr/bin/msys-crypto-3.dll"): OPENSSL_CRYPTO_SHA256,
        ("libopenssl", "usr/bin/msys-ssl-3.dll"): OPENSSL_SSL_SHA256,
        ("zlib", "usr/bin/msys-z.dll"): ZLIB_SHA256,
        ("libxcrypt", "usr/bin/msys-crypt-2.dll"): LIBXCRYPT_SHA256,
    }
    for (package_name, relative), expected in exact_payload.items():
        files = {row["path"]: row for row in package_map[package_name]["files"]}
        if relative not in files or files[relative]["sha256"] != expected:
            raise RuntimeError(f"{package_name} did not preserve {relative}={expected}")
    package_openssl_record = next(
        row
        for row in package_map["openssl"]["files"]
        if row["path"] == "usr/bin/openssl.exe"
    )

    relocation = relocated_controls(
        args.tar,
        packages,
        args.openssh_package,
        args.runtime,
        args.native_python,
        args.fixture_script,
        args.fixture_driver,
        args.pwsh,
        output,
    )
    write_json(output / "relocation-result.json", relocation)
    write_json(output / "package-readback.json", {"schema": 1, "packages": package_records})

    evidence_inputs = {
        "openssl/source-prepare.json": args.openssl_source_manifest,
        "openssl/suite-result.json": args.openssl_suite,
        "openssl/native-job.json": args.openssl_native_job,
        "openssl/dependency-qualification.json": args.openssl_qualification,
        "zlib/build-receipt.json": args.zlib_build_receipt,
        "zlib/consumer-receipt.json": args.zlib_consumer_receipt,
        "zlib/prior-package-handoff.json": args.zlib_package_handoff,
        "zlib/source-manifest.json": args.zlib_source_manifest,
        "libxcrypt/source-prepare.json": args.libxcrypt_source_manifest,
        "libxcrypt/build-receipt.json": args.libxcrypt_build_receipt,
        "libxcrypt/native-job.json": args.libxcrypt_native_job,
        "libxcrypt/provider-handoff.json": args.libxcrypt_handoff,
        "openssh/admitted-export.json": args.openssh_export,
        "openssh/admission-verdict.json": args.openssh_verdict,
        "openssh/independent-verification.json": args.openssh_verification,
    }
    proof_references = []
    for relative, source in evidence_inputs.items():
        target = evidence / relative
        record = copy_evidence(source, target)
        record["name"] = relative
        record["path"] = target.relative_to(output).as_posix()
        proof_references.append(record)
    sanitization = copy_evidence(
        work / "package-container-sanitization.json",
        evidence / "packaging/package-container-sanitization.json",
    )
    sanitization["name"] = "packaging/package-container-sanitization.json"
    sanitization["path"] = "evidence/packaging/package-container-sanitization.json"
    proof_references.append(sanitization)

    package_exports = [
        {"name": record["name"], "path": record["path"], "sha256": record["sha256"]}
        for record in sorted(package_records, key=lambda row: row["name"])
    ]
    handoff = {
        "schema": 1,
        "status": "sealed-native-msys-openssl-dependency-cohort-pending-independent-intake",
        "scope": (
            "Pinned native ARM64 MSYS OpenSSL 3.6.4, zlib 1.3.2, and libxcrypt "
            "4.5.2 package splits preserving the exact client03 dependency bytes."
        ),
        "packages": package_exports,
        "runtime": {
            "name": "msys2-runtime",
            "sha256": RUNTIME_SHA256,
            "packaged": False,
            "ownership": "external runtime-907 provider",
        },
        "dependency_bindings": {
            "msys-crypto-3.dll": OPENSSL_CRYPTO_SHA256,
            "msys-ssl-3.dll": OPENSSL_SSL_SHA256,
            "msys-z.dll": ZLIB_SHA256,
            "msys-crypt-2.dll": LIBXCRYPT_SHA256,
            "openssh-package": OPENSSH_PACKAGE_SHA256,
            "ssh.exe": OPENSSH_SHA256,
        },
        "openssl_executable_projection": {
            "full_suite_test_executable_sha256": OPENSSL_TEST_EXECUTABLE_SHA256,
            "package_executable_sha256": package_openssl_record["sha256"],
            "package_executable_machine": package_openssl_record["machine"],
            "change": "release debug sections removed for the newly shipping command-line package",
            "libraries_rebuilt_or_changed": False,
            "package_executable_targeted_relocation_controls": True,
        },
        "canonical_openssl_paths": {
            "prefix": "/usr",
            "openssldir": "/usr/ssl",
            "enginesdir": "/usr/lib/openssl/engines-3",
            "modulesdir": "/usr/lib/ossl-modules",
        },
        "source_verification": source_records,
        "proof_references": proof_references,
        "package_readback": {
            "path": "package-readback.json",
            "sha256": sha256(output / "package-readback.json"),
        },
        "relocation": {
            "path": "relocation-result.json",
            "sha256": sha256(output / "relocation-result.json"),
            "openssl_default_config": True,
            "legacy_provider_default_path": True,
            "dasync_engine_default_path": True,
            "client_positive_exit": 0,
            "client_wrong_host_exit": 255,
        },
        "shipping_policy": {
            "machine_private_receipts_in_packages": False,
            "woarm64_package_provenance_directory_in_packages": False,
            "runtime_dll_repackaged": False,
            "qualified_library_bits_changed": False,
            "package_openssl_executable_release_stripped": True,
            "original_receipts_retained_externally": True,
        },
        "limitations": [
            "Runtime-907 admission and Bash/runtime compatibility remain separate provider-owner work.",
            "The unchanged OpenSSH provider remains client-only with its admitted feature and hardening limitations.",
            "The OpenSSL full-suite evidence is preserved rather than rerun; package relocation uses targeted exact-byte controls.",
            "The exact required libxcrypt DLL retains sealed runtime/toolchain debug provenance; its required SHA-256 is preserved unchanged.",
            "Static development archives remain exact ABI-cohort bytes and are not rewritten to remove build-time debug paths.",
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
        "runtime_external_sha256": RUNTIME_SHA256,
        "exact_dependency_bindings": handoff["dependency_bindings"],
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
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise
