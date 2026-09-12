#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || exit 2
root=$(cygpath -u "$1") output=$(cygpath -u "$2")
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tc=/c/ag-e138920f/tc-cpp-guard-01
dependency=/c/ag-readline-e138-01/ncurses-static-cxx-01/stage
native_python=$(cygpath -u "$WOARM64_NATIVE_PYTHON")
export PATH="$root/build/src/.libs:$dependency/usr/bin:$tc/bin:/usr/bin"
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export LC_ALL=C MSYSTEM=CYGWIN MAKEFLAGS=-j2 MFLAGS=-j2 OMP_NUM_THREADS=1
export TERMINFO="$dependency/usr/share/terminfo" WOARM64_NATIVE_ARG_CONVERSION=none
/usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch -p1 -d "$root/source" \
    -i "$here/patches/libedit-20240808-display-cells.patch"
"$native_python" -B "$here/finish-libedit-wide.py" --validate-working
cd "$root/build"
make -j2
make -j2 check
make -j1 DESTDIR="$root/stage" install
install -Dm644 "$root/source/COPYING" "$root/stage/usr/share/licenses/libedit/LICENSE"
