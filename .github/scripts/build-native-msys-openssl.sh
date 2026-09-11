#!/usr/bin/env bash
set -euo pipefail

[[ $# == 5 ]] || {
    echo "usage: $0 SOURCE PREPARE_MANIFEST TOOLCHAIN RUNTIME_SDK OUTPUT" >&2
    exit 2
}

export PATH=/usr/bin:/usr/bin/core_perl

source_root=$(cygpath -u "$1")
prepare_manifest=$(cygpath -u "$2")
toolchain=$(cygpath -u "$3")
runtime_sdk=$(cygpath -u "$4")
output=$(cygpath -u "$5")

[[ ! -e $output ]] || {
    echo "Refusing existing output: $output" >&2
    exit 2
}

declare -A expected=(
    ["$prepare_manifest"]="0c61787ce4af99d8bb404446d092835aabd31421c0c5f806b1c52918dde72ae0"
    ["$source_root/Configure"]="622e9c7013848b2b14adf5e5d20cadd5cc1555928bfcb9b9715c0099ae578e36"
    ["$source_root/Configurations/99-msys-arm64.conf"]="2b7905717aec6ad5e39adbc42e01a44e97684104eec500951615f61587470c9c"
    ["$runtime_sdk/lib/libmsys-2.0.a"]="6f19eb725d275d6e9f3564783cf5a18c9f13849b6c8033ca92291ecd3f5a735c"
    ["$runtime_sdk/lib/crt0.o"]="29b356f7105386a37bc8b16169e8beac1b0cbc2c1640946df02f85bbae5d3737"
    ["$runtime_sdk/bin/msys-2.0.dll"]="907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
)

for path in "${!expected[@]}"; do
    [[ -f $path ]] || {
        echo "Missing input: $path" >&2
        exit 3
    }
    actual=$(sha256sum "$path" | awk '{print $1}')
    [[ $actual == "${expected[$path]}" ]] || {
        echo "Hash mismatch: $path" >&2
        exit 3
    }
done

for path in \
    "$toolchain/bin/gcc.exe" \
    "$toolchain/bin/ar.exe" \
    "$toolchain/bin/ranlib.exe" \
    "$toolchain/bin/windres.exe"; do
    [[ -f $path ]] || {
        echo "Missing toolchain input: $path" >&2
        exit 3
    }
done

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export PATH="$script_dir:$toolchain/bin:/usr/bin:/usr/bin/core_perl"
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS GCC_EXEC_PREFIX COMPILER_PATH
export CXX=g++ AR=ar RANLIB=ranlib RC=windres
export MSYSTEM=CYGWIN LC_ALL=C
export MSYS2_ARG_CONV_EXCL='-DOPENSSLDIR=;-DENGINESDIR=;-DMODULESDIR='

[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]] || {
    echo "Wrong compiler target" >&2
    exit 3
}

for name in crt0.o libmsys-2.0.a; do
    resolved=$(gcc "-B$runtime_sdk/lib/" -print-file-name="$name")
    resolved_windows=$(cygpath -am "$resolved" | tr '[:upper:]' '[:lower:]')
    expected_windows=$(cygpath -am "$runtime_sdk/lib/$name" | tr '[:upper:]' '[:lower:]')
    [[ $resolved_windows == "$expected_windows" ]] || {
        echo "Compiler did not select the sealed runtime input: $name=$resolved" >&2
        exit 3
    }
done

mkdir -p "$output"
cp -a "$source_root" "$output/source"
mkdir -p "$output/temp" "$output/stage"

build_source="$output/source"

export OPENSSL_RELEASE_GCC_REAL="$toolchain/bin/gcc.exe"
export OPENSSL_RELEASE_BUILD_SOURCE="$build_source"
export OPENSSL_RELEASE_BUILD_ROOT="$output"
export CC=msys-openssl-release-gcc
export CFLAGS="-O2 -g0"
export LDFLAGS="-B$runtime_sdk/lib/ -L$runtime_sdk/lib"
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"

cd "$build_source"
exec > >(tee "$output/build.log") 2>&1

printf '%s\n' \
    "build_host=windows-arm64-native-compiler" \
    "configure_driver=windows-x64-emulated-msys" \
    "target=Cygwin-aarch64" \
    "jobs=2" \
    "prefix=/usr" \
    "openssldir=/usr/ssl" \
    "enginesdir=/usr/lib/openssl/engines-3" \
    "modulesdir=/usr/lib/ossl-modules" \
    "runtime_import_sha256=${expected[$runtime_sdk/lib/libmsys-2.0.a]}" \
    "runtime_dll_sha256=${expected[$runtime_sdk/bin/msys-2.0.dll]}"

perl ./Configure \
    --prefix=/usr \
    --openssldir=/usr/ssl \
    --libdir=lib \
    shared \
    Cygwin-aarch64

perl configdata.pm --dump > "$output/configdata.txt"
make depend
make -j2 build_sw
make -j1 DESTDIR="$output/stage" install_sw install_ssldirs

mkdir -p "$output/stage/usr/share/licenses/openssl"
cp LICENSE.txt "$output/stage/usr/share/licenses/openssl/LICENSE.txt"
cp "$runtime_sdk/bin/msys-2.0.dll" "$output/stage/usr/bin/msys-2.0.dll"

printf '%s\n' \
    "status=native-msys-openssl-canonical-built-tests-pending" \
    "source_manifest_sha256=${expected[$prepare_manifest]}" \
    "runtime_import_sha256=${expected[$runtime_sdk/lib/libmsys-2.0.a]}" \
    "runtime_dll_sha256=${expected[$runtime_sdk/bin/msys-2.0.dll]}" \
    "upstream_tests=pending-exact-byte-replay" \
    > "$output/BUILD-STATUS.txt"
