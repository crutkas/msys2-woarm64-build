#!/usr/bin/env bash
set -euo pipefail
root=$(/usr/bin/cygpath.exe -u "$1")
export PATH="$root/bootstrap/usr/bin"
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export LC_ALL=C MAKEFLAGS=-j1 MFLAGS=-j1
export AUTOCONF="$root/bootstrap/usr/bin/autoconf-2.72"
export AUTOHEADER="$root/bootstrap/usr/bin/autoheader-2.72"
export AUTOM4TE="$root/bootstrap/usr/bin/autom4te-2.72"
export AUTOMAKE="$root/bootstrap/usr/bin/automake-1.17"
export ACLOCAL="$root/bootstrap/usr/bin/aclocal-1.17"
driver_dir=$(cd "$(dirname "$0")" && pwd)
cd "$root/test-tools/expect-source/expect5.45.4"
patch -p2 < "$root/downloads/5.45-openpty.patch"
patch -p1 < "$driver_dir/patches/expect-5.45.4-declared-configure-probes.patch"
patch -p1 < "$driver_dir/patches/expect-5.45.4-tcl-delete-proc-type.patch"
patch -p1 < "$driver_dir/patches/expect-5.45.4-c23-interfaces.patch"
patch -p1 < "$driver_dir/patches/expect-5.45.4-cygwin-stty-stdin.patch"
"$root/bootstrap/usr/bin/autoreconf-2.72" -vfi
cd "$root/test-tools/dejagnu-source/dejagnu-1.6.3"
patch -p1 < "$root/downloads/0001-PATCH-Add-lregex-to-unit-target.patch"
patch -p1 < "$root/downloads/0002-Remove-redundant-ESC-escape-characters.patch"
"$root/bootstrap/usr/bin/autoreconf-2.72" -vfi
