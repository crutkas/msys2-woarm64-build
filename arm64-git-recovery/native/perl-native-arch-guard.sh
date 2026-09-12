#!/usr/bin/env bash

require_native_perl_arch() {
    local root=${1//\\//} machine
    machine=$("$root/usr/bin/uname.exe" -m) || {
        echo "Native uname failed before configuring Perl" >&2
        return 3
    }
    case "$machine" in
        aarch64|arm64) printf '%s\n' "$machine" ;;
        *) echo "Native uname must identify ARM64 before configuring Perl: $machine" >&2; return 3 ;;
    esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    [[ $# == 1 ]] || { echo "usage: $0 NATIVE_ROOT" >&2; exit 2; }
    require_native_perl_arch "$1"
fi
