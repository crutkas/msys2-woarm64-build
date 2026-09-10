#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/test/recipes/25-test_verify.t"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-verify-mingw-paths.patch"
original_sha=5ba87fccf8a3f9b0d65fdb442744829d9873eebe3d3ca51aa74a8da80515ecc6
patched_sha=a6dae8cadee18036bb0fdf54a944f3e33238ec127003c2b542258c54f288fbe3

actual=$(sha256sum "$target")
actual=${actual%% *}
case $actual in
    "$original_sha")
        sed 's/\r$//' "$patch_file" |
            patch --batch --forward --fuzz=0 -p1 -d "$source_root"
        ;;
    "$patched_sha")
        ;;
    *)
        echo "Unknown OpenSSL verify recipe identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
