#!/usr/bin/env bash
set -euo pipefail
[[ $# == 3 ]] || { printf 'Expected private output, runtime and source paths\n' >&2; exit 2; }
output=$1 runtime=$2 source=$3
case "$output" in /c/ag-sqlite-resume-01/*) ;; *) exit 2;; esac
export PATH="$runtime/usr/bin"
export HOME="$output/home" TMP="$output/temp" TEMP="$output/temp" TMPDIR="$output/temp"
export TCL_LIBRARY="$runtime/usr/lib/tcl8.6" TCLLIBPATH="$runtime/usr/lib"
export LC_ALL=C MAKEFLAGS=-j1 MFLAGS=-j1 OMP_NUM_THREADS=1
cd "$output/work"
exec "$output/bin/testfixture.exe" "$source/test/shell5.test" \
    --verbose=file "--output=$output/shell5-verbose.txt"
