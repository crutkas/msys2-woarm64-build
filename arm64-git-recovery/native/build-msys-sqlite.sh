#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 ]] || exit 2
phase=$1 root=$(cygpath -u "$2") build=$(cygpath -u "$3") jobs=$4 output=$(cygpath -u "$5")
ccroot=$(cygpath -m "$2")
[[ $jobs == 1 || $jobs == 2 ]] || exit 2
[[ -f "$output/launch.json" ]] || { echo "Receipt-verifying launcher required" >&2; exit 2; }
export PATH="$root/tcl/usr/bin:$root/readline/usr/bin:$root/ncurses/usr/bin:$root/zlib/usr/bin:$root/compiler/bin:$root/bootstrap/usr/bin"
export LC_ALL=C MSYSTEM=CYGWIN CONFIG_SITE=/dev/null CCACHE_DISABLE=1
export MSYS2_ARG_CONV_EXCL='*'
export MSYS2_ENV_CONV_EXCL='WRAPPER;CC;CC_FOR_BUILD;CXX;AR;RANLIB;LD;AS;NM;STRIP;OBJDUMP;CFLAGS;CPPFLAGS;LDFLAGS;TCL_LIBRARY;TCLLIBPATH;TCLLIBDIR;TCLSH;TMP;TEMP;TMPDIR'
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS LIBS CONFIG_SHELL GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export CC="$root/compiler/bin/gcc.exe" CXX="$root/compiler/bin/g++.exe"
export CC_FOR_BUILD="$CC" CCACHE=none
export TMP="$ccroot/temp" TEMP="$ccroot/temp" TMPDIR="$ccroot/temp"
export AR="$root/compiler/bin/ar.exe" RANLIB="$root/compiler/bin/ranlib.exe"
export LD="$root/compiler/bin/ld.exe" AS="$root/compiler/bin/as.exe"
export NM="$root/compiler/bin/nm.exe" STRIP="$root/compiler/bin/strip.exe"
export OBJDUMP="$root/compiler/bin/objdump.exe"
export CFLAGS="-O2 -g -fstack-protector-strong -pipe -D_FORTIFY_SOURCE=2"
export CPPFLAGS="$SQLITE_RECIPE_CPPFLAGS -I$ccroot/zlib/usr/include -I$ccroot/readline/usr/include -I$ccroot/ncurses/usr/include/ncursesw"
export LDFLAGS="-Wl,--no-insert-timestamp -L$ccroot/zlib/usr/lib -L$ccroot/readline/usr/lib -L$ccroot/ncurses/usr/lib -L$ccroot/tcl/usr/lib"
export MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs" OMP_NUM_THREADS=1
export TCLLIBDIR=/usr/lib/sqlite3.53.4
export TCL_LIBRARY="$root/tcl/usr/lib/tcl8.6" TCLLIBPATH="$root/tcl/usr/lib"
export TCLSH="$root/tcl/usr/bin/tclsh8.6.exe"
[[ $("$CC" -dumpmachine) == aarch64-pc-cygwin ]] || { echo "Wrong compiler ABI" >&2; exit 3; }
cd "$build"
tools=(sqlite3.exe sqlite3_analyzer.exe sqldiff.exe dbhash.exe rbu.exe)
driver_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
make_args=("B.tclsh=$driver_dir/sqlite-native-tcl-script.sh" "TCLSH_CMD=$driver_dir/sqlite-native-tcl-script.sh" "TCL_CONFIG_SH=$root/tcl-config-windows/tclConfig.sh")
if [[ $phase != configure ]]; then
    # Native Windows-hosted GCC needs normal host-driver filename conversion;
    # Tcl alone crosses its separate literal-MSYS-path relay boundary.
    unset MSYS2_ARG_CONV_EXCL
fi
case "$phase" in
    configure)
        fixture="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fixtures/sqlite-tcl-paths.tcl"
        "$root/observer/native-target-exec.sh" "$TCLSH" "$fixture" "$output" \
            "$root/tcl/usr/include/tcl.h" "$root/tcl-config-windows/tclConfig.sh"
        mapfile -t options <<< "$SQLITE_NATIVE_CONFIGURE"
        # The shell trampoline trusts Tcl's /usr/bin nameofexecutable, which
        # belongs to the native runtime, not the foreign bootstrap shell.
        export WRAPPER="$root/prepared/source/configure"
        mkdir -p "$build/configure-driver/usr/bin" "$build/configure-driver/etc"
        cp "$root/tcl/etc/fstab" "$build/configure-driver/etc/fstab"
        cp "$root/compiler/bin/msys-2.0.dll" "$build/configure-driver/usr/bin/"
        "$CC" -O1 "$ccroot/prepared/source/autosetup/jimsh0.c" -o "$(cygpath -m "$build")/configure-driver/usr/bin/jimsh.exe"
        "$build/configure-driver/usr/bin/jimsh.exe" "$root/prepared/source/autosetup/autosetup" "${options[@]}" \
            "--with-tcl=$root/tcl-config-windows" \
            "--with-readline-cflags=-I$ccroot/readline/usr/include" \
            "--with-readline-ldflags=-L$ccroot/readline/usr/lib -lreadline -L$ccroot/ncurses/usr/lib -lncursesw"
        ;;
    build)
        make -j"$jobs" "${make_args[@]}" all "${tools[@]}"
        ;;
    extensions)
        make -j"$jobs" -C ext/misc \
            "CPPFLAGS=-I$build -I$root/prepared/source/src -I$root/zlib/usr/include" \
            "LIBS=-Wl,--no-undefined -L$build -lsqlite3 -L$root/zlib/usr/lib -lz"
        ;;
    install)
        splits=(sqlite libsqlite libsqlite-devel sqlite-doc tcl-sqlite sqlite-extensions lemon)
        for name in "${splits[@]}"; do
            [[ ! -e splits/$name ]] || { echo "Existing split: $name" >&2; exit 3; }
            mkdir -p "splits/$name/usr/share/licenses/$name"
            cp "$root/prepared/recipe/LICENSE" "splits/$name/usr/share/licenses/$name/"
        done
        make -j1 "${make_args[@]}" "DESTDIR=$build/splits/sqlite" install-shell-0 install-man1
        install -m755 "${tools[@]}" "$build/splits/sqlite/usr/bin/"
        make -j1 "${make_args[@]}" "DESTDIR=$build/splits/libsqlite" install-dll
        # Split pruning exactly follows the pinned package functions.
        rm -rf "$build/splits/libsqlite/usr/lib"
        make -j1 "${make_args[@]}" "DESTDIR=$build/splits/libsqlite-devel" install-pc install-headers install-lib install-dll
        rm -rf "$build/splits/libsqlite-devel/usr/bin"
        mkdir -p "$build/splits/sqlite-doc/usr/share/doc/sqlite"
        cp -R "$root/prepared/docs/." "$build/splits/sqlite-doc/usr/share/doc/sqlite/"
        make -j1 "${make_args[@]}" "DESTDIR=$build/splits/tcl-sqlite" install-tcl
        make -j1 -C ext/misc "DESTDIR=$build/splits/sqlite-extensions" \
            "CPPFLAGS=-I$build -I$root/prepared/source/src -I$root/zlib/usr/include" \
            "LIBS=-Wl,--no-undefined -L$build -lsqlite3 -L$root/zlib/usr/lib -lz" install
        sed 's|@VERSION@|3.53.4|g' "$root/prepared/recipe/README.md.in" > "$build/splits/sqlite-extensions/usr/share/sqlite/extensions/README.md"
        mkdir -p "$build/splits/lemon/usr/bin" "$build/splits/lemon/usr/share/lemon"
        cp lemon.exe "$build/splits/lemon/usr/bin/"
        cp lempar.c "$build/splits/lemon/usr/share/lemon/"
        ;;
    quicktest)
        # Two runner jobs, each with serial make children: aggregate <= 2.
        export MAKEFLAGS=-j1 MFLAGS=-j1
        make -j1 "${make_args[@]}" "TSTRNNR_OPTS=--jobs $jobs" quicktest
        ;;
    tcltest)
        make -j"$jobs" "${make_args[@]}" testfixture.exe
        export PATH="$build:$PATH"
        "$root/observer/native-target-exec.sh" "$build/testfixture.exe" "$root/prepared/source/test/veryquick.test" \
            --verbose=file --output=test-out.txt
        ;;
    *) echo "Unknown phase: $phase" >&2; exit 2 ;;
esac
