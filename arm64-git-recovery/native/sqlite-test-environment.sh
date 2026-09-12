#!/usr/bin/env bash
# Sourced explicitly by each upstream-owned run.sh, not inherited across
# the native Tcl -> foreign bootstrap environment boundary.
root=/c/ag-sqlite-e138-01
win=C:/ag-sqlite-e138-01
driver="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$root/tcl/usr/bin:$root/readline/usr/bin:$root/ncurses/usr/bin:$root/zlib/usr/bin:$root/compiler/bin:$root/bootstrap/usr/bin"
export MSYSTEM=CYGWIN LC_ALL=C CCACHE=none CCACHE_DISABLE=1 CONFIG_SITE=/dev/null
export HOME="$root/home" TMP="$win/temp" TEMP="$win/temp" TMPDIR="$win/temp"
export CC="$win/compiler/bin/gcc.exe" CXX="$win/compiler/bin/g++.exe"
export CC_FOR_BUILD="$CC" AR="$win/compiler/bin/ar.exe" RANLIB="$win/compiler/bin/ranlib.exe"
export TCLSH="$root/tcl/usr/bin/tclsh8.6.exe" TCL_LIBRARY="$root/tcl/usr/lib/tcl8.6"
export TCLLIBPATH="$root/tcl/usr/lib" TCLLIBDIR=/usr/lib/sqlite3.53.4
export autosetup_tclsh="$root/host-jim-01/jimsh.exe"
export MAKEFLAGS="-j1 B.tclsh=$driver/sqlite-native-tcl-script.sh TCLSH_CMD=$driver/sqlite-native-tcl-script.sh TCL_CONFIG_SH=$root/tcl-config-hostwin/tclConfig.sh"
export MFLAGS=-j1 OMP_NUM_THREADS=1 CMAKE_BUILD_PARALLEL_LEVEL=1
export CPPFLAGS="-I$win/zlib/usr/include -I$win/readline/usr/include -I$win/ncurses/usr/include/ncursesw"
export LDFLAGS="-Wl,--no-insert-timestamp -L$win/zlib/usr/lib -L$win/readline/usr/lib -L$win/ncurses/usr/lib -L$win/tcl/usr/lib"
export WOARM64_NATIVE_PYTHON='C:\Program Files\Python314-arm64\python.exe'
export WOARM64_NATIVE_PYTHON_SHA256=7e402261031efd4524809c57a1759cda1c8ba334fb498184fa13b8ca2bc98c29
export WOARM64_NATIVE_TEST_ROOT='C:\ag-sqlite-e138-01' WOARM64_NATIVE_ARG_CONVERSION=none
export WOARM64_NATIVE_DRIVER_ROOT='C:\ag-sqlite-e138-01\observer'
[[ ${SQLITE_TMPDIR:-} == "$root/"* ]] || { echo "Upstream test directory must be private" >&2; return 2; }
[[ ${2:-} == "$root/"* && -d $2 ]] || { echo "Existing private relay directory required" >&2; return 2; }
export WOARM64_NATIVE_EXIT_DIR="$(cygpath -w "$2")"
case "$1" in
    build)
        unset MSYS2_ARG_CONV_EXCL
        export MSYS2_ENV_CONV_EXCL='TCLSH;TCL_LIBRARY;TCLLIBPATH;TCLLIBDIR;autosetup_tclsh'
        ;;
    test)
        export MSYS2_ARG_CONV_EXCL='*'
        export MSYS2_ENV_CONV_EXCL='TCLSH;TCL_LIBRARY;TCLLIBPATH;TCLLIBDIR;TMPDIR'
        export TMPDIR="$SQLITE_TMPDIR"
        ;;
    *) echo "Unknown upstream job kind: $1" >&2; return 2 ;;
esac
