#!/usr/bin/env bash

openssl_native_test_uri() {
    REPLY=$1
    if [[ $1 =~ ^(file:(//(localhost)?)?)/([A-Za-z])/(.*)$ ]]; then
        if [[ ${OPENSSL_NATIVE_TEST_PROFILE:-mingw} == msys ]]; then
            REPLY="${BASH_REMATCH[1]}/cygdrive/${BASH_REMATCH[4],,}/${BASH_REMATCH[5]}"
        else
            REPLY="${BASH_REMATCH[1]}/${BASH_REMATCH[4]}:/${BASH_REMATCH[5]}"
        fi
    elif [[ $1 =~ ^(ot:|org.openssl.engine:ossltest:ot:)/([A-Za-z])/(.*)$ ]]; then
        if [[ ${OPENSSL_NATIVE_TEST_PROFILE:-mingw} == msys ]]; then
            REPLY="${BASH_REMATCH[1]}/cygdrive/${BASH_REMATCH[2],,}/${BASH_REMATCH[3]}"
        else
            REPLY="${BASH_REMATCH[1]}${BASH_REMATCH[2]}:/${BASH_REMATCH[3]}"
        fi
    elif [[ $1 =~ ^(/[A-Za-z]/[^[:space:]]+)([[:space:]]+/[A-Za-z]/[^[:space:]]+)+$ ]]; then
        while [[ $REPLY =~ (^|[[:space:]])/([A-Za-z])/ ]]; do
            REPLY=${REPLY/"${BASH_REMATCH[0]}"/"${BASH_REMATCH[1]}${BASH_REMATCH[2]}:/"}
        done
    elif [[ $1 =~ ^/([A-Za-z])/(.*)$ ]]; then
        REPLY="${BASH_REMATCH[1]}:/${BASH_REMATCH[2]}"
    fi
}
