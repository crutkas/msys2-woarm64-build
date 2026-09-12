#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || exit 2
output=$(cygpath -u "$1") generator=$(cygpath -u "$2")
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export PATH="/usr/bin" LC_ALL=C
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export MAKEFLAGS=-j1 MFLAGS=-j1 OMP_NUM_THREADS=1
export ACLOCAL=/usr/bin/aclocal-1.18 AUTOMAKE=/usr/bin/automake-1.18
export LIBTOOLIZE="$generator/bin/libtoolize"
export _lt_pkgdatadir="$generator/generator-data"
export ACLOCAL_PATH="$generator/generator-data/m4"
for tool in /usr/bin/autoreconf "$ACLOCAL" "$AUTOMAKE" "$LIBTOOLIZE"; do
    "$tool" --version
done
/usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch -p1 -d "$output/source" \
    -i "$here/patches/libiconv-1.19-nested-macro-path.patch"
cd "$output/source"
"$ACLOCAL" -I m4
/usr/bin/autoreconf -fiv
cd libcharset
"$ACLOCAL" -I m4 -I ../m4
/usr/bin/autoreconf -fiv
/usr/bin/bash -n configure
cd ..
/usr/bin/bash -n configure
