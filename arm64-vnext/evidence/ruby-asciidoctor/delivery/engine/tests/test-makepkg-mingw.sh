#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
command -v makepkg-mingw
temporary=$(mktemp -d)
trap 'rm -r -- "$temporary"' EXIT
cp "$root/tests/mingwarm64/PKGBUILD" "$temporary/PKGBUILD"
cd "$temporary"

for flavor in NATIVE_WITH_NATIVE NATIVE_WITH_CROSS; do
    printf '=== Configuration only, no compiler: %s ===\n' "$flavor"
    FLAVOR=$flavor MINGW_ARCH=mingwarm64 \
        makepkg-mingw --nodeps --nocheck --force --noconfirm
done

if [[ ${1:-} == --expect-native-rejection ]]; then
    status=0
    FLAVOR=NATIVE_WITH_NATIVE MINGW_ARCH=mingwarm64 PROBE_X64_COMPILER_PATH=/usr/bin/bash \
        bash "$root/.github/scripts/with-makepkg-evidence.sh" \
        makepkg-mingw --nodeps --nocheck --force --noconfirm > "$temporary/native.log" 2>&1 || status=$?
    cat "$temporary/native.log"
    (( status != 0 ))
    grep -F 'Expected ARM64 PE machine 0xAA64, found 0x8664' "$temporary/native.log"
    if grep -F 'PASS: actual makepkg-mingw' "$temporary/native.log"; then
        printf 'FAIL: native rejection did not prevent build()\n' >&2
        exit 1
    fi
    printf '%s\n' 'PASS: known x64 executable rejected as native compiler before build()'
elif [[ ${1:-} == --native-toolchain ]]; then
    if [[ ! -d ${2:-} ]]; then
        printf 'Usage: %s --native-toolchain <ARM64 toolchain bin directory>\n' "$0" >&2
        exit 2
    fi
    FLAVOR=NATIVE_WITH_NATIVE MINGW_ARCH=mingwarm64 PROBE_NATIVE_TOOLCHAIN_BIN=$2 \
        bash "$root/.github/scripts/with-makepkg-evidence.sh" \
        makepkg-mingw --nodeps --nocheck --force --noconfirm > "$temporary/native.log" 2>&1
    cat "$temporary/native.log"
    grep -F 'PASS: actual makepkg-mingw NATIVE_WITH_NATIVE configuration' "$temporary/native.log"
    printf '%s\n' 'PASS: real ARM64 toolchain passed identity gate and reached build() (no compilation)'
fi
