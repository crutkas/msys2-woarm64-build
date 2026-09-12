#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 4 && $# -le 6 ]] || { echo "usage: $0 WINDOWS_SOURCE WINDOWS_NATIVE_TOOLCHAIN WINDOWS_OUTPUT APPROVED_JOBS [TARGET] [all|deferred]" >&2; exit 2; }
source_root=$(cygpath -u "$1")
toolchain=$(cygpath -u "$2")
output=$(cygpath -u "$3")
jobs=$4
target=${5:-mingwarm64}
tests=${6:-all}
[[ $tests == all || $tests == deferred ]] || { echo "Unknown test policy" >&2; exit 2; }
[[ $jobs =~ ^[1-8]$ ]] || { echo "Explicit 1-8 job allocation required" >&2; exit 2; }
[[ ! -e $output ]] || { echo "Refusing existing build output" >&2; exit 2; }
for path in "$source_root/Configure" "$toolchain/bin/gcc.exe" "$toolchain/bin/ar.exe"; do
    [[ -f $path ]] || { echo "Missing input: $path" >&2; exit 3; }
done
export PATH="$toolchain/bin:/usr/bin"
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib RC=windres
export LC_ALL=C
case "$target" in
    mingwarm64) expected=aarch64-w64-mingw32 ;;
    Cygwin-aarch64) expected=aarch64-pc-cygwin ;;
    *) echo "Unknown OpenSSL ABI target" >&2; exit 2 ;;
esac
[[ $(gcc -dumpmachine) == "$expected" ]] || { echo "Wrong compiler target" >&2; exit 3; }
mkdir -p "$output"
cp -a "$source_root" "$output/source"
mkdir -p "$output/temp" "$output/stage"
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
cd "$output/source"
exec > >(tee "$output/build.log") 2>&1
printf 'build_host=windows-arm64-native-compiler; configure_driver=windows-x64-emulated-msys\n'
type -a gcc perl make
perl ./Configure "$target" shared \
    --libdir=lib \
    --prefix="$(cygpath -m "$output/stage")" \
    --openssldir="$(cygpath -m "$output/stage/ssl")"
perl configdata.pm --dump > "$output/configdata.txt"
make -j"$jobs"
if [[ $tests == all ]]; then
    HARNESS_JOBS="$jobs" make test
fi
make -j1 install_sw install_ssldirs
mkdir -p "$output/stage/share/licenses/openssl"
cp LICENSE.txt "$output/stage/share/licenses/openssl/LICENSE.txt"
printf '%s\n' "status=built-test-policy-$tests-not-distribution" \
    'build_host=windows-arm64-native-compiler' \
    'configure_driver=windows-x64-emulated-msys' \
    'Native Perl/make replay and relocated TLS configuration remain distribution gates.' > "$output/BUILD-STATUS.txt"
