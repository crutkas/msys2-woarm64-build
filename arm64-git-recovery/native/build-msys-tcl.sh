#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 ]] || { echo "usage: build-msys-tcl.sh OUTPUT TOOLCHAIN ZLIB PATCH JOBS" >&2; exit 2; }
export PATH=/usr/bin
output=$(cygpath -au "$1")
toolchain=$(cygpath -au "$2")
zlib=$(cygpath -au "$3")
patch_file=$(cygpath -au "$4")
jobs=$5
[[ $jobs == 1 || $jobs == 2 ]] || { echo "An explicit one/two-job allocation is required" >&2; exit 2; }
source="$output/source"
build="$output/build"
stage="$output/stage"
export PATH="$toolchain/bin:$zlib/usr/bin:$build:/usr/bin"
export CC="$toolchain/bin/gcc.exe" CXX="$toolchain/bin/g++.exe"
export AR="$toolchain/bin/ar.exe" RANLIB="$toolchain/bin/ranlib.exe" RC="$toolchain/bin/windres.exe"
export LC_ALL=C MSYSTEM=CYGWIN HOME="$output/home" USERPROFILE="$output/home"
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export MAKEFLAGS="-j$jobs" OMP_NUM_THREADS=1
export CFLAGS="-O2 -g -fstack-protector-strong"
export CPPFLAGS="-D_FORTIFY_SOURCE=2 -I$(cygpath -am "$zlib/usr/include")"
export LDFLAGS="-L$(cygpath -am "$zlib/usr/lib")"
[[ $("$CC" -dumpmachine) == aarch64-pc-cygwin ]] || { echo "MSYS LP64 compiler required" >&2; exit 3; }
mkdir -p "$build" "$stage" "$HOME" "$TMPDIR"
(cd "$source" && patch --batch --forward --fuzz=0 -p2 -i "$patch_file")
for package in itcl4.2.2 tdbc1.1.3 tdbcmysql1.1.3 tdbcodbc1.1.3 tdbcpostgres1.1.3 tdbcsqlite3-1.1.3 thread2.8.7; do
    (cd "$source/pkgs/$package" && autoreconf -fiv)
done
(cd "$source/unix" && autoreconf -fiv)
cd "$build"
"$source/unix/configure" \
    --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
    --prefix=/usr --mandir=/usr/share/man --enable-threads --enable-64bit \
    tcl_cv_strtod_buggy=no tcl_cv_sys_version=CYGWIN_NT
make -j"$jobs" 'SHELL=/bin/bash -e'
make -j"$jobs" 'SHELL=/bin/bash -e' tcltest.exe
# Tcl's install-sh is not errexit-safe; keep strict recipes and use the real GNU installer.
make -j1 'SHELL=/bin/bash -e' 'INSTALL=/usr/bin/install -c' INSTALL_ROOT="$stage" install install-private-headers
install -Dm644 libtcl8.6.dll.a "$stage/usr/lib/libtcl8.6.dll.a"
install -Dm644 "$source/license.terms" "$stage/usr/share/licenses/tcl/LICENSE"
install -Dm644 "$source/unix/tcl.m4" "$stage/usr/share/aclocal/tcl.m4"
