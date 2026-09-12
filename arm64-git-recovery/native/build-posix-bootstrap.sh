#!/usr/bin/env bash
# First real POSIX applications, not full-feature distribution packages.
set -euo pipefail

if [[ $# -lt 6 || $# -gt 8 ]]; then
    echo "usage: $0 PACKAGE PREPARED_SOURCE TOOLCHAIN_PREFIX NEW_BUILD_ROOT APPROVED_JOBS|check RUNTIME_HELLO_RECEIPT [PROFILE [DEPENDENCY_STAGE]]" >&2
    exit 2
fi
package=$1 source_root=$2 toolchain=$3 build_root=$4 jobs=$5 runtime_receipt=$6
profile=${7:-default}
dependencies=${8:-}
[[ $profile == default || ($package == ncurses && $profile == ncurses-c-bootstrap) ||
   ($package == nano && $profile == native-editor-bootstrap && -n $dependencies) ]] || {
    echo "Unknown package profile" >&2; exit 2;
}
case "$package" in make|bash|coreutils|sed|grep|gawk|findutils|ncurses|nano) ;; *) echo "Unsupported bootstrap package: $package" >&2; exit 2 ;; esac
[[ $package != nano || $profile == native-editor-bootstrap ]] || { echo "Nano requires an explicit dependency-bound profile" >&2; exit 2; }
[[ $jobs == check || $jobs =~ ^[1-9][0-9]*$ ]] || { echo "Explicit approved job count or check required" >&2; exit 2; }
[[ ! -e $build_root ]] || { echo "Refusing existing build root: $build_root" >&2; exit 2; }
source_root=$(realpath "$source_root")
toolchain=$(realpath "$toolchain")
runtime_receipt=$(realpath "$runtime_receipt")
target=aarch64-pc-cygwin
cc="$toolchain/bin/msys2-gcc"
cxx="$toolchain/bin/msys2-g++"
for tool in "$cc" "$cxx" "$toolchain/bin/$target-ar" "$toolchain/bin/$target-ranlib"; do
    [[ -x $tool ]] || { echo "Missing cross tool: $tool" >&2; exit 3; }
done
[[ $("$cc" -dumpmachine) == "$target" ]] || { echo "Wrong compiler target" >&2; exit 3; }
for input in "$toolchain/$target/include/sys/cygwin.h" \
             "$toolchain/$target/lib/libmsys-2.0.a" "$toolchain/bin/msys-2.0.dll"; do
    [[ -s $input ]] || { echo "Runtime boundary not ready: $input" >&2; exit 3; }
done
for tool in python3 make; do
    command -v "$tool" >/dev/null || { echo "Missing host tool: $tool (contact bootstrap owner)" >&2; exit 3; }
done
script_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_root/runtime_readiness.py" \
    --receipt "$runtime_receipt" --prefix "$toolchain"
"$cc" -std=gnu11 -Werror -fsyntax-only "$script_root/fixtures/msys-jmp-layout.c"
PYTHONDONTWRITEBYTECODE=1 python3 - "$script_root" "$source_root" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from sources import verify_tree
root = Path(sys.argv[2])
verify_tree(root, root.with_name(root.name + ".prepare.json"))
PY
if [[ $jobs == check ]]; then
    echo "Bootstrap inputs present; no configure or compilation requested."
    exit 0
fi
mkdir -p "$build_root"
build_root=$(realpath "$build_root")
cp -a "$source_root" "$build_root/source"
mkdir "$build_root/build" "$build_root/stage"
if [[ $package == bash ]]; then
    build_directory="$build_root/source"
else
    build_directory="$build_root/build"
fi
export CC="$cc" CXX="$cxx" AR="$toolchain/bin/$target-ar" RANLIB="$toolchain/bin/$target-ranlib"
export CPPFLAGS=-D__MSYS__
export CFLAGS="-O2 -g"
export LDFLAGS="-Wl,--no-insert-timestamp"
if [[ $package == nano ]]; then
    dependencies=$(realpath "$dependencies")
    [[ -s "$dependencies/usr/include/ncursesw/ncurses.h" && -s "$dependencies/usr/lib/libncursesw.dll.a" ]] || {
        echo "Missing native curses development dependency" >&2; exit 3;
    }
    cmp "$dependencies/usr/bin/msys-2.0.dll" "$toolchain/bin/msys-2.0.dll"
    export CPPFLAGS="$CPPFLAGS -I$dependencies/usr/include -I$dependencies/usr/include/ncursesw"
    export LDFLAGS="$LDFLAGS -L$dependencies/usr/lib"
    export PKG_CONFIG_LIBDIR="$dependencies/usr/lib/pkgconfig" PKG_CONFIG_SYSROOT_DIR="$dependencies"
fi
export LC_ALL=C
unset CONFIG_SITE
exec > >(tee "$build_root/build.log") 2>&1
echo "classification=bootstrap; build_host=linux-aarch64-cross; target=$target; approved_jobs=$jobs"
sha256sum "$runtime_receipt"
sha256sum "$cc" "$toolchain/$target/lib/libmsys-2.0.a" "$toolchain/bin/msys-2.0.dll"
PYTHONDONTWRITEBYTECODE=1 python3 - "$script_root" "$build_root" "$source_root" "$runtime_receipt" "$package" "$jobs" "$build_directory" "$profile" "$dependencies" <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from sources import digest, inventory
build_root, source_root, receipt = map(Path, sys.argv[2:5])
record = {
    "schema": 1, "package": sys.argv[5], "approved_jobs": int(sys.argv[6]),
    "classification": "bootstrap", "build_host": "linux-aarch64-cross",
    "target": "aarch64-pc-cygwin",
    "build_directory": sys.argv[7],
    "profile": sys.argv[8],
    "dependencies": {"path": sys.argv[9], "files": inventory(sys.argv[9])} if sys.argv[9] else None,
    "runtime_receipt": {"path": str(receipt), "sha256": digest(receipt)},
    "prepared_source": {"path": str(source_root),
                        "manifest_sha256": digest(source_root.with_name(source_root.name + ".prepare.json"))},
    "tools": {name: {"path": os.environ[name], "sha256": digest(os.environ[name])}
              for name in ("CC", "CXX", "AR", "RANLIB")},
    "flags": {name: os.environ[name] for name in ("CPPFLAGS", "CFLAGS", "LDFLAGS")}
}
with (build_root / "build-inputs.json").open("x", encoding="utf-8") as output:
    json.dump(record, output, indent=2)
    output.write("\n")
PY
if [[ $package == bash ]]; then
    command -v autoconf >/dev/null || { echo "Missing host autoconf; contact bootstrap owner" >&2; exit 3; }
    (cd "$build_root/source" && autoconf)
fi
cd "$build_directory"
case "$package" in
    make|coreutils|sed|grep|gawk|findutils) config_guess="$build_root/source/build-aux/config.guess" ;;
    bash) config_guess="$build_root/source/support/config.guess" ;;
    ncurses|nano) config_guess="$build_root/source/config.guess" ;;
esac
[[ -f $config_guess ]] || { echo "Missing build-host detection script: $config_guess" >&2; exit 3; }
build=$(sh "$config_guess")
flags=(--build="$build" --host="$target" --prefix=/usr --disable-nls)
if [[ $package == ncurses ]]; then
    flags=(--build="$build" --host=aarch64-pc-msys --prefix=/usr
           --without-ada --with-shared --with-cxx-shared --with-normal --without-debug
           --disable-relink --disable-rpath --with-ticlib --without-termlib --enable-widec
           --enable-ext-colors --enable-ext-mouse --enable-sp-funcs --with-wrap-prefix=ncwrap_
           --enable-sigwinch --disable-term-driver --enable-colorfgbg --enable-tcap-names
           --disable-termcap --disable-mixed-case --with-pkg-config --enable-pc-files
           --with-manpage-format=normal --with-manpage-aliases --with-default-terminfo-dir=/usr/share/terminfo
           --enable-echo --mandir=/usr/share/man --includedir=/usr/include/ncursesw
           --with-build-cflags=-D_XOPEN_SOURCE_EXTENDED --with-pkg-config-libdir=/usr/lib/pkgconfig)
    if [[ $profile == ncurses-c-bootstrap ]]; then
        flags+=(--without-cxx --without-cxx-binding --without-cxx-shared)
    fi
elif [[ $package == make ]]; then
    flags+=(--without-guile --without-libintl-prefix --without-libiconv-prefix --disable-posix-spawn)
elif [[ $package == bash ]]; then
    flags+=(--disable-readline --without-bash-malloc --sysconfdir=/etc --localstatedir=/var)
elif [[ $package == sed ]]; then
    flags+=(--without-libintl-prefix --without-libiconv-prefix gl_cv_have_weak=no)
elif [[ $package == grep ]]; then
    flags+=(--without-libintl-prefix --without-libiconv-prefix --disable-perl-regexp gl_cv_have_weak=no)
elif [[ $package == gawk ]]; then
    flags+=(--libexecdir=/usr/lib --without-libintl-prefix --without-libiconv-prefix
            --without-mpfr --without-readline gl_cv_have_weak=no)
elif [[ $package == findutils ]]; then
    flags+=(--without-libintl-prefix --without-libiconv-prefix 'DEFAULT_ARG_SIZE=(32u*1024)')
elif [[ $package == nano ]]; then
    flags+=(--sysconfdir=/etc --enable-color --enable-nanorc --enable-utf8)
else
    flags+=(--without-gmp --without-libintl-prefix --without-libiconv-prefix
            --libexecdir=/usr/lib --sysconfdir=/etc --localstatedir=/var
            --program-transform-name=s/kill/gkill/
            --enable-install-program=arch,hostname --enable-no-install-program=uptime
            gl_cv_have_weak=no gl_cv_func_strtod_works=yes gl_cv_func_strtold_works=yes)
fi
"$build_root/source/configure" "${flags[@]}"
make_args=()
if [[ $package == bash ]]; then
    make_args+=('LOCAL_LDFLAGS=-Wl,--export-all,--out-implib,libbash.dll.a'
                'LDFLAGS_FOR_BUILD=$(CFLAGS_FOR_BUILD)'
                "SHOBJ_LIBS=$build_directory/libbash.dll.a")
fi
make -j"$jobs" "${make_args[@]}"
make -j1 "${make_args[@]}" DESTDIR="$build_root/stage" install
if [[ $package == bash ]]; then
    cp "$build_root/stage/usr/bin/bash.exe" "$build_root/stage/usr/bin/sh.exe"
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$script_root/package_posix.py" \
    --package "$package" --source "$build_root/source" --stage "$build_root/stage" --build "$build_directory"
if [[ $package == coreutils ]]; then
    required=(cat cp env mkdir mv printf rm sort stat)
elif [[ $package == findutils ]]; then
    required=(find xargs)
elif [[ $package == ncurses ]]; then
    required=(tic infocmp tput)
else
    required=("$package")
fi
for program in "${required[@]}"; do
    [[ -s "$build_root/stage/usr/bin/$program.exe" ]] || { echo "Missing executable: $program" >&2; exit 4; }
done
cp "$toolchain/bin/msys-2.0.dll" "$build_root/stage/usr/bin/"
find "$build_root/stage" -type f -print0 | sort -z | xargs -0 sha256sum > "$build_root/SHA256SUMS"
PYTHONDONTWRITEBYTECODE=1 python3 - "$script_root" "$build_root" "$toolchain" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runtime_readiness import verify
from sources import ContractError, digest, inventory, verify_tree
build_root, toolchain = map(Path, sys.argv[2:4])
record = json.loads((build_root / "build-inputs.json").read_text())
receipt = record["runtime_receipt"]
if verify(receipt["path"], toolchain) != receipt["sha256"]:
    raise ContractError("Runtime readiness receipt changed during build")
for name, tool in record["tools"].items():
    if digest(tool["path"]) != tool["sha256"]:
        raise ContractError(f"{name} changed during build")
source = Path(record["prepared_source"]["path"])
manifest = source.with_name(source.name + ".prepare.json")
if digest(manifest) != record["prepared_source"]["manifest_sha256"]:
    raise ContractError("Prepared source manifest changed during build")
verify_tree(source, manifest)
limitations = ["NLS disabled"]
if record["package"] == "ncurses":
    limitations = ["Linux-hosted cross build; native terminal and C/C++ library behavior pending"]
    if record["profile"] == "ncurses-c-bootstrap":
        limitations.append("C-only editor bootstrap; C++ binding absent and full package admission pending")
if record["package"] == "bash":
    limitations.append("Bash readline disabled")
elif record["package"] == "coreutils":
    limitations.append("GMP disabled")
elif record["package"] == "grep":
    limitations.append("PCRE1 support disabled in bootstrap")
elif record["package"] == "gawk":
    limitations.extend(["MPFR/GMP disabled in bootstrap", "Readline disabled in bootstrap"])
elif record["package"] == "nano":
    limitations.append("Explicit editor bootstrap; NLS/full package dependency admission pending")
else:
    limitations.append("Requires a real shell at execution time")
dependency = record.get("dependencies")
if dependency and inventory(dependency["path"]) != dependency["files"]:
    raise ContractError("Native dependency changed during build")
record.update({
    "status": "built-not-run", "files": inventory(build_root / "stage"),
    "config_log_sha256": digest(Path(record["build_directory"]) / "config.log"),
    "limitations": limitations,
    "pending": ["raw-native-ARM64-PE", "native-process", "loaded-runtime-path", "functional-behavior"]
})
with (build_root / "build-evidence.json").open("x", encoding="utf-8") as output:
    json.dump(record, output, indent=2)
    output.write("\n")
PY
printf '%s\n' \
    'status=built-not-run' \
    'classification=bootstrap' \
    'build_host=linux-aarch64-cross' \
    'NLS disabled; Bash readline disabled; coreutils GMP disabled. Not a full distribution package.' \
    'Runtime import closure, raw ARM64 PE and native behavior gates remain mandatory.' \
    > "$build_root/BUILD-STATUS.txt"
