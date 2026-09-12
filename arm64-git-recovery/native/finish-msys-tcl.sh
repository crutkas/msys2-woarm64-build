#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 ]] || { echo "usage: finish-msys-tcl.sh BUILD_ROOT OUTPUT TOOLCHAIN ZLIB JOBS" >&2; exit 2; }
export PATH=/usr/bin
old=$(cygpath -au "$1")
output=$(cygpath -au "$2")
toolchain=$(cygpath -au "$3")
zlib=$(cygpath -au "$4")
jobs=$5
[[ $jobs == 1 || $jobs == 2 ]] || exit 2
export PATH="$toolchain/bin:$zlib/usr/bin:$old/build:/usr/bin"
export LC_ALL=C MSYSTEM=CYGWIN
export HOME="$output/home" USERPROFILE="$output/home"
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export MAKEFLAGS="-j$jobs" OMP_NUM_THREADS=1
mkdir -p "$HOME" "$TMPDIR" "$output/stage"
cd "$old/build"
make -j"$jobs" 'SHELL=/bin/bash -e' tcltest.exe
make -j1 'SHELL=/bin/bash -e' 'INSTALL=/usr/bin/install -c' INSTALL_ROOT="$output/stage" install install-private-headers
install -Dm644 libtcl8.6.dll.a "$output/stage/usr/lib/libtcl8.6.dll.a"
install -Dm644 "$old/source/license.terms" "$output/stage/usr/share/licenses/tcl/LICENSE"
install -Dm644 "$old/source/unix/tcl.m4" "$output/stage/usr/share/aclocal/tcl.m4"
