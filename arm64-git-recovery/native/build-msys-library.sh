#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 || $# == 6 ]] || { echo "usage: $0 PACKAGE SOURCE NATIVE_TOOLCHAIN OUTPUT JOBS [DEPENDENCY_STAGE]" >&2; exit 2; }
package=$1 source_root=$(cygpath -u "$2") toolchain=$(cygpath -u "$3")
output=$(cygpath -u "$4") jobs=$5
[[ $jobs =~ ^[1-8]$ && ! -e $output ]] || { echo "New output and approved job allocation required" >&2; exit 2; }
case "$package" in libxcrypt|libiconv-bootstrap|zlib-msys|gettext-msys|xz-msys) ;; *) echo "Unsupported MSYS library profile" >&2; exit 2 ;; esac
dependency=
if [[ $# == 6 ]]; then dependency=$(cygpath -u "$6"); fi
[[ $package != gettext-msys || -n $dependency ]] || { echo "Native iconv dependency required" >&2; exit 3; }
[[ $package != xz-msys || -n $dependency ]] || { echo "Native iconv/gettext dependencies required" >&2; exit 3; }
export PATH="$toolchain/bin:/usr/bin" LC_ALL=C
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CONFIG_SITE GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm STRIP=strip OBJDUMP=objdump
export CFLAGS="-O2 -g" LDFLAGS="-Wl,--no-insert-timestamp"
if [[ -n $dependency ]]; then
    export PATH="$dependency/usr/bin:$PATH"
    export CPPFLAGS="-I$(cygpath -m "$dependency/usr/include")"
    export LDFLAGS="$LDFLAGS -L$(cygpath -m "$dependency/usr/lib")"
fi
[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]] || { echo "Wrong compiler target" >&2; exit 3; }
mkdir -p "$output"/{source,build,stage,temp,home}
mkdir "$output/native-exits"
mkdir "$output/documentation-exits"
cp -a "$source_root/." "$output/source/"
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
exec > >(tee "$output/build.log") 2>&1
cd "$output/build"
if [[ $package == zlib-msys ]]; then
    cd "$output/source"
    export MSYSTEM=CYGWIN
    ./configure --prefix=/usr
    make -j"$jobs" -f win32/Makefile.gcc CFLAGS="$CFLAGS" SHAREDLIB=msys-z.dll
    export PATH="$PWD:$PATH"
    make -j"$jobs" test
    make -j1 -f win32/Makefile.gcc install DESTDIR="$output/stage" SHAREDLIB=msys-z.dll \
        BINARY_PATH=/usr/bin INCLUDE_PATH=/usr/include LIBRARY_PATH=/usr/lib prefix=/usr SHARED_MODE=1
    install -Dm644 zlib.3 "$output/stage/usr/share/man/man3/zlib.3"
    install -Dm644 LICENSE "$output/stage/usr/share/licenses/zlib/LICENSE"
    printf '%s\n' 'build_host=windows-arm64-native-compiler' 'orchestration=private-x64-emulated-bootstrap' \
        'profile=zlib-msys' 'Native consumer and package admission still required.' > "$output/BUILD-STATUS.txt"
    exit 0
fi
options=(--build=aarch64-pc-cygwin --host=aarch64-pc-cygwin --prefix=/usr --enable-static --enable-shared)
case "$package" in
    xz-msys)
        : "${WOARM64_DOCUMENTATION_DRIVER:?An explicit qualified documentation driver is required}"
        documentation_driver=$(cygpath -u "$WOARM64_DOCUMENTATION_DRIVER")
        documentation_relay="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/doc-driver"
        export PATH="$documentation_relay:$documentation_driver:$PATH" WOARM64_WINDOWS_DOXYGEN=1
        command -v doxygen >/dev/null || {
            echo "The pinned XZ package requires Doxygen; ask the bootstrap owner, do not disable documentation." >&2
            exit 3
        }
        export MSYSTEM=CYGWIN lt_cv_deplibs_check_method=pass_all
        options+=(--enable-doxygen --enable-nls --enable-threads=posix
                  "--with-libintl-prefix=$dependency/usr" "--with-libiconv-prefix=$dependency/usr")
        ;;
    libxcrypt)
        options+=(--disable-failure-tokens --disable-xcrypt-compat-files --disable-obsolete-api
                  --enable-hashes=all --disable-symvers)
        ;;
    libiconv-bootstrap)
        options+=(--without-libintl-prefix --enable-extra-encodings --disable-nls)
        ;;
    gettext-msys)
        options+=(--with-included-libcroco --with-included-libunistring --with-included-libxml
                  --with-included-glib --with-included-gettext "--with-libiconv-prefix=$dependency/usr"
                  --without-emacs --disable-java --disable-native-java --disable-csharp --disable-openmp)
        export PATH="$PWD/gettext-runtime/intl/.libs:$PWD/gettext-runtime/libasprintf/.libs:$PWD/gettext-tools/src/.libs:$PWD/gettext-tools/gnulib-lib/.libs:$PWD/gettext-tools/libgettextpo/.libs:$PATH"
        ;;
esac
"$output/source/configure" "${options[@]}"
if [[ $package == xz-msys ]]; then
    for feature in ENABLE_NLS MYTHREAD_POSIX; do
        grep -qx "#define $feature 1" config.h || {
            echo "Required XZ configuration feature was not enabled: $feature" >&2
            exit 3
        }
    done
fi
libtools=(libtool)
if [[ $package == gettext-msys ]]; then
    libtools=(gettext-runtime/libtool gettext-runtime/libasprintf/libtool gettext-tools/libtool)
fi
for configured in "${libtools[@]}"; do
    if [[ ! -f $configured ]] || ! grep -qx 'build_libtool_libs=yes' "$configured"; then
        echo "The configured libtool cannot build shared MSYS libraries: $configured; refusing static-only fallback." >&2
        exit 3
    fi
done
make -j"$jobs"
case "$package" in
    libxcrypt) export PATH="$PWD/.libs:$PATH" ;;
    libiconv-bootstrap) export PATH="$PWD/lib/.libs:$PWD/libcharset/lib/.libs:$PWD/srclib/.libs:$PATH" ;;
    xz-msys) export PATH="$PWD/src/liblzma/.libs:$PATH" ;;
esac
dispatcher="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/native-msys-test-dispatch.sh"
make -j"$jobs" "LOG_COMPILER=/usr/bin/bash $dispatcher" check
make -j1 DESTDIR="$output/stage" install
mkdir -p "$output/stage/usr/share/licenses/$package"
count=0
for license in COPYING COPYING.LIB COPYING.LIB.LIBXCRYPT COPYING.LIB.LIBCRYPT COPYING.LESSER COPYING.RUNTIME LICENSING; do
    if [[ -f "$output/source/$license" ]]; then
        cp "$output/source/$license" "$output/stage/usr/share/licenses/$package/"
        count=$((count + 1))
    fi
done
[[ $count -gt 0 ]] || { echo "Missing source license payload" >&2; exit 4; }
if [[ $package == xz-msys ]]; then
    for license in COPYING.0BSD COPYING.GPLv2 COPYING.GPLv3 COPYING.LGPLv2.1; do
        [[ -s "$output/source/$license" ]] || { echo "Missing XZ license: $license" >&2; exit 4; }
        cp "$output/source/$license" "$output/stage/usr/share/licenses/$package/"
    done
fi
printf '%s\n' 'build_host=windows-arm64-native-compiler' 'orchestration=private-x64-emulated-bootstrap' \
    "profile=$package" 'Native consumer and package admission still required.' > "$output/BUILD-STATUS.txt"
