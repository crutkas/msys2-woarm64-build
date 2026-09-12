#!/usr/bin/env bash
set -euo pipefail
[[ $# == 3 ]] || exit 2
package=$1 root=$(cygpath -u "$2") output=$(cygpath -u "$3")
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tc=/c/ag-e138920f/tc-cpp-guard-01
if [[ $package == readline ]]; then
    dependency=/c/ag-readline-e138-01/ncurses-01/stage
    patch_file=readline-8.3-history-example-link.patch
else
    [[ $package == libedit ]] || exit 2
    dependency=/c/ag-readline-e138-01/ncurses-static-cxx-01/stage
    patch_file=libedit-20240808-read-ioctl.patch
fi
native_python=$(cygpath -u "$WOARM64_NATIVE_PYTHON")
native_driver=$(cygpath -u "$WOARM64_NATIVE_DRIVER_ROOT")
export PATH="$dependency/usr/bin:$tc/bin:/usr/bin" LC_ALL=C MSYSTEM=CYGWIN
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export MAKEFLAGS=-j1 MFLAGS=-j1 OMP_NUM_THREADS=1 WOARM64_NATIVE_ARG_CONVERSION=none
export TERMINFO="$dependency/usr/share/terminfo"
/usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch \
    -p1 -d "$root/source" -i "$here/patches/$patch_file"
if [[ $package == readline ]]; then
    cd "$root/build/shared"
    ./config.status --file=examples/Makefile
    export PATH="$PWD/shlib:$PATH"
    make -C examples -j1 all READLINE_LIB=../shlib/msys-readline8.dll.a HISTORY_LIB=../shlib/msys-history8.dll.a
    make -C examples -j1 check READLINE_LIB=../shlib/msys-readline8.dll.a HISTORY_LIB=../shlib/msys-history8.dll.a
    "$native_python" -I "$native_driver/native-target-exec.py" "$(cygpath -m "$PWD/examples/rlversion.exe")"
    make -j1 DESTDIR="$root/stage" install
    install -Dm644 "$root/source/msys2-package/inputrc" "$root/stage/etc/inputrc"
else
    cd "$root/build"
    export PATH="$PWD/src/.libs:$PATH"
    grep -qx '#define HAVE_SYS_IOCTL_H 1' config.h
    make -j1
    make -j1 check
    make -j1 DESTDIR="$root/stage" install
fi
install -Dm644 "$root/source/COPYING" "$root/stage/usr/share/licenses/$package/LICENSE"
