#!/usr/bin/env bash
set -euo pipefail

[[ $# == 5 ]] || {
    echo "usage: $0 SOURCE_ROOT TOOLCHAIN GETTEXT_STAGE OUTPUT JOBS" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
toolchain=$(cygpath -u "$2")
gettext_stage=$(cygpath -u "$3")
output=$(cygpath -u "$4")
jobs=$5
[[ $jobs =~ ^[1-6]$ ]] || exit 2

runtime_sha=${WOARM64_TC_RUNTIME_SHA256:-}
import_sha=${WOARM64_TC_IMPORT_SHA256:-}
crt_sha=${WOARM64_TC_CRT0_SHA256:-}
[[ $runtime_sha =~ ^[0-9a-f]{64}$ &&
   $import_sha =~ ^[0-9a-f]{64}$ &&
   $crt_sha =~ ^[0-9a-f]{64}$ ]] ||
    { echo "Sealed compiler runtime, import-library, and CRT hashes are required" >&2; exit 2; }

for sealed_input in \
    "$runtime_sha:$toolchain/bin/msys-2.0.dll" \
    "$import_sha:$toolchain/aarch64-pc-cygwin/lib/libmsys-2.0.a" \
    "$crt_sha:$toolchain/aarch64-pc-cygwin/lib/crt0.o"; do
    expected=${sealed_input%%:*}
    input=${sealed_input#*:}
    actual=$(sha256sum "$input")
    [[ ${actual%% *} == "$expected" ]] ||
        { echo "Compiler cohort mismatch: $input" >&2; exit 3; }
done

[[ -f $gettext_stage/usr/lib/libintl.a ]]
[[ -f $gettext_stage/usr/bin/msys-intl-8.dll ]]

export PATH="$toolchain/bin:$gettext_stage/usr/bin:/usr/bin"
export MSYSTEM=CYGWIN LC_ALL=C
unset CC CXX CPP CPPFLAGS CFLAGS CXXFLAGS LDFLAGS LIBRARY_PATH COMPILER_PATH GCC_EXEC_PREFIX CONFIG_SITE
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm STRIP=strip
export CFLAGS="-O2 -g -fstack-protector-strong"
export CXXFLAGS="$CFLAGS"
export CPPFLAGS="-I$(cygpath -m "$gettext_stage/usr/include")"
export LDFLAGS="-Wl,--no-insert-timestamp -L$(cygpath -m "$gettext_stage/usr/lib")"
export PKG_CONFIG_LIBDIR="$gettext_stage/usr/lib/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR="$gettext_stage"
export CONFIG_SITE=/dev/null CCACHE_DISABLE=1
export MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export XDG_CACHE_HOME="$output/cache"
export WOARM64_NATIVE_ARG_CONVERSION=none
export MSYS2_ARG_CONV_EXCL='-DLOCALEDIR=;-DLOCALE_ALIAS_PATH=;-DLIBDIR=;-DINSTALLDIR='

[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]]
mkdir -p "$HOME" "$TMPDIR" "$XDG_CACHE_HOME" "$output/source" "$output/build" "$output/stage"
cp -a "$source_root/." "$output/source/"

makefile="$output/source/src/Makefile.in"
[[ $(grep -c 'cygwin\*) .*@LTLIBINTL@' "$makefile") == 1 ]]
sed -i '/cygwin\*) /s/@LTLIBINTL@/@LIBINTL@/' "$makefile"
[[ $(grep -c 'cygwin\*) .*@LIBINTL@' "$makefile") == 1 ]]
[[ $(grep -c 'cygwin\*) .*@LTLIBINTL@' "$makefile") == 0 ]]

exec > >(tee "$output/build.log") 2>&1
cd "$output/build"
"$output/source/configure" \
    --build=aarch64-pc-cygwin \
    --host=aarch64-pc-cygwin \
    --prefix=/usr \
    --enable-static \
    --enable-shared \
    --enable-nls \
    --enable-extra-encodings \
    "--with-libintl-prefix=$gettext_stage/usr"

grep -qx '#define ENABLE_EXTRA 1' config.h
grep -qx '#define ENABLE_NLS 1' config.h
grep -qx 'build_libtool_libs=yes' libtool
grep -qx 'build_old_libs=yes' libtool

export PATH="$PWD/lib/.libs:$PWD/libcharset/lib/.libs:$PWD/srclib/.libs:$PWD/src/.libs:$PATH"
make -j"$jobs"
make -j"$jobs" "LOG_COMPILER=/usr/bin/bash /c/ag-native-e138-01/maintained/native-msys-test-dispatch.sh" check
make -j1 DESTDIR="$output/stage" install

for license in COPYING COPYING.LIB; do
    [[ ! -f $output/source/$license ]] ||
        install -Dm644 "$output/source/$license" "$output/stage/usr/share/licenses/libiconv/$license"
done

host_locale=$(cygpath -am /usr/share/locale)
dependency_locale=$(cygpath -m "$gettext_stage/usr/share/locale")
while IFS= read -r payload; do
    for forbidden_locale in "$host_locale" "$dependency_locale"; do
        if grep -aFq "$forbidden_locale" "$payload"; then
            echo "Staged payload retains build-only locale prefix: $payload" >&2
            exit 3
        fi
    done
done < <(find "$output/stage" -type f \( -name '*.exe' -o -name '*.dll' -o -name '*.a' \) -print)

[[ -f $output/stage/usr/bin/iconv.exe ]]
[[ -f $output/stage/usr/bin/msys-iconv-2.dll ]]
[[ -f $output/stage/usr/lib/libiconv.a ]]
grep -aFq '/usr/share/locale' "$output/stage/usr/bin/iconv.exe"
