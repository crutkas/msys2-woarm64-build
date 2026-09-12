#!/bin/bash
set -euo pipefail
: "${NATIVE_UTILITY_ROOT:?A new owned output root is required}"
export PATH=/usr/bin:/c/Windows/System32
root=$(/usr/bin/cygpath -u "$NATIVE_UTILITY_ROOT")
case "${1:?Specify which or dos2unix}" in
  which)
    tar -xf "$root/inputs/which-2.25.tar.gz" -C "$root/which/src"
    cp "$root/inputs/msys2-allow-windows-mixed-absolute-paths.patch" "$root/which/src"
    ;;
  dos2unix)
    tar -xf "$root/inputs/dos2unix-7.5.7.tar.gz" -C "$root/dos2unix/src"
    ;;
  *) printf 'Unsupported package\n' >&2; exit 2 ;;
esac
