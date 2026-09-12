#!/usr/bin/env bash
set -euo pipefail
bindir=$(cd -- "$(dirname -- "$0")" && pwd -P)
target=aarch64-pc-cygwin
case ${0##*/} in
  msys2-gcc) compiler=$bindir/$target-gcc ;;
  msys2-g++) compiler=$bindir/$target-g++ ;;
  *) printf 'Unknown hosted MSYS wrapper: %s\n' "$0" >&2; exit 1 ;;
esac
version=$("$compiler" -dumpversion)
sysroot=$bindir/../$target
specs=$bindir/../lib/gcc/$target/$version/msys2.specs
if [[ ! -s $specs || ! -s $sysroot/include/c++/$version/iostream ||
      ! -s $sysroot/lib/libstdc++.a || ! -x $sysroot/bin/ld ]]; then
  printf 'Incomplete hosted MSYS cross SDK at %s\n' "$bindir/.." >&2
  exit 1
fi
# The preserved POSIX helper was configured against an external bootstrap
# sysroot and absolute as/ld paths. Select this paired SDK, not that old root.
exec "$compiler" "--sysroot=$sysroot" "-B$sysroot/bin/" "-specs=$specs" "$@"
