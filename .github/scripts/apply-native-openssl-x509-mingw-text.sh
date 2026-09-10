#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/test/recipes/25-test_x509.t"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-x509-mingw-text.patch"
original_sha=bfa53afa582370a97ae75459e2506020c67bef6f621257ba217d2dfbcb49eddd
patched_sha=a209c9edcc943f2d7f81097791a49e2402006a6aa6859fb1fd662ee82706ca51

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
        echo "Unknown OpenSSL x509 recipe identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
