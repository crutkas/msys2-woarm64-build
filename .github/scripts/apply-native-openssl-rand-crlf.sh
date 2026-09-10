#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/test/recipes/05-test_rand.t"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-rand-crlf.patch"
original_sha=c556ab5c62a04e19201a67e4e5f52652d1281b0c1f57aa4c95440245eb98f339
patched_sha=85e94fcaa41c50d672b95fbc2f1be84273aae00e29c3980db673036ffa1ef27b

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
        echo "Unknown OpenSSL rand recipe identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
