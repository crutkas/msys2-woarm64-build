#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || exit 2
root=$(cygpath -u "$1") output=$(cygpath -u "$2")
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export PATH="/c/ag-e138920f/tc-cpp-guard-01/bin:/usr/bin"
export MAKEFLAGS=-j1 MFLAGS=-j1 OMP_NUM_THREADS=1 WOARM64_NATIVE_ARG_CONVERSION=none
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
cd "$root/build/c++"
make -j1 -f Makefile -f "$here/ncurses-static-cxx.mk" \
    "STATIC_CXX_DIR=$output/objects" chain-static-cxx
