#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/test/recipes/90-test_store.t"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-store-mingw-target.patch"
original_sha=508f089842d7cb708029f07fd63d55237c7c18063b8fede17b46a624fb3a4f82
patched_sha=434a202d70c62d823c96851e000acc14eefcaba41d20b9db77545bbd098fde65

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
        echo "Unknown OpenSSL store recipe identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
