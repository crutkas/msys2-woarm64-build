#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || {
    echo "usage: $0 OPENSSL_SOURCE_ROOT" >&2
    exit 2
}

source_root=$1
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

patches=(
    bioprint-width
    mingw-symbol-presence
    mingw-errstr-host-crt
    rand-crlf
    dsaparam-crlf
    ml-dsa-codecs-text
    ml-kem-codecs-text
    pkey-crlf
    dhparam-crlf
    pkeyutl-tap-output
    speed-mingw-multi
    eai-mingw-utf8
    pkcs8-crlf
    verify-mingw-paths
    x509-mingw-text
    sslrecords-mingw-dtlsproxy
    cmp-http-mingw-target
    ocsp-lifecycle
    store-mingw-target
    windows-rcu-acquire
)

for patch in "${patches[@]}"; do
    bash "$here/apply-native-openssl-$patch.sh" "$source_root"
done
