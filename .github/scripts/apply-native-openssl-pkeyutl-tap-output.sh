#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/test/recipes/20-test_pkeyutl.t"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-pkeyutl-tap-output.patch"
original_sha=8025c8da8fabcba9f4dee4d63ecc3c493e5ac39120a15050f9ae8178c277b5c1
patched_sha=56e5b534323d897dcf1d51c775841da1b801bced63bfa4960f29f64e15d24b9e

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
        echo "Unknown OpenSSL pkeyutl recipe identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
