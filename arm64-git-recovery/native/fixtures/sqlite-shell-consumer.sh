#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 && $2 =~ ^[a-z0-9-]+$ ]] || { printf 'Expected private root and run name\n' >&2; exit 2; }
output=$1
case "$output" in /c/ag-sqlite-resume-01/*) ;; *) printf 'Private work root required\n' >&2; exit 2;; esac
runtime="$output/runtime"
work="$output/work/$2"
export PATH="$runtime/usr/bin"
export HOME="$output/home" TMP="$output/temp" TEMP="$output/temp" TMPDIR="$output/temp"
export TCL_LIBRARY="$runtime/usr/lib/tcl8.6" TCLLIBPATH="$runtime/usr/lib"
export LC_ALL=C MAKEFLAGS=-j1 MFLAGS=-j1 OMP_NUM_THREADS=1
mkdir "$work"
cd "$work"
printf 'native-parent=%s\n' "$BASH_VERSION"
command -v sh awk sqlite3
test -x /bin/sh
"$runtime/usr/bin/sqlite-shell-pipe.exe"
"$runtime/usr/bin/sqlite3.exe" -batch "$work/import.sqlite" \
    ".read $output/inputs/shell5-import.sql"
"$runtime/usr/bin/tclsh8.6.exe" "$output/inputs/sqlite-tdbc-consumer.tcl" \
    "$work/tdbc-candidate.sqlite"
printf '%s\n' native-msys-sqlite-shell-consumer-passed
