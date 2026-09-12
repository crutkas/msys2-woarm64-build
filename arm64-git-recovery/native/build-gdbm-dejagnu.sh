#!/usr/bin/env bash
set -euo pipefail
root=$(/usr/bin/cygpath.exe -u "$1")
export PATH="$root/host-target-runtime/usr/bin:$root/bootstrap/usr/bin:$root/compiler/bin"
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export LC_ALL=C MAKEFLAGS=-j1 MFLAGS=-j1
export CONFIG_SHELL="$root/bootstrap/usr/bin/bash.exe"
export MAKE="$root/bootstrap/usr/bin/make.exe"
export CC="$root/compiler/bin/gcc.exe" CXX="$root/compiler/bin/g++.exe"
export CFLAGS="-O2 -g -fstack-protector-strong"
export CXXFLAGS="-O2 -g -fstack-protector-strong"
export LDFLAGS="-Wl,--no-insert-timestamp"
export DEJAGNU=/dev/null
unset MSYS2_ARG_CONV_EXCL CONFIG_SITE
cd "$root/test-tools/dejagnu-build"
"$CONFIG_SHELL" "$root/test-tools/dejagnu-source/dejagnu-1.6.3/configure" \
    --prefix=/usr --exec-prefix=/usr --build=aarch64-pc-cygwin
"$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL"
"$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" DESTDIR="$root/test-tools/dejagnu-stage" install
