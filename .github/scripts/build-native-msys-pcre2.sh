#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 7; then
    echo "usage: $0 OUTPUT SOURCE_ROOT RECIPE_ROOT COMPILER_ROOT SDK_ROOT FIXTURE SYSTEM32" >&2
    exit 2
fi

output="$(cygpath -u "$1")"
sources="$(cygpath -u "$2")"
recipes="$(cygpath -u "$3")"
compiler="$(cygpath -u "$4")"
sdk="$(cygpath -u "$5")"
fixture="$(cygpath -u "$6")"
system32="$(cygpath -u "$7")"
bootstrap_bin="$(dirname "$(command -v bash)")"

if test -e "$output"; then
    echo "fresh native MSYS PCRE2 output required: $output" >&2
    exit 3
fi

umask 022
mkdir -p "$output"/{src,stage,runtime/usr/bin,logs,home,temp,native-exits}
runtime_bin="$output/runtime/usr/bin"
export HOME="$output/home"
export TMP="$output/temp"
export TEMP="$output/temp"
export TMPDIR="$output/temp"
export MAKEFLAGS=-j1
export MFLAGS=-j1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export CCACHE_DISABLE=1
export CHOST=aarch64-pc-cygwin
export CC="$compiler/bin/gcc.exe"
export CXX="$compiler/bin/g++.exe"
export AR="$compiler/bin/ar.exe"
export RANLIB="$compiler/bin/ranlib.exe"
export STRIP="$compiler/bin/strip.exe"
export WINDRES="$compiler/bin/windres.exe"
export PATH="$runtime_bin:$compiler/bin:$bootstrap_bin:$system32"
export CFLAGS="-O2 -g -pipe -fstack-protector-strong -D_FORTIFY_SOURCE=2"
export CPPFLAGS="-I$sdk/usr/include -I$sdk/usr/include/ncursesw"
export LDFLAGS="-L$sdk/usr/lib -Wl,--no-insert-timestamp"
export PKG_CONFIG_PATH="$sdk/usr/lib/pkgconfig"

cp "$compiler/bin/msys-2.0.dll" "$runtime_bin/"
cp "$sdk/usr/bin/msys-readline8.dll" "$runtime_bin/"
cp "$sdk/usr/bin/msys-history8.dll" "$runtime_bin/"
cp "$sdk/usr/bin/msys-ncursesw6.dll" "$runtime_bin/"

tar -xf "$sources/bzip2-1.0.8.tar.gz" -C "$output/src"
cd "$output/src/bzip2-1.0.8"
patch -p1 -i "$recipes/bzip2-1.0.6-msys-dll.patch"
patch -p1 -i "$recipes/bzip2-1.0.6-msys2.patch"
./configure --build="$CHOST" --prefix=/usr --enable-shared \
    >"$output/logs/bzip2-configure.log" 2>&1
make -j1 all >"$output/logs/bzip2-build.log" 2>&1
make -j1 test >"$output/logs/bzip2-check.log" 2>&1
make PREFIX="$output/stage/bzip2" install >"$output/logs/bzip2-install.log" 2>&1
cp "$output/stage/bzip2/bin/msys-bz2-1.dll" "$runtime_bin/"

tar -xf "$sources/zlib-1.3.2.tar.xz" -C "$output/src"
cd "$output/src/zlib-1.3.2"
patch -p2 -i "$recipes/zlib-1.2.13-configure.patch"
patch -p2 -i "$recipes/zlib-1.2.13-gzopen_w.patch"
export MSYSTEM=CYGWIN
./configure --prefix=/usr >"$output/logs/zlib-configure.log" 2>&1
make -j1 -f win32/Makefile.gcc \
    CC="$CC" AR="$AR" RC="$WINDRES" \
    CFLAGS="$CFLAGS" SHAREDLIB=msys-z.dll \
    >"$output/logs/zlib-build.log" 2>&1
make -j1 test >"$output/logs/zlib-check.log" 2>&1
make -f win32/Makefile.gcc install \
    CC="$CC" AR="$AR" RC="$WINDRES" \
    DESTDIR="$output/stage/zlib" SHAREDLIB=msys-z.dll \
    BINARY_PATH=/usr/bin INCLUDE_PATH=/usr/include LIBRARY_PATH=/usr/lib \
    prefix=/usr SHARED_MODE=1 >"$output/logs/zlib-install.log" 2>&1
install -Dm644 zlib.3 "$output/stage/zlib/usr/share/man/man3/zlib.3"
cp "$output/stage/zlib/usr/bin/msys-z.dll" "$runtime_bin/"

tar -xf "$sources/pcre2-10.48.tar.bz2" -C "$output/src"
cd "$output/src/pcre2-10.48"
autoreconf -fi >"$output/logs/pcre2-autoreconf.log" 2>&1
export CPPFLAGS="-I$output/stage/bzip2/include -I$output/stage/zlib/usr/include -I$sdk/usr/include -I$sdk/usr/include/ncursesw"
export LDFLAGS="-L$output/stage/bzip2/lib -L$output/stage/zlib/usr/lib -L$sdk/usr/lib -Wl,--no-insert-timestamp"
export PKG_CONFIG_PATH="$output/stage/zlib/usr/lib/pkgconfig:$sdk/usr/lib/pkgconfig"
./configure \
    --build="$CHOST" \
    --prefix=/usr \
    --enable-jit \
    --enable-pcre2-8 \
    --enable-pcre2-16 \
    --enable-pcre2-32 \
    --enable-newline-is-anycrlf \
    --enable-unicode \
    --enable-pcre2grep-jit \
    --enable-pcre2grep-libbz2 \
    --enable-pcre2grep-libz \
    --disable-pcre2test-libedit \
    --enable-pcre2test-libreadline \
    ac_cv_header_windows_h=no \
    >"$output/logs/pcre2-configure.log" 2>&1
make -j1 >"$output/logs/pcre2-build.log" 2>&1
make -j1 check >"$output/logs/pcre2-check.log" 2>&1
make DESTDIR="$output/stage/pcre2" install >"$output/logs/pcre2-install.log" 2>&1
cp "$output/stage/pcre2/usr/bin/"msys-pcre2-*-0.dll "$runtime_bin/"
cp "$output/stage/pcre2/usr/bin/msys-pcre2-posix-3.dll" "$runtime_bin/"

"$CC" $CFLAGS \
    -I"$output/stage/pcre2/usr/include" \
    "$fixture" \
    -L"$output/stage/pcre2/usr/lib" -lpcre2-8 \
    -Wl,--no-insert-timestamp \
    -o "$runtime_bin/native-pcre2-jit-api.exe" \
    >"$output/logs/api-compile.log" 2>&1

printf '%s\n' "native MSYS PCRE2 serial build and strict upstream check completed" \
    >"$output/build-complete.txt"
