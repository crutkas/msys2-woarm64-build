#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/test/recipes/15-test_dsaparam.t"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-dsaparam-crlf.patch"
original_sha=c0cbec94a5bf0d307fc22e0d36cb85e6e0b6bddf327c39a14e277197d9fe1e66
patched_sha=2059118da56028a33109e8aa63a5e95fa07562da1095d8b97f2e46a0dc937941

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
        echo "Unknown OpenSSL dsaparam recipe identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
