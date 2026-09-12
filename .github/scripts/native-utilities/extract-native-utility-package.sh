#!/bin/bash
set -euo pipefail
: "${NATIVE_UTILITY_ROOT:?A new owned output root is required}"
root=$(/usr/bin/cygpath -u "$NATIVE_UTILITY_ROOT")
export PATH=/usr/bin:/c/Windows/System32
case "${1:?Specify which or dos2unix}" in
  which) name=which; version=2.25-1 ;;
  dos2unix) name=dos2unix; version=7.5.7-1 ;;
  *) printf 'Unsupported package\n' >&2; exit 2 ;;
esac
mkdir "$root/$name/extracted"
tar -xf "$root/$name/packages/$name-$version-aarch64.pkg.tar.zst" -C "$root/$name/extracted"
