#!/usr/bin/env bash
set -euo pipefail
[[ $# == 6 ]] || { echo "Expected PACKAGE SOURCE COMPILER OUTPUT JOBS DEPENDENCY" >&2; exit 2; }
package=$1 source_root=$(cygpath -u "$2") tc=$(cygpath -u "$3")
output=$(cygpath -u "$4") jobs=$5 dependency=$(cygpath -u "$6")
[[ $jobs == 1 || $jobs == 2 ]] || exit 2
: "${WOARM64_CHAIN_LAUNCH_SHA256:?Receipt-verifying launcher required}"
[[ $(sha256sum "$output/launch.json" | cut -d ' ' -f1) == "$WOARM64_CHAIN_LAUNCH_SHA256" ]] || exit 3
[[ ${WOARM64_NATIVE_ARG_CONVERSION:-} == none ]] || exit 3
script_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
native_python=$(cygpath -u "$WOARM64_NATIVE_PYTHON")
native_driver=$(cygpath -u "$WOARM64_NATIVE_DRIVER_ROOT")
export PATH="$tc/bin:/usr/bin" LC_ALL=C MSYSTEM=CYGWIN
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CONFIG_SITE GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm STRIP=strip OBJDUMP=objdump
export CFLAGS="-O2 -g -fstack-protector-strong" CXXFLAGS="-O2 -g -fstack-protector-strong"
export LDFLAGS="-Wl,--no-insert-timestamp"
export MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export CMAKE_BUILD_PARALLEL_LEVEL="$jobs" CONFIG_SITE=/dev/null CCACHE_DISABLE=1
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export XDG_CACHE_HOME="$output/cache" CCACHE_DIR="$output/cache/ccache"
[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]] || exit 3
for path in source build stage; do
    [[ ! -e "$output/$path" ]] || { echo "Fresh source/build/stage required" >&2; exit 3; }
done
mkdir "$output"/{source,build,stage}
cp -a "$source_root/." "$output/source/"
exec > >(tee "$output/build.log") 2>&1
case "$package" in
    readline)
        /usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch -p1 -d "$output/source" \
            -i "$script_root/patches/readline-8.3-history-example-link.patch"
        ;;
    libedit)
        /usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch -p1 -d "$output/source" \
            -i "$script_root/patches/libedit-20240808-read-ioctl.patch"
        /usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch -p1 -d "$output/source" \
            -i "$script_root/patches/libedit-20240808-display-cells.patch"
        ;;
esac
if [[ $package != ncurses ]]; then
    [[ -s "$dependency/usr/lib/libncursesw.a" && -s "$dependency/usr/lib/libncursesw.dll.a" ]]
    export PATH="$dependency/usr/bin:$PATH"
    export CPPFLAGS="-I$(cygpath -m "$dependency/usr/include") -I$(cygpath -m "$dependency/usr/include/ncursesw")"
    export LDFLAGS="$LDFLAGS -L$(cygpath -m "$dependency/usr/lib")"
    export PKG_CONFIG_LIBDIR="$dependency/usr/lib/pkgconfig" PKG_CONFIG_SYSROOT_DIR="$dependency"
    export TERMINFO="$dependency/usr/share/terminfo"
fi
cd "$output/build"
case "$package" in
    ncurses)
        options=(--build=aarch64-pc-msys --host=aarch64-pc-msys --prefix=/usr
                 --without-ada --with-shared --with-cxx-shared --with-normal --without-debug
                 --disable-relink --disable-rpath --with-ticlib --without-termlib --enable-widec
                 --enable-ext-colors --enable-ext-mouse --enable-sp-funcs --with-wrap-prefix=ncwrap_
                 --enable-sigwinch --disable-term-driver --enable-colorfgbg --enable-tcap-names
                 --disable-termcap --disable-mixed-case --with-pkg-config --enable-pc-files
                 --with-manpage-format=normal --with-manpage-aliases
                 --with-default-terminfo-dir=/usr/share/terminfo --enable-echo
                 --mandir=/usr/share/man --includedir=/usr/include/ncursesw
                 --with-build-cflags=-D_XOPEN_SOURCE_EXTENDED
                 --with-pkg-config-libdir=/usr/lib/pkgconfig)
        "$output/source/configure" "${options[@]}"
        export PATH="$PWD/lib:$PWD/progs:$PATH"
        make -j"$jobs"
        mkdir "$output/build/static-cxx"
        make -C c++ -j"$jobs" -f Makefile -f "$script_root/ncurses-static-cxx.mk" \
            "STATIC_CXX_DIR=$output/build/static-cxx" chain-static-cxx
        cp "$output/build/static-cxx/libncurses++w.a" "$output/build/lib/libncurses++w.a"
        /usr/bin/bash "$script_root/finish-ncurses-chain.sh" "$output" "$jobs"
        ;;
    readline)
        base_cflags="$CFLAGS -Wno-error=incompatible-pointer-types"
        for linkage in static shared; do
            mkdir "$output/build/$linkage"
            cd "$output/build/$linkage"
            if [[ $linkage == static ]]; then
                export CFLAGS="$base_cflags -DNCURSES_STATIC"
                options=(--disable-shared --enable-static)
            else
                export CFLAGS="$base_cflags"
                options=(--disable-static --enable-shared)
            fi
            "$output/source/configure" --prefix=/usr --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
                --with-curses --enable-multibyte "${options[@]}" bash_cv_termcap_lib=libncurses
            make -j"$jobs"
            export PATH="$PWD/shlib:$PATH"
            if [[ $linkage == static ]]; then
                make -C examples -j"$jobs" all
                make -C examples -j1 check
                "$native_python" -I "$native_driver/native-target-exec.py" \
                    "$(cygpath -m "$PWD/examples/rlversion.exe")"
            else
                make -C examples -j"$jobs" all READLINE_LIB=../shlib/msys-readline8.dll.a HISTORY_LIB=../shlib/msys-history8.dll.a
                make -C examples -j1 check READLINE_LIB=../shlib/msys-readline8.dll.a HISTORY_LIB=../shlib/msys-history8.dll.a
                "$native_python" -I "$native_driver/native-target-exec.py" \
                    "$(cygpath -m "$PWD/examples/rlversion.exe")"
            fi
            make -j1 DESTDIR="$output/stage" install
        done
        install -Dm644 "$output/source/msys2-package/inputrc" "$output/stage/etc/inputrc"
        ;;
    libedit)
        "$output/source/configure" --prefix=/usr --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
            --enable-widec --enable-shared --enable-static --enable-examples
        grep -qx 'build_libtool_libs=yes' libtool
        grep -qx 'build_old_libs=yes' libtool
        export PATH="$PWD/src/.libs:$PATH"
        make -j"$jobs"
        make -j"$jobs" check
        ar_flags=$(sed -n 's/^lt_ar_flags="\([a-z]*\)"$/\1/p' libtool)
        [[ $ar_flags =~ ^[a-z]+$ ]]
        mkdir "$output/build/static-libedit"
        make -C src -j"$jobs" -f Makefile -f "$script_root/libedit-static.mk" \
            "STATIC_LIBEDIT_DIR=$output/build/static-libedit" \
            "STATIC_LIBEDIT_AR_FLAGS=$ar_flags" chain-static-libedit
        cp "$output/build/static-libedit/libedit.a" "$output/build/src/.libs/libedit.a"
        make -j1 DESTDIR="$output/stage" install
        ;;
    *) echo "Unknown terminal library" >&2; exit 2 ;;
esac
install -Dm644 "$output/source/COPYING" "$output/stage/usr/share/licenses/$package/LICENSE"
printf '%s\n' "package=$package" 'build_host=windows-arm64-native-compiler' \
    'orchestration=private-x64-emulated-bootstrap' 'upstream-check-targets=completed' \
    'native API/PTY/DLL closure and package admission are separate gates' > "$output/build-status.txt"
