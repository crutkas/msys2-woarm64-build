#!/usr/bin/env bash
set -euo pipefail
bindir=$(cd -- "$(dirname -- "$0")" && pwd -P)
case ${0##*/} in
  msys2-gcc) compiler=$bindir/aarch64-pc-cygwin-gcc ;;
  msys2-g++) compiler=$bindir/aarch64-pc-cygwin-g++ ;;
  *) printf 'Unknown MSYS compiler wrapper name: %s\n' "$0" >&2; exit 1 ;;
esac
version=$("$compiler" -dumpversion)
specs=$bindir/../lib/gcc/aarch64-pc-cygwin/$version/msys2.specs
[[ -s $specs ]] || { printf 'Missing MSYS application specs: %s\n' "$specs" >&2; exit 1; }
exec "$compiler" "-specs=$specs" "$@"
