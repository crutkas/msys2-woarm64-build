#!/usr/bin/env bash
set -euo pipefail
[[ $# == 6 ]] || exit 2
profile=$1 source_root=$(cygpath -u "$2") tc=$(cygpath -u "$3")
output=$(cygpath -u "$4") jobs=$5 dependency=$(cygpath -u "$6")
[[ $jobs == 1 || $jobs == 2 ]] || exit 2
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
: "${WOARM64_BASH_NLS_LAUNCH_SHA256:?Verified launcher required}"
[[ $(sha256sum "$output/launch.json" | cut -d ' ' -f1) == "$WOARM64_BASH_NLS_LAUNCH_SHA256" ]]
export PATH="$tc/bin:/usr/bin" MSYSTEM=CYGWIN LC_ALL=C
unset CC CXX CPP CPPFLAGS CFLAGS CXXFLAGS LDFLAGS LIBRARY_PATH COMPILER_PATH GCC_EXEC_PREFIX CONFIG_SITE
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm STRIP=strip
export CFLAGS="-O2 -g -fstack-protector-strong" CXXFLAGS="-O2 -g -fstack-protector-strong"
export LDFLAGS="-Wl,--no-insert-timestamp" CONFIG_SITE=/dev/null CCACHE_DISABLE=1
export MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export XDG_CACHE_HOME="$output/cache" WOARM64_NATIVE_ARG_CONVERSION=none
[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]]
mkdir "$output"/{source,build,stage}
cp -a "$source_root/." "$output/source/"
exec > >(tee "$output/build.log") 2>&1
options=(--build=aarch64-pc-cygwin --host=aarch64-pc-cygwin --prefix=/usr --enable-static --enable-shared)
configure="$output/source/configure"
if [[ $profile != iconv-bridge ]]; then
    [[ -d "$dependency/usr/include" && -d "$dependency/usr/lib" ]]
    export PATH="$dependency/usr/bin:$PATH"
    export CPPFLAGS="-I$(cygpath -m "$dependency/usr/include")"
    export LDFLAGS="$LDFLAGS -L$(cygpath -m "$dependency/usr/lib")"
    export PKG_CONFIG_LIBDIR="$dependency/usr/lib/pkgconfig" PKG_CONFIG_SYSROOT_DIR="$dependency"
fi
case "$profile" in
    iconv-bridge)
        options+=(--disable-nls --without-libintl-prefix --enable-extra-encodings)
        ;;
    iconv-full)
        options+=(--enable-nls "--with-libintl-prefix=$dependency/usr" --enable-extra-encodings)
        ;;
    gettext-runtime)
        configure="$output/source/gettext-runtime/configure"
        options+=(--enable-nls --with-included-gettext "--with-libiconv-prefix=$dependency/usr"
                  --disable-java --disable-native-java --disable-csharp --disable-openmp)
        ;;
    *) echo "Unsupported Bash NLS profile" >&2; exit 2 ;;
esac
cd "$output/build"
"$configure" "${options[@]}"
if [[ $profile == iconv-* ]]; then
    grep -qx '#define ENABLE_EXTRA 1' config.h
    if [[ $profile == iconv-full ]]; then grep -qx '#define ENABLE_NLS 1' config.h; fi
    export PATH="$PWD/lib/.libs:$PWD/libcharset/lib/.libs:$PWD/srclib/.libs:$PWD/src/.libs:$PATH"
else
    grep -qx '#define ENABLE_NLS 1' config.h
    export PATH="$PWD/intl/.libs:$PWD/libasprintf/.libs:$PWD/src/.libs:$PWD/gnulib-lib/.libs:$PATH"
fi
grep -qx 'build_libtool_libs=yes' libtool
grep -qx 'build_old_libs=yes' libtool
make -j"$jobs"
make -j"$jobs" "LOG_COMPILER=/usr/bin/bash $here/native-msys-test-dispatch.sh" check
make -j1 DESTDIR="$output/stage" install
license_package=libiconv
license_source="$output/source"
if [[ $profile == gettext-runtime ]]; then license_package=gettext-runtime; fi
for license in COPYING COPYING.LIB COPYING.LESSER; do
    if [[ -f "$license_source/$license" ]]; then
        install -Dm644 "$license_source/$license" "$output/stage/usr/share/licenses/$license_package/$license"
    fi
done
