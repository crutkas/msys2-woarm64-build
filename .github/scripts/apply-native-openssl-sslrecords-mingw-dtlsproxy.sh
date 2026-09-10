#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/test/recipes/70-test_sslrecords.t"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-sslrecords-mingw-dtlsproxy.patch"
original_sha=d032249600d558e0dadbcd3ad1e7057bff5429e13e7bf48542be300ba1b13e3c
patched_sha=fd9152c72ba64bec79a43fede525666bb70fb129e197ab3b28b3a4ec12230602

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
        echo "Unknown OpenSSL sslrecords recipe identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
