#!/usr/bin/env bash
set -euo pipefail
root=$(/usr/bin/cygpath.exe -u "$1")
phase=${2:-all}
export PATH="$root/host-target-runtime/usr/bin:$root/bootstrap/usr/bin:$root/compiler/bin"
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export LC_ALL=C MAKEFLAGS=-j1 MFLAGS=-j1 MSYSTEM=CYGWIN
unset MSYS2_ARG_CONV_EXCL GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH CONFIG_SITE
export MSYS2_ARG_CONV_EXCL=-D
export CONFIG_SHELL="$root/bootstrap/usr/bin/bash.exe"
export MAKE="$root/bootstrap/usr/bin/make.exe"
export CC="$root/compiler/bin/gcc.exe" AR="$root/compiler/bin/ar.exe" RANLIB="$root/compiler/bin/ranlib.exe"
export CFLAGS="-O2 -g -fstack-protector-strong"
export CPPFLAGS="-I$root/test-tools/zlib/usr/include"
export LDFLAGS="-L$root/test-tools/zlib/usr/lib -Wl,--no-insert-timestamp"
windows_root="C:/${root#/c/}"
export TCL_PROVIDER_PREFIX="$windows_root/test-tools/tcl/usr"
export TCL_PROVIDER_ZLIB_PREFIX="$windows_root/test-tools/zlib/usr"
export TCL_PROVIDER_CC="$windows_root/compiler/bin/gcc.exe"
export TCL_PROVIDER_RANLIB="$windows_root/compiler/bin/ranlib.exe"
export TCL_LIBRARY="$root/test-tools/runtime/usr/lib/tcl8.6"
export TCLLIBPATH="$root/test-tools/runtime/usr/lib"
cd "$root/test-tools/expect-build"
if [[ "$phase" == all ]]; then
    "$CONFIG_SHELL" "$root/test-tools/expect-source/expect5.45.4/configure" \
        --prefix=/usr --exec-prefix=/usr --mandir=/usr/share/man --build=aarch64-pc-cygwin \
        --with-tcl="$root/test-tools/tcl/usr/lib" \
        --with-tclinclude="$root/test-tools/tcl/usr/include"
fi
"$MAKE" -k -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" 'SHLIB_LD=$(CC) -shared -Wl,--out-implib,$@.a'
(
    export PATH="$root/test-tools/expect-build:$root/test-tools/runtime/usr/bin:$root/bootstrap/usr/bin"
    export TCLLIBPATH="$root/test-tools/expect-build"
    MSYS2_ARG_CONV_EXCL='*' "$WOARM64_NATIVE_PYTHON" -I \
        "$windows_root/observer/native-target-exec.py" \
        "$windows_root/test-tools/runtime/usr/bin/tclsh8.6.exe" \
        "$root/test-tools/expect-source/expect5.45.4/tests/all.tcl"
)
"$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" \
    DESTDIR="$root/test-tools/expect-stage" install
