#!/usr/bin/env bash
set -euo pipefail
[[ $# == 6 ]] || { echo "usage: $0 tcl|tk OUTPUT TOOLCHAIN DEPENDENCY PATCH JOBS" >&2; exit 2; }
export PATH=/usr/bin
package=$1 output=$(cygpath -au "$2") toolchain=$(cygpath -au "$3")
dependency=$(cygpath -au "$4") patch_file=$(cygpath -au "$5") jobs=$6
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo "Explicit job allocation required" >&2; exit 2; }
export PATH="$toolchain/bin:$dependency/bin:/usr/bin"
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib RC=windres
export LC_ALL=C HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
mkdir -p "$HOME" "$TMPDIR" "$output/build" "$output/stage"
[[ $(gcc -dumpmachine) == aarch64-w64-mingw32 ]] || { echo "Wrong compiler target" >&2; exit 3; }
options=(--build=aarch64-w64-mingw32 --host=aarch64-w64-mingw32
         --prefix="$(cygpath -m "$output/stage")" --enable-64bit=arm64 --enable-threads)
make_args=('SHELL=/bin/bash -e' 'INSTALL=/usr/bin/install -c')
if [[ $package == tcl ]]; then
    (cd "$output/source" && patch --batch --forward --fuzz=0 -p1 -i "$patch_file")
    dep_native=$(cygpath -m "$dependency")
    make_args+=("ZLIB_LIBS=$dep_native/lib/libz.dll.a"
                "ZLIB_DIR_NATIVE=$dep_native/include"
                "ZLIB_EXTERNAL_DIR=$dependency/bin" "ZLIB_DLL_FILE=libz.dll")
elif [[ $package == tk ]]; then
    options+=("--with-tcl=$dependency/lib")
else
    echo "Unsupported interpreter package" >&2
    exit 2
fi
cd "$output/build"
"$output/source/win/configure" "${options[@]}"
make -j"$jobs" "${make_args[@]}"
if [[ $package == tcl ]]; then
    make -j"$jobs" "${make_args[@]}" tcltest
    make -j1 "${make_args[@]}" test-tcl \
        'TESTFLAGS=-file "basic.test expr.test dict.test list.test regexp.test encoding.test zlib.test"'
fi
make -j1 "${make_args[@]}" install
if [[ $package == tcl ]]; then
    cp "$output/stage/bin/tclsh86.exe" "$output/stage/bin/tclsh.exe"
else
    cp "$output/stage/bin/wish86.exe" "$output/stage/bin/wish.exe"
fi
mkdir -p "$output/stage/share/licenses/$package"
cp "$output/source/license.terms" "$output/stage/share/licenses/$package/"
