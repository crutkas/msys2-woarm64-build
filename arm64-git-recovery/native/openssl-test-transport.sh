#!/usr/bin/env bash
set -euo pipefail
: "${OPENSSL_NATIVE_TEST_ROOT:?need the original unmodified OpenSSL build root}"
script_path=${BASH_SOURCE[0]//\\//}
source "${script_path%/*}/openssl-test-uris.sh"
args=()
previous=
for arg in "$@"; do
    if [[ $previous =~ ^-(passin|passout|password|pass)$ && $arg =~ ^file:/([A-Za-z])/(.*)$ ]]; then
        REPLY="file:${BASH_REMATCH[1]}:/${BASH_REMATCH[2]}"
    else
        openssl_native_test_uri "$arg"
    fi
    args+=("$REPLY")
    previous=$arg
done
export MSYS2_ARG_CONV_EXCL='*'
if [[ ${OPENSSL_NATIVE_TEST_PROFILE:-mingw} == msys && ${args[0],,} == *.exe ]]; then
    : "${OPENSSL_NATIVE_TEST_PYTHON:?need explicit native Windows Python}"
    bridge=$(cygpath -m "${script_path%/*}/openssl-native-exec.py")
    exec "$OPENSSL_NATIVE_TEST_PYTHON" "$bridge" "${args[@]}"
fi
exec /usr/bin/perl "$OPENSSL_NATIVE_TEST_ROOT/util/wrap.pl" "${args[@]}"
