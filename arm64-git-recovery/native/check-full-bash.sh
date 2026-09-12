#!/usr/bin/env bash
set -euo pipefail
[[ $# == 4 ]] || exit 2
root=$(cygpath -u "$1") output=$(cygpath -u "$2") sdk=$(cygpath -u "$3") host=$(cygpath -u "$4")
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tc=/c/ag-e138920f/tc-cpp-guard-01
export PATH="$output/runtime/usr/bin:$sdk/usr/bin:$tc/bin:$host/usr/bin"
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export LC_ALL=C.UTF-8 MSYSTEM=CYGWIN MAKEFLAGS=-j1 MFLAGS=-j1 OMP_NUM_THREADS=1
export WOARM64_NATIVE_ARG_CONVERSION=none TERMINFO="$sdk/usr/share/terminfo"
export BASH_TEST_EVIDENCE="$output/cases"
unset BASH_ENV ENV
"$host/usr/bin/patch.exe" --batch --forward --fuzz=0 --no-backup-if-mismatch \
    -p1 -d "$root/source" -i "$here/patches/bash-5.3-record-all-tests.patch"
cd "$root/source"
"$host/usr/bin/make.exe" -j1 check \
    "THIS_SH=$output/runtime/usr/bin/bash.exe" \
    'LOCAL_LDFLAGS=-Wl,--export-all,--out-implib,libbash.dll.a' \
    'LDFLAGS_FOR_BUILD=$(CFLAGS_FOR_BUILD)' \
    "SHOBJ_LIBS=$PWD/libbash.dll.a" HISTORY_LDFLAGS= READLINE_LDFLAGS=
