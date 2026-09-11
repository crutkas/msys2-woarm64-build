#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 MINGW_W64_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/mingw-w64-headers/include/psdk_inc/intrin-impl.h"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/mingw-w64-arm64-interlocked-exchange-ordering.patch"
original_sha=b4b1ac36669b315ebdcee4d4e01731419e714a9663174467fe4adb1da1ca2a29
patched_sha=8e0d3b2f2f94969faf166d8d9a0d4eb5e358a32be6bd7e99fc76e552ebfc909a

actual=$(sha256sum "$target")
actual=${actual%% *}
case $actual in
    "$original_sha")
        normalized_patch=$(mktemp)
        trap 'rm -f "$normalized_patch"' EXIT
        sed 's/\r$//' "$patch_file" >"$normalized_patch"
        git -C "$source_root" apply --check "$normalized_patch"
        git -C "$source_root" apply "$normalized_patch"
        ;;
    "$patched_sha")
        ;;
    *)
        echo "Unknown MinGW-w64 intrinsic header identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
