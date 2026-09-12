#!/usr/bin/env bash
set -euo pipefail
[[ $# == 3 ]] || exit 2
root=$(cygpath -u "$1") build=$(cygpath -u "$2") source=$(cygpath -u "$3")
win=$(cygpath -m "$1")
driver="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$root/tcl/usr/bin:$root/readline/usr/bin:$root/ncurses/usr/bin:$root/zlib/usr/bin:$root/compiler/bin:$root/bootstrap/usr/bin"
export MSYSTEM=CYGWIN LC_ALL=C CCACHE=none CCACHE_DISABLE=1 CONFIG_SITE=/dev/null
export CC="$win/compiler/bin/gcc.exe" CXX="$win/compiler/bin/g++.exe"
export CC_FOR_BUILD="$CC"
export AR="$win/compiler/bin/ar.exe" RANLIB="$win/compiler/bin/ranlib.exe"
export TMP="$win/temp" TEMP="$win/temp" TMPDIR="$win/temp"
export TCLSH="$root/tcl/usr/bin/tclsh8.6.exe" TCL_LIBRARY="$root/tcl/usr/lib/tcl8.6"
export TCLLIBPATH="$build $root/tcl/usr/lib" TCLLIBDIR=/usr/lib/sqlite3.53.4
export SQLITE_TEST_TCL_CONFIG="$root/tcl-config-hostwin/tclConfig.sh"
export SQLITE_TEST_BUILD=aarch64-pc-cygwin autosetup_tclsh="$root/host-jim-01/jimsh.exe"
export LDFLAGS="-Wl,--no-insert-timestamp -L$win/zlib/usr/lib -L$win/readline/usr/lib -L$win/ncurses/usr/lib -L$win/tcl/usr/lib"
export CPPFLAGS="-I$win/zlib/usr/include -I$win/readline/usr/include -I$win/ncurses/usr/include/ncursesw"
# The runner deliberately overrides CFLAGS for All-O0/All-Debug. Preserve
# private header search paths in its supported extra OPTS without changing
# any of those upstream feature or instrumentation settings.
export OPTS="$CPPFLAGS"
export MAKEFLAGS="-j1 B.tclsh=$driver/sqlite-native-tcl-script.sh TCLSH_CMD=$driver/sqlite-native-tcl-script.sh TCL_CONFIG_SH=$root/tcl-config-hostwin/tclConfig.sh"
export MFLAGS=-j1 OMP_NUM_THREADS=1 CMAKE_BUILD_PARALLEL_LEVEL=1
unset MSYS2_ARG_CONV_EXCL
export MSYS2_ENV_CONV_EXCL='TCLSH;TCL_LIBRARY;TCLLIBPATH;TCLLIBDIR;SQLITE_TEST_TCL_CONFIG;SQLITE_TEST_SHELL_INIT;SQLITE_TEST_EXIT_DIR;SQLITE_TEST_VERBOSE_DIR;autosetup_tclsh'
cd "$build"
make -j1 "TOP=$source" "TSTRNNR_OPTS=--jobs 1" quicktest
