#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$(cygpath -u "$1")
target="$source_root/crypto/threads_win.c"
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch_file="$here/openssl-3.6.4-windows-rcu-acquire.patch"
original_sha=0f21e5027f84594ba7dd38942d374376b35d98ec765eee572110413d1c513940
patched_sha=92581e43c25267868475689c3721b9db0db1720d5a9d4af94a07cb949d401820

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
        echo "Unknown OpenSSL Windows threads source identity: $actual" >&2
        exit 3
        ;;
esac

actual=$(sha256sum "$target")
[[ ${actual%% *} == "$patched_sha" ]]
