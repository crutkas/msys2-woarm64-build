#!/usr/bin/env bash
set -euo pipefail
root=$(/usr/bin/cygpath.exe -u "$1")
phase=${2:-all}
case "$phase" in all|configure|resume|check|install) ;; *) echo "Unsupported GDBM phase: $phase" >&2; exit 2 ;; esac
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
host_path="$root/host-target-runtime/usr/bin:$root/bootstrap/usr/bin:$root/compiler/bin"
export PATH="$host_path"
export LC_ALL=C MAKEFLAGS=-j2 MFLAGS=-j2
unset MSYS2_ARG_CONV_EXCL GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH CONFIG_SITE
export MSYS2_ARG_CONV_EXCL='-D;../'
export CONFIG_SHELL="$root/bootstrap/usr/bin/bash.exe"
export CC="$root/compiler/bin/gcc.exe" CXX="$root/compiler/bin/g++.exe"
export AR="$root/compiler/bin/ar.exe" RANLIB="$root/compiler/bin/ranlib.exe"
export NM="$root/compiler/bin/nm.exe" OBJDUMP="$root/compiler/bin/objdump.exe" LD="$root/compiler/bin/ld.exe"
export STRIP="$root/compiler/bin/strip.exe"
export CFLAGS="-O2 -g -fstack-protector-strong"
export CPPFLAGS="-I$root/dependencies/usr/include"
export LDFLAGS="-L$root/dependencies/usr/lib -Wl,--no-insert-timestamp"
export CONFIG_SITE=/dev/null
export MAKE="$root/bootstrap/usr/bin/make.exe"
if [[ "$phase" == all || "$phase" == configure ]]; then
"$CC" -dumpmachine | tee "$root/logs/compiler-target.txt"
"$CC" -dM -E -x c /dev/null > "$root/logs/compiler-macros.txt"
grep -qx '#define __MSYS__ 1' "$root/logs/compiler-macros.txt"
grep -qx '#define __SIZEOF_LONG__ 8' "$root/logs/compiler-macros.txt"
"$CC" -### -x c /dev/null -o "$root/temp/link-intent.exe" 2> "$root/logs/compiler-link-intent.txt"
grep -q -- '-lmsys-2.0' "$root/logs/compiler-link-intent.txt"
cd "$root/build"
"$CONFIG_SHELL" ../source/configure --prefix=/usr --build=aarch64-pc-cygwin \
    --enable-libgdbm-compat COMPATINCLUDEDIR=/usr/include/gdbm \
    --with-libiconv-prefix="$root/dependencies/usr" --with-libintl-prefix="$root/dependencies/usr"
else
cd "$root/build"
fi
grep -q '^#define ENABLE_NLS 1' autoconf.h || { echo "Required NLS was not enabled" >&2; exit 1; }
grep -q '^#define WITH_READLINE 1' autoconf.h || { echo "Required GNU Readline was not enabled" >&2; exit 1; }
grep -q '^MAYBE_COMPAT = compat' Makefile || { echo "GDBM compatibility library missing" >&2; exit 1; }
if [[ "$phase" == configure ]]; then
    exit 0
fi
if [[ "$phase" == all || "$phase" == resume ]]; then
    "$MAKE" -j2 MAKE="$MAKE" SHELL="$CONFIG_SHELL"
    "$MAKE" -j2 MAKE="$MAKE" SHELL="$CONFIG_SHELL" -C tests \
        --eval='.SECONDEXPANSION:' \
        --eval='woarm64-check-programs: $$(check_PROGRAMS)' woarm64-check-programs
fi
if [[ "$phase" != install ]]; then
    (
        export PATH="$root/build-runtime/usr/bin:$root/compiler/bin:$root/bootstrap/usr/bin"
        export CONFIG_SHELL="$root/build-runtime/usr/bin/bash.exe"
        export SHELL="$CONFIG_SHELL"
        cd tests
        "$CONFIG_SHELL" "$root/source/tests/testsuite"
    )
fi
if [[ "$phase" != check ]]; then
    "$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" DESTDIR="$root/stage" install
fi
