#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || exit 2
source_root=$(cygpath -u "$1")
test_file="$source_root/test/recipes/82-test_ocsp_cert_chain.t"
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
patch_file="$script_dir/openssl-3.6.4-native-ocsp-lifecycle.patch"
original_sha=924b413e933d24683d2e0e58fddd9c0be563f1e2035e06697f8c66a5a48ce166
patched_sha=ab0136c9734bd7f396fe49e5488afe13ddd2a7b4a49709953603a1c80b621adb

actual_sha=$(sha256sum "$test_file")
actual_sha=${actual_sha%% *}
case "$actual_sha" in
    "$original_sha")
        patch --fuzz=0 -d "$source_root" -p1 < "$patch_file"
        ;;
    "$patched_sha")
        ;;
    *)
        echo "Unexpected OpenSSL OCSP recipe identity: $actual_sha" >&2
        exit 3
        ;;
esac

actual_sha=$(sha256sum "$test_file")
actual_sha=${actual_sha%% *}
[[ $actual_sha == "$patched_sha" ]] || {
    echo "OpenSSL OCSP lifecycle patch produced an unexpected recipe" >&2
    exit 3
}
