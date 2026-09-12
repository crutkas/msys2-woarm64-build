#!/usr/bin/env bash
set -euo pipefail
script_path=${BASH_SOURCE[0]//\\//}
source "${script_path%/*}/openssl-test-uris.sh"
passed=0
export OPENSSL_NATIVE_TEST_PROFILE=mingw
check() {
    openssl_native_test_uri "$1"
    if [[ $REPLY != "$2" ]]; then
        printf 'URI transport mismatch: %q => %q, expected %q\n' "$1" "$REPLY" "$2" >&2
        exit 1
    fi
    passed=$((passed+1))
}
check 'file:/c/a.pem' 'file:/c:/a.pem'
check 'file:///C/dir with spaces/a.pem' 'file:///C:/dir with spaces/a.pem'
check 'file://localhost/d/a.pem' 'file://localhost/d:/a.pem'
check 'ot:/c/a.pem' 'ot:c:/a.pem'
check 'org.openssl.engine:ossltest:ot:/C/a.pem' 'org.openssl.engine:ossltest:ot:C:/a.pem'
check '/c/a.pem' 'c:/a.pem'
check '/c/dir with spaces/a.pem' 'c:/dir with spaces/a.pem'
check '/c/a.der /D/b.der' 'c:/a.der D:/b.der'
for unchanged in '' 'file:relative.pem' 'file:///c:/a.pem' 'file://remote/c/a.pem' \
    'file://localhost/not-a-drive/a.pem' 'https://host/c/a.pem' '/CN=fixture/O=local' \
    'ot:relative.pem' 'ot:c:/a.pem' 'file:/etc/ssl/a.pem' \
    'org.openssl.engine:unknown:ot:/c/a.pem' 'file:/cc/a.pem' '//path///component/'; do
    check "$unchanged" "$unchanged"
done
export OPENSSL_NATIVE_TEST_PROFILE=msys
check 'file:/c/a.pem' 'file:/cygdrive/c/a.pem'
check 'file:///C/dir with spaces/a.pem' 'file:///cygdrive/c/dir with spaces/a.pem'
check 'file://localhost/d/a.pem' 'file://localhost/cygdrive/d/a.pem'
check 'ot:/c/a.pem' 'ot:/cygdrive/c/a.pem'
check 'org.openssl.engine:ossltest:ot:/C/a.pem' 'org.openssl.engine:ossltest:ot:/cygdrive/c/a.pem'
check '/c/a.pem' 'c:/a.pem'
check 'file://remote/c/a.pem' 'file://remote/c/a.pem'
check '/CN=fixture/O=local' '/CN=fixture/O=local'
printf 'URI transport controls passed: %s\n' "$passed"
