#!/usr/bin/env bash
set -euo pipefail

[[ $# == 5 ]] || {
    echo "usage: $0 SOURCE TOOLCHAIN ICONV_STAGE OUTPUT JOBS" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
toolchain=$(cygpath -u "$2")
iconv_stage=$(cygpath -u "$3")
output=$(cygpath -u "$4")
jobs=$5

[[ $jobs =~ ^[1-9][0-9]*$ ]]
[[ ! -e $output/source && ! -e $output/build && ! -e $output/stage ]]
[[ -x $source_root/gettext-runtime/configure ]]
[[ -x $toolchain/bin/gcc.exe ]]
[[ -f $iconv_stage/usr/include/iconv.h ]]
[[ -f $iconv_stage/usr/lib/libiconv.a ]]

mkdir -p "$output"/{source,build,stage,home,temp,cache}
cp -a "$source_root/." "$output/source/"

export PATH="$toolchain/bin:$iconv_stage/usr/bin:/usr/bin"
export MSYSTEM=CYGWIN LC_ALL=C
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export XDG_CACHE_HOME="$output/cache"
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm STRIP=strip
export CFLAGS="-O2 -g -fstack-protector-strong"
export CXXFLAGS="-O2 -g -fstack-protector-strong"
export CPPFLAGS="-I$(cygpath -m "$iconv_stage/usr/include")"
export LDFLAGS="-Wl,--no-insert-timestamp -L$(cygpath -m "$iconv_stage/usr/lib")"
export PKG_CONFIG_LIBDIR="$iconv_stage/usr/lib/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR="$iconv_stage"
export CONFIG_SITE=/dev/null CCACHE_DISABLE=1
export MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]]

# The x64 MSYS build shell otherwise rewrites these target runtime literals
# when it launches the native ARM64 compiler.
export MSYS2_ARG_CONV_EXCL='-DLOCALEDIR=;-DLOCALE_ALIAS_PATH=;-DLIBDIR=;-DINSTALLDIR='

exec > >(tee "$output/build.log") 2>&1
cd "$output/build"
"$output/source/gettext-runtime/configure" \
    --build=aarch64-pc-cygwin \
    --host=aarch64-pc-cygwin \
    --prefix=/usr \
    --enable-static \
    --enable-shared \
    --enable-nls \
    --with-included-gettext \
    "--with-libiconv-prefix=$iconv_stage/usr" \
    --disable-java \
    --disable-native-java \
    --disable-csharp \
    --disable-openmp

grep -qx '#define ENABLE_NLS 1' config.h
grep -qx 'build_libtool_libs=yes' libtool
grep -qx 'build_old_libs=yes' libtool

export PATH="$PWD/intl/.libs:$PWD/libasprintf/.libs:$PWD/src/.libs:$PWD/gnulib-lib/.libs:$PATH"
make -j"$jobs"
make -j"$jobs" check
make -j1 DESTDIR="$output/stage" install

for license in COPYING COPYING.LIB COPYING.LESSER; do
    if [[ -f $output/source/$license ]]; then
        install -Dm644 "$output/source/$license" \
            "$output/stage/usr/share/licenses/gettext-runtime/$license"
    fi
done

for required in \
    usr/bin/msys-intl-8.dll \
    usr/bin/msys-asprintf-0.dll \
    usr/bin/gettext.exe \
    usr/bin/ngettext.exe \
    usr/bin/envsubst.exe \
    usr/include/libintl.h \
    usr/lib/libintl.a \
    usr/lib/libintl.dll.a \
    usr/lib/libasprintf.a \
    usr/lib/libasprintf.dll.a
do
    [[ -f $output/stage/$required ]]
done

host_locale='C:/ag-bash-e138-01/host-bootstrap-02/msys64/usr/share/locale'
if grep -aFlR --include='*.exe' --include='*.dll' --include='*.a' \
    "$host_locale" "$output/stage"; then
    echo "Relocated gettext payload retains host locale prefix" >&2
    exit 3
fi
grep -aFq '/usr/share/locale' "$output/stage/usr/lib/libintl.a"
grep -aFq '/usr/share/locale' "$output/stage/usr/bin/msys-intl-8.dll"
