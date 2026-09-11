#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 MINGW_W64_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/mingw-w64-headers/crt/_mingw.h.in"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/mingw-w64-arm64-fastfail-c89-inline.patch"
original_sha=eeef89bcc19b9449fb67aa54ef0d5048dedd70464ad231281e250cd5699285e6
patched_sha=73f341f1783674ce3cd7c58a4e4aa545ece9f8e16e81474b0b0ac4f3fbd3f633

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
        echo "Unknown MinGW-w64 fastfail header identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
