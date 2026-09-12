"""Prepare the pinned native POSIX build utilities in the original recipe order."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

from sources import ContractError, digest, inventory, relative_path, verify_tree


RECIPES = {
    "zlib-msys": {"source_id": "zlib", "recipe_name": "zlib", "version": "1.3.2",
                  "dependencies": ["gcc-libs"],
                  "build_policy": {"makefile": "win32/Makefile.gcc", "SHAREDLIB": "msys-z.dll",
                                   "MSYSTEM": "CYGWIN", "upstream_check_target": "test"},
                  "steps": [("patch", "zlib-1.2.13-configure.patch", 2),
                            ("patch", "zlib-1.2.13-gzopen_w.patch", 2)]},
    "bzip2": {"version": "1.0.8", "dependencies": ["gcc-libs"],
              "steps": [("patch", "bzip2-1.0.6-msys-dll.patch", 1),
                        ("patch", "bzip2-1.0.6-msys2.patch", 1)]},
    "xz": {"version": "5.8.3", "dependencies": ["libiconv", "gettext"],
           "build_policy": {"windows_doxygen_paths": True},
           "steps": [("local-patch", "xz-windows-doxygen-paths.patch", 1),
                     ("generate", "./autogen.sh")]},
    "zstd": {"version": "1.5.7", "dependencies": ["gcc-libs"],
             "build_policy": {"ZSTD_PROGRAMS_LINK_SHARED": "ON"},
             "steps": [("local-patch", "zstd-native-windows-build-aliases.patch", 1),
                       ("local-file", "cmake/ZstdProgramAlias.cmake", "build/cmake/programs/ZstdProgramAlias.cmake")]},
    "cmocka": {"version": "1.1.8", "recipe_collection": "mingw-upstream-recipes",
               "recipe_name": "mingw-w64-cmocka", "dependencies": [],
               "build_policy": {"UNIT_TESTING": "ON", "WITH_CMOCKERY_SUPPORT": "ON",
                                "source_provenance": "Archive pin only from MinGW recipe; no MinGW binary or ABI substitution"},
               "steps": [("local-patch", "cmocka-optional-source-compilation-database.patch", 1),
                         ("local-patch", "cmocka-single-config-test-dll-path.patch", 1)]},
    "heimdal": {"version": "7.8.0", "dependencies": ["libdb", "libxcrypt", "libedit", "libsqlite", "libopenssl"],
                "steps": [*[("patch", name, strip) for name, strip in (
                    ("1.2.1-test-modules.patch", 2), ("1.5.2-hdbdir.patch", 2),
                    ("1.5.2-install-catman.patch", 2), ("1.5.2-roken-signal.patch", 2),
                    ("1.5.3-missing-libs-pkg-config.patch", 1), ("1.5.3-fix-detect-libedit.patch", 1),
                    ("7.5.0-hcrypto-build-fix.patch", 1), ("7.5.0-names-clash-with-openssl.patch", 1),
                    ("1041.patch", 1))], ("generate", "./autogen.sh")]},
    "libcbor": {"version": "0.14.0", "dependencies": [],
                "build_policy": {"allocator_api": "unconditional cbor_set_allocs; verify actual export",
                                 "WITH_EXAMPLES": "OFF", "BUILD_SHARED_LIBS": "ON"},
                "steps": []},
    "libfido2": {"version": "1.17.0", "dependencies": ["libcbor", "openssl", "zlib"],
                 "build_policy": {"USE_WINHELLO": "ON", "authentication_execution": "requires separate authorization"},
                 "steps": [("patch", "msys2-fix-ln.diff", 1),
                           ("local-patch", "libfido2-native-man-copy.patch", 1)]},
    "db": {"version": "6.2.32", "dependencies": ["gcc-libs", "sh"],
           "steps": [("generate-in", "dist", "env", "ac_macrodir=aclocal", "libtoolize", "--copy", "--force", "--install"),
                     ("generate-in", "dist", "./s_config")]},
    "sqlite-msys": {"recipe_name": "sqlite", "version": "3.53.4",
                    "dependencies": ["libreadline", "zlib", "tcl"],
                    "steps": [*[("patch", name, 1) for name in (
                        "0001-sqlite-pcachetrace-include-sqlite3.patch",
                        "0002-sqlite3.32.3-Makefile.in-fix-rule-compiling-rbu.exe.patch",
                        "0031-use-packaged-lempar.c.patch")],
                              *[("copy-resource", name) for name in ("LICENSE", "Makefile.ext.in", "README.md.in")]]},
    "file": {"version": "5.48", "dependencies": ["zlib", "libbz2", "liblzma", "libzstd"],
             "steps": [("generate", "autoreconf", "-fiv")]},
    "readline": {"version": "8.3", "package_version": "8.3.003", "dependencies": ["ncurses"],
                 "steps": [*[("source-patch", f"readline83-{number:03d}", 0) for number in range(1, 4)],
                           ("patch", "readline-7.0.3-3.src.patch", 2),
                           ("patch", "readline-6.3-msys2.patch", 1),
                           ("patch", "readline-6.3-paste-utf8.patch", 1),
                           ("patch", "readline-7.0.3-3.clipboard.patch", 1),
                           ("copy-resource", "inputrc")]},
    "libtool-msys": {"recipe_name": "libtool", "version": "2.6.2",
                    "dependencies": ["autoconf", "automake", "m4", "bash"],
                    "steps": [*[("patch", name, 1) for name in (
                        "0001-cygwin-mingw-Create-UAC-manifest-files.patch",
                        "0002-Fix-seems-to-be-moved.patch",
                        "0003-Fix-STRICT_ANSI-vs-POSIX.patch",
                        "0004-Allow-statically-linking-Flang-support-libraries-whe.patch",
                        "0005-libtool-include-process.h.patch",
                        "0006-Pass-various-flags-to-GCC.patch",
                        "0007-msysize.patch",
                        "0014-Support-llvm-objdump-f-output.patch")],
                              ("generate", "autoconf", "-f")]},
    "sed": {"version": "4.9", "dependencies": ["libintl", "sh"],
            "steps": [("patch", "sed-4.4-msys-use-text-mode.patch", 1),
                      ("generate", "autoreconf", "-fiv"),
                      ("patch", "sed-4.4-1.src.patch", 2)]},
    "gawk": {"version": "5.4.1", "dependencies": ["sh", "mpfr", "libintl", "libreadline"],
             "steps": [("generate", "autoreconf", "-fiv")]},
    "grep": {"version": "3.0", "dependencies": ["libiconv", "libintl", "libpcre", "sh"],
             "steps": [("permissions",), ("generate", "autoreconf", "-fi")]},
    "findutils": {"version": "4.11.0", "dependencies": ["libiconv", "libintl"],
                  "steps": [("generate", "autoreconf", "-fi")]},
    "ncurses": {"version": "6.6", "dependencies": ["gcc-libs"],
                "steps": [("patch", "ncurses-6.3-pkgconfig.patch", 1),
                          ("patch", "ncurses-6.3-cflags-private.patch", 1)]},
    "nano": {"version": "9.2", "dependencies": ["file", "libintl", "ncurses", "sh"],
             "steps": [("generate", "autoreconf", "-vfi")]},
    "openssh": {"version": "10.5p1", "dependencies": ["heimdal", "libedit", "libxcrypt", "libfido2", "openssl"],
                "steps": [("patch", "openssh-7.3p1-msys2.patch", 1),
                          ("patch", "openssh-7.3p1-msys2-setkey.patch", 1),
                          ("patch", "openssh-7.3p1-msys2-drive-name-in-path.patch", 1),
                          ("generate", "autoreconf", "-fvi")]},
    "libedit": {"version": "20240808-3.1", "dependencies": ["ncurses", "sh"],
                "steps": [("patch", "cygwin-build.patch", 1),
                          ("patch", "libedit-20191231-3.1.patch", 1),
                          ("generate", "autoreconf", "-fi")]},
    "libxcrypt": {"version": "4.5.2", "dependencies": [],
                  "steps": [("patch", "4.4.2-cygwin-no-undefined.patch", 2),
                            ("local-patch", "libxcrypt-coff-private-refptr-test.patch", 1),
                            ("generate", "autoreconf", "-vfi")]},
    "libiconv-msys": {"source_id": "libiconv", "recipe_name": "libiconv", "version": "1.19",
                     "dependencies": ["gcc-libs", "libintl"],
                     "steps": [("patch", "1.16-aliases.patch", 1),
                               ("patch", "1.16-cross-install.patch", 1),
                               ("patch", "1.16-wchar.patch", 1),
                               ("patch", "libiconv-1.16-msysize.patch", 1),
                               ("patch", "0001-fixes-building-with-gcc-15.patch", 1),
                               ("copy-macros", "srcm4", "m4"),
                               ("generate-in", "libcharset", "autoreconf", "-fiv"),
                               ("generate", "autoreconf", "-fiv")]},
    "gettext-msys": {"recipe_name": "gettext", "version": "0.22.5",
                     "dependencies": ["libiconv", "gcc-libs"],
                     "steps": [
                         *[("patch", name, 1) for name in (
                             "gettext-tools-tests-locale-ll-es.patch",
                             "gettext-0.21.1-autopoint-V.patch",
                             "gettext-0.21.1-cygwin-ftm.patch",
                             "gettext-0.22-no-woe32dll-gettext-tools-configure-ac.patch",
                             "gettext-0.22-no-woe32dll-m4-woe32-dll-m4.patch",
                             "gettext-0.22.5-gettext-runtime-gnulib-lib-localcharset-c.patch",
                             "gettext-0.22.5-gettext-runtime-gnulib-lib-localename-h.patch",
                             "gettext-0.22.5-gettext-runtime-gnulib-lib-localename-unsafe-c.patch",
                             "gettext-0.22.5-gettext-runtime-intl-gnulib-lib-localcharset-c.patch",
                             "gettext-0.22.5-gettext-runtime-intl-gnulib-lib-localename-h.patch",
                             "gettext-0.22.5-gettext-runtime-intl-gnulib-lib-localename-unsafe-c.patch",
                             "gettext-0.22.5-gettext-tools-gnulib-lib-localcharset-c.patch",
                             "gettext-0.22.5-gettext-tools-gnulib-lib-localename-h.patch",
                             "gettext-0.22.5-gettext-tools-gnulib-lib-localename-unsafe-c.patch",
                             "gettext-0.22-disable-libtextstyle.patch",
                             "gettext-0.19.8.1-msys2.patch")],
                         ("autopoint-archive", "gettext-0.19.7-archive.patch"),
                         ("generate", "libtoolize", "--copy", "--force"),
                         ("generate", "./autogen.sh", "--skip-gnulib")]},
}
ADAPTED_PATCHES = {
    ("openssh", "openssh-7.3p1-msys2.patch"): "openssh-10.5p1-msys.patch",
    ("openssh", "openssh-7.3p1-msys2-setkey.patch"): "openssh-10.5p1-msys-setkey.patch",
    ("libiconv-msys", "libiconv-1.16-msysize.patch"): "libiconv-1.19-msys-macro-dir.patch",
    ("gettext-msys", "gettext-0.22-disable-libtextstyle.patch"): "gettext-0.22.5-disable-libtextstyle.patch",
    ("gettext-msys", "gettext-0.19.8.1-msys2.patch"): "gettext-0.22.5-msys-platforms.patch",
}
PATCH_CONTEXTS = {
    ("heimdal", "1.5.2-hdbdir.patch"): (
        (" Note that the file name is space sensitive.\n",
         " Note that the file contents are space sensitive.\n"),
        (" \tdefault = SYSLOG:INFO:USER\n .Ed\n",
         " \tdefault = SYSLOG:INFO:USER\n [kadmin]\n"),
    ),
    ("readline", "readline-7.0.3-3.src.patch"): (
        (" everything: all\n \n check:\trlversion$(EXEEXT)\n",
         " \t${MAKE} ${MFLAGS} ASAN_CFLAGS='${ASAN_XCFLAGS}' ASAN_LDFLAGS='${ASAN_XLDFLAGS}' all\n \n check:\trlversion$(EXEEXT)\n"),
    ),
    ("readline", "readline-6.3-paste-utf8.patch"): (
        ("@@ -660,16 +660,40 @@\n #if defined (_WIN32)\n #include <windows.h>\n",
         "@@ -662,16 +662,40 @@\n \n #include <windows.h>\n"),
    ),
    ("readline", "readline-7.0.3-3.clipboard.patch"): (
        ('   { "non-incremental-reverse-search-history-again", rl_noninc_reverse_search_again },\n'
         '   { "old-menu-complete", rl_old_menu_complete },\n',
         '   { "old-menu-complete", rl_old_menu_complete },\n'
         '   { "operate-and-get-next", rl_operate_and_get_next },\n'),
    ),
}


def adapt_package_context(key, text):
    for before, after in PATCH_CONTEXTS[key]:
        if text.count(before) != 1:
            raise ContractError("Unexpected pinned package patch context")
        text = text.replace(before, after)
    return text


def adapt_autopoint_patch(text):
    targets = {f"archive-orig/gettext-0.22.{version}/m4/build-to-host.m4.orig" for version in range(1, 5)}
    changed = []
    sections = re.split(r"(?=^--- )", text, flags=re.MULTILINE)
    for index, section in enumerate(sections):
        if not section.startswith("--- "):
            continue
        path = section.splitlines()[0].split()[1]
        if path not in targets:
            continue
        before = "         mingw*)\n"
        if (path in changed or section.count(before) != 1 or
                section.count("+    cygwin* | msys*)\n") != 1):
            raise ContractError("Unexpected gettext archive host-conversion patch context")
        sections[index] = section.replace(before, "         mingw* | windows*)\n")
        changed.append(path)
    if set(changed) != targets:
        raise ContractError("Expected exactly the four gettext 0.22.1-0.22.4 archive contexts")
    return "".join(sections), sorted(changed)


def prepare_autopoint_archive(output, patch, recipe_text, environment, log):
    archive = output / "gettext-tools/misc/archive.dir.tar"
    before = digest(archive)
    patch_sha = digest(patch)
    if patch_sha not in recipe_text:
        raise ContractError("Autopoint archive patch is not bound to the pinned recipe")
    adapted, adaptations = adapt_autopoint_patch(patch.read_text())
    adapted_patch = output.with_name(output.name + ".autopoint-adapted.patch")
    adapted_patch.write_text(adapted, newline="\n")
    working = output.with_name(output.name + ".autopoint-archive")
    working.mkdir()
    with tarfile.open(archive) as source:
        seen = set()
        for member in source.getmembers():
            name = member.name.rstrip("/")
            relative_path(name)
            if name in seen or not (member.isfile() or member.isdir()):
                raise ContractError("Unsupported or duplicate nested autopoint archive entry")
            seen.add(name)
        source.extractall(working, filter="data")
    original = inventory(working)
    command = ["patch", "--batch", "--forward", "--fuzz=0", "--no-backup-if-mismatch",
               "-p1", "-i", str(adapted_patch)]
    subprocess.run(command, cwd=working, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
    files = inventory(working)
    if files.keys() != original.keys():
        raise ContractError("Autopoint archive patch added or removed files")
    changed = sorted(name for name in files.keys() | original.keys() if files.get(name) != original.get(name))
    if not changed:
        raise ContractError("Autopoint archive patch changed no files")
    replacement = archive.with_suffix(".prepared.tar")
    with tarfile.open(replacement, "x", format=tarfile.PAX_FORMAT) as target:
        for path in sorted(working.rglob("*")):
            info = target.gettarinfo(path, arcname=path.relative_to(working).as_posix())
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            if path.is_file():
                with path.open("rb") as stream:
                    target.addfile(info, stream)
            else:
                target.addfile(info)
    with tarfile.open(replacement) as rebuilt:
        if {member.name.rstrip("/") for member in rebuilt.getmembers()} != seen:
            raise ContractError("Repacked autopoint archive member set differs")
    replacement.replace(archive)
    return {"operation": "pinned-autopoint-archive-patch", "before_sha256": before,
            "after_sha256": digest(archive), "patch_sha256": patch_sha, "command": command,
            "adapted_patch_sha256": digest(adapted_patch), "adapted_contexts": adaptations,
            "archive_member_count": len(seen),
            "changed_files": changed, "files": files, "archive_metadata": "sorted; uid/gid/mtime=0"}


def materialize_zstd_launchers(root):
    root = Path(root)
    expected = {"tests/cli-tests/bin/unzstd", "tests/cli-tests/bin/zstdcat"}
    links = {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_symlink()}
    target = root / "tests/cli-tests/bin/zstd"
    if set(links) != expected or target.is_symlink() or not target.is_file():
        raise ContractError("Unexpected Zstd source launcher-link layout")
    text = target.read_text(encoding="utf-8")
    if ('zstdname=$(basename $0)' not in text or '"$ZSTD_SYMLINK_DIR/$zstdname"' not in text or
            any(os.readlink(path) != "zstd" or path.resolve() != target.resolve() for path in links.values())):
        raise ContractError("Zstd launcher aliases no longer preserve invocation-basename dispatch")
    sha = digest(target)
    records = []
    for name, path in sorted(links.items()):
        path.unlink()
        shutil.copy2(target, path)
        if digest(path) != sha or digest(target) != sha:
            raise ContractError("Zstd source launcher bytes changed during explicit alias export")
        records.append({"path": name, "original_type": "internal-symbolic-link", "target": "zstd",
                        "operation": "materialize-identical-launcher-bytes", "sha256": sha,
                        "scope": "Source launcher alias only; runtime symlink capability is not inferred"})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=RECIPES, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--libtool-generator", type=Path,
                        help="Verified portable MSYS-aware libtool generator copy")
    parser.add_argument("--windows-launcher-aliases", action="store_true",
                        help="Zstd only: explicitly materialize its two basename-dispatched source launchers")
    args = parser.parse_args()
    if sys.platform != "linux" or args.output.exists():
        raise ContractError("Linux source generation and a fresh output are required")
    if args.windows_launcher_aliases and args.package != "zstd":
        raise ContractError("Windows launcher materialization is supported only for the exact Zstd source aliases")
    if args.package in ("libxcrypt", "libiconv-msys", "libedit", "gettext-msys", "heimdal", "db", "file", "xz") and args.libtool_generator is None:
        raise ContractError("Shared MSYS libraries require the explicit MSYS-aware libtool generator")
    settings = RECIPES[args.package]
    source_id = settings.get("source_id", args.package)
    source = args.sources / source_id
    manifest = args.sources / f"{source_id}.inventory.json"
    recipes = args.sources / settings.get("recipe_collection", "msys-upstream-recipes")
    verify_tree(source, manifest)
    verify_tree(recipes, recipes.with_name(recipes.name + ".inventory.json"))
    identity = json.loads(manifest.read_text())
    recipe = recipes / settings.get("recipe_name", args.package) / "PKGBUILD"
    recipe_text = recipe.read_text()
    if (identity["source"]["id"] != source_id or identity["source"]["version"] != settings["version"]
            or identity["source"]["sha256"] not in recipe_text):
        raise ContractError("Source does not match the pinned MSYS package recipe")
    shutil.copytree(source, args.output, symlinks=True)
    steps = []
    environment = {name: os.environ[name] for name in ("PATH", "HOME", "LANG", "LC_ALL") if name in os.environ}
    libtool_dependency = None
    if args.libtool_generator:
        host_receipt = args.libtool_generator.with_name(args.libtool_generator.name + ".copy.json")
        verify_tree(args.libtool_generator, host_receipt)
        host = json.loads(host_receipt.read_text())
        if (host.get("status") != "byte-identical-msys-libtool-generator" or
                host.get("package_version") != "2.6.2-1"):
            raise ContractError("Unexpected libtool generator receipt")
        environment["PATH"] = str(args.libtool_generator / "bin") + os.pathsep + environment.get("PATH", "")
        environment["LIBTOOLIZE"] = str(args.libtool_generator / "bin/libtoolize")
        environment["_lt_pkgdatadir"] = str(args.libtool_generator / "generator-data")
        environment["ACLOCAL_PATH"] = str(args.libtool_generator / "generator-data/m4")
        libtool_dependency = {"prefix": str(args.libtool_generator), "manifest_sha256": digest(host_receipt)}
    macro_dependency = None
    if args.package == "nano":
        macros = args.sources / "pkgconf"
        macro_manifest = args.sources / "pkgconf.inventory.json"
        verify_tree(macros, macro_manifest)
        environment["ACLOCAL_PATH"] = os.pathsep.join(filter(None, (environment.get("ACLOCAL_PATH"), str(macros))))
        macro_dependency = {"manifest_sha256": digest(macro_manifest),
                            "pkg_m4_sha256": digest(macros / "pkg.m4")}
    with args.output.with_name(args.output.name + ".prepare.log").open("x") as log:
        for step in settings["steps"]:
            working_directory = args.output
            if step[0] in ("patch", "local-patch", "source-patch"):
                local = step[0] == "local-patch"
                source_patch_manifest = None
                if step[0] == "source-patch":
                    source_patch_root = args.sources / step[1]
                    source_patch_manifest = args.sources / f"{step[1]}.inventory.json"
                    verify_tree(source_patch_root, source_patch_manifest)
                    path = source_patch_root / step[1]
                else:
                    path = (Path(__file__).resolve().parent / "patches" if local else recipe.parent) / step[1]
                upstream_sha = None if local else digest(path)
                if not local and upstream_sha not in recipe_text:
                    raise ContractError("Package patch hash is not covered by its recipe")
                adapted = None if local else ADAPTED_PATCHES.get((args.package, step[1]))
                if adapted:
                    path = Path(__file__).resolve().parent / "patches" / adapted
                elif not local and (args.package, step[1]) in PATCH_CONTEXTS:
                    text = adapt_package_context((args.package, step[1]), path.read_text())
                    patch_directory = args.output.with_name(args.output.name + ".patch-inputs")
                    patch_directory.mkdir(exist_ok=True)
                    path = patch_directory / step[1]
                    path.write_text(text, newline="\n")
                    adapted = "strict-current-context-only"
                command = ["patch", "--batch", "--forward", "--fuzz=0", "--no-backup-if-mismatch",
                           f"-p{step[2]}", "-i", str(path)]
                record = {"patch_sha256": digest(path), "upstream_patch_sha256": upstream_sha,
                          "adaptation": adapted, "local_port_patch": local,
                          "source_patch_manifest_sha256": digest(source_patch_manifest) if source_patch_manifest else None}
            elif step[0] == "copy-resource":
                path = recipe.parent / step[1]
                sha = digest(path)
                if sha not in recipe_text:
                    raise ContractError("Package resource is not checksum-pinned")
                destination = args.output / "msys2-package" / step[1]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                if digest(destination) != sha:
                    raise ContractError("Package resource changed during copy")
                steps.append({"operation": "copy-pinned-package-resource", "name": step[1], "sha256": sha})
                continue
            elif step[0] == "local-file":
                path = Path(__file__).parent / step[1]
                destination = args.output / step[2]
                if destination.exists():
                    raise ContractError("Local build helper would overwrite an existing source file")
                sha = digest(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                if digest(path) != sha or digest(destination) != sha:
                    raise ContractError("Local build helper changed during source preparation")
                steps.append({"operation": "copy-local-build-helper", "source": step[1],
                              "destination": step[2], "sha256": sha})
                continue
            elif step[0] == "generate":
                command = list(step[1:])
                record = {}
            elif step[0] == "generate-in":
                working_directory = args.output / step[1]
                command = list(step[2:])
                record = {}
            elif step[0] == "copy-macros":
                copied = []
                for path in sorted((args.output / step[1]).glob("*")):
                    if path.is_file() and not path.name.startswith("."):
                        target = args.output / step[2] / path.name
                        shutil.copyfile(path, target)
                        copied.append({"path": target.relative_to(args.output).as_posix(), "sha256": digest(target)})
                if not copied:
                    raise ContractError("Pinned macro-copy step had no input files")
                steps.append({"operation": "copy-vendored-macros", "files": copied})
                continue
            elif step[0] == "autopoint-archive":
                steps.append(prepare_autopoint_archive(args.output, recipe.parent / step[1],
                                                       recipe_text, environment, log))
                continue
            else:
                path = args.output / "tests/init.sh"
                original = "case $perms in drwx--[-S]---*"
                replacement = "case $perms in drwx*"
                text = path.read_text()
                before = digest(path)
                if text.count(original) == 1:
                    path.write_text(text.replace(original, replacement))
                    operation = "pinned-MSYS-permission-test-adjustment"
                elif text.count("case $perms in drwx------*)") == 1:
                    operation = "pinned-recipe-substitution-is-noop-retain-strict-permission-test"
                else:
                    raise ContractError("Unexpected grep permission-test source shape")
                steps.append({"operation": operation,
                              "before_sha256": before, "after_sha256": digest(path)})
                continue
            result = subprocess.run(command, cwd=working_directory, env=environment, stdout=log, stderr=subprocess.STDOUT)
            steps.append({**record, "command": command, "cwd": str(working_directory), "exit": result.returncode})
            if result.returncode:
                raise ContractError(f"Source preparation failed: {command}; failed tree/log retained")
        for configure in args.output.rglob("configure"):
            if configure.is_file():
                command = ["bash", "-n", str(configure)]
                result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
                if result.returncode:
                    raise ContractError("Generated configure is not valid shell; missing macros must not be accepted")
                steps.append({"command": command, "exit": result.returncode})
    windows_aliases = materialize_zstd_launchers(args.output) if args.windows_launcher_aliases else []
    identity.update({"scope": "prepared MSYS-target sources, not built",
                     "original_manifest_sha256": digest(manifest), "recipe_sha256": digest(recipe),
                     "recipe_manifest_sha256": digest(recipes.with_name(recipes.name + ".inventory.json")),
                     "dependencies": settings["dependencies"], "steps": steps,
                     "package_version": settings.get("package_version", settings["version"]),
                     "build_policy": settings.get("build_policy"),
                     "macro_dependency": macro_dependency,
                     "libtool_dependency": libtool_dependency,
                     "windows_source_aliases": windows_aliases,
                     "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes",
                     "files": inventory(args.output)})
    if args.libtool_generator:
        verify_tree(args.libtool_generator, host_receipt)
    args.output.with_name(args.output.name + ".prepare.json").write_text(json.dumps(identity, indent=2) + "\n")
    print(f"Prepared {args.package} {settings['version']}; {len(identity['files'])} files")


if __name__ == "__main__":
    main()
