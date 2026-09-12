#!/usr/bin/env bash
set -euo pipefail
[[ $# == 7 ]] || { echo "usage: $0 PACKAGE WINDOWS_SOURCE WINDOWS_TOOLCHAIN WINDOWS_OUTPUT JOBS WINDOWS_DEPENDENCIES both|shared|static-bootstrap" >&2; exit 2; }
package=$1 source_root=$(cygpath -u "$2") toolchain=$(cygpath -u "$3") output=$(cygpath -u "$4") jobs=$5
dependencies=$(cygpath -u "$6")
profile=$7
[[ $profile == both || $profile == shared || $profile == static-bootstrap ]] || { echo "Unknown library profile" >&2; exit 2; }
[[ $package != libidn2 || $profile != both ]] || { echo "libidn2 needs separate shared/static configurations" >&2; exit 2; }
[[ $jobs =~ ^[1-8]$ && ! -e $output ]] || { echo "Explicit job allocation and fresh output required" >&2; exit 2; }
case "$package" in libiconv|libunistring|libidn2|libpsl|gettext-runtime) ;; *) echo "Unsupported library" >&2; exit 2 ;; esac
export PATH="$toolchain/bin:$dependencies/bin:/usr/bin"
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib RC=windres LC_ALL=C
export LD=ld AS=as NM=nm STRIP=strip OBJDUMP=objdump
export RC='windres --preprocessor=gcc --preprocessor-arg=-E --preprocessor-arg=-xc --preprocessor-arg=-DRC_INVOKED'
export WINDRES="$RC"
export CFLAGS="-O2 -g"
export CPPFLAGS="-I$(cygpath -m "$dependencies/include")"
export LDFLAGS="-L$(cygpath -m "$dependencies/lib")"
export PKG_CONFIG_PATH="$dependencies/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$dependencies/lib/pkgconfig"
[[ $(gcc -dumpmachine) == aarch64-w64-mingw32 ]] || { echo "Wrong compiler target" >&2; exit 3; }
mkdir -p "$output"
cp -a "$source_root" "$output/source"
mkdir "$output/build" "$output/stage" "$output/temp" "$output/home"
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
exec > >(tee "$output/build.log") 2>&1
cd "$output/build"
options=(--build=aarch64-w64-mingw32 --host=aarch64-w64-mingw32
         --prefix="$output/stage" --enable-shared --enable-static)
if [[ $profile == static-bootstrap ]]; then options+=(--disable-shared); fi
if [[ $profile == shared ]]; then options+=(--disable-static); fi
configure="$output/source/configure"
case "$package" in
    libiconv) options+=(--enable-relocatable --enable-extra-encodings --disable-rpath) ;;
    libunistring) options+=(--enable-threads=windows) ;;
    libidn2)
        options+=(--target=aarch64-w64-mingw32 --disable-doc --disable-rpath lt_cv_deplibs_check_method=pass_all)
        if [[ $profile == static-bootstrap ]]; then
            export CPPFLAGS="$CPPFLAGS -DIN_LIBUNISTRING -DIDN2_STATIC"
        fi
        ;;
    libpsl) options+=(--enable-runtime=libidn2 --disable-gtk-doc) ;;
    gettext-runtime)
        configure="$output/source/gettext-runtime/configure"
        options+=(--enable-threads=windows --enable-relocatable
                  "--with-libiconv-prefix=$dependencies" lt_cv_deplibs_check_method=pass_all)
        ;;
esac
"$configure" "${options[@]}"
make -j"$jobs"
make -j"$jobs" check
make -j1 install
mkdir -p "$output/stage/share/licenses/$package"
for license in COPYING COPYING.LIB COPYING.LESSER; do
    if [[ -f "$output/source/$license" ]]; then cp "$output/source/$license" "$output/stage/share/licenses/$package/"; fi
done
printf '%s\n' 'status=native-library-built-tested' \
    'compiler=windows-arm64-native' 'orchestration=windows-x64-emulated-msys' \
    "profile=$profile" > "$output/BUILD-STATUS.txt"
