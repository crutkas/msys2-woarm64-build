#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 ]] || { echo "usage: $0 PACKAGE SOURCE NATIVE_SDK OUTPUT JOBS" >&2; exit 2; }
package=$1 source_root=$(cygpath -u "$2") toolchain=$(cygpath -u "$3")
output=$(cygpath -u "$4") jobs=$5
[[ $jobs =~ ^[1-8]$ && ! -e $output ]] || { echo "Fresh output and explicit approved jobs required" >&2; exit 2; }
case "$package" in bash|coreutils|make) ;; *) echo "Unsupported POSIX bootstrap" >&2; exit 2 ;; esac
export PATH="$toolchain/bin:/usr/bin" LC_ALL=C
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CONFIG_SITE GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm STRIP=strip
export CFLAGS="-O2 -g" LDFLAGS="-Wl,--no-insert-timestamp"
[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]] || { echo "Wrong native compiler target" >&2; exit 3; }
mkdir -p "$output"/{source,build,stage,temp,home,native-exits}
cp -a "$source_root/." "$output/source/"
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
exec > >(tee "$output/build.log") 2>&1
if [[ $package == bash ]]; then cd "$output/source"; else cd "$output/build"; fi
options=(--build=aarch64-pc-cygwin --host=aarch64-pc-cygwin --prefix=/usr --disable-nls)
case "$package" in
    bash) options+=(--disable-readline --without-bash-malloc --sysconfdir=/etc --localstatedir=/var) ;;
    make) options+=(--without-guile --without-libintl-prefix --without-libiconv-prefix --disable-posix-spawn ac_cv_dos_paths=yes) ;;
    coreutils)
        options+=(--without-gmp --without-libintl-prefix --without-libiconv-prefix
                  --libexecdir=/usr/lib --sysconfdir=/etc --localstatedir=/var
                  --program-transform-name=s/kill/gkill/
                  --enable-install-program=arch,hostname --enable-no-install-program=uptime)
        ;;
esac
"$output/source/configure" "${options[@]}"
make_args=()
if [[ $package == bash ]]; then
    make_args+=('LOCAL_LDFLAGS=-Wl,--export-all,--out-implib,libbash.dll.a'
                'LDFLAGS_FOR_BUILD=$(CFLAGS_FOR_BUILD)' "SHOBJ_LIBS=$PWD/libbash.dll.a")
fi
make -j"$jobs" "${make_args[@]}"
make -j1 "${make_args[@]}" DESTDIR="$output/stage" install
printf '%s\n' 'classification=bootstrap' 'build_host=windows-arm64-native-compiler' \
    'orchestration=private-x64-bootstrap-drivers' 'Native behavior/full-feature package admission remains required.' \
    > "$output/BUILD-STATUS.txt"
