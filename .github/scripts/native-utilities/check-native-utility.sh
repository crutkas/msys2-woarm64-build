#!/bin/bash
set -euo pipefail
: "${NATIVE_UTILITY_ROOT:?A new owned output root is required}"
root=$(/usr/bin/cygpath -u "$NATIVE_UTILITY_ROOT")
export PATH="$root/compiler/bin:/usr/bin:/usr/bin/core_perl:/usr/bin/vendor_perl:/c/Windows/System32"
export MSYS2_ARG_CONV_EXCL='*' MAKEFLAGS=-j1 LC_ALL=C.UTF-8
case "${1:?Specify which or dos2unix}" in
  which)
    cd "$root/which/src/build-aarch64-pc-cygwin"
    make check
    ;;
  dos2unix)
    cd "$root/dos2unix/src/dos2unix-7.5.7"
    sdk=$(/usr/bin/cygpath -am "$root/sdk/usr")
    compiler="$root/compiler/bin/aarch64-pc-cygwin-gcc.exe"
    : "${NATIVE_UTILITY_TRANSPORT_LOG:?A new owned native argv transport log is required}"
    driver=$(/usr/bin/cygpath -u "$NATIVE_UTILITY_TRANSPORT_DIRECTORY")
    make CC="$compiler" CPP="$compiler -E" \
      LDFLAGS_USER="-L$sdk/lib -Wl,--no-insert-timestamp -Wl,-t" \
      PROVE_OPT="--nocolor --exec='/usr/bin/perl -I$driver -MNativeUtilityTransport'" check
    ;;
  *) printf 'Unsupported package\n' >&2; exit 2 ;;
esac
