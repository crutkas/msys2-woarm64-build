#!/usr/bin/env bash
set -euo pipefail
[[ $# == 3 ]] || { echo "usage: $0 COPIED_BUILD_ROOT TOOLCHAIN JOBS" >&2; exit 2; }
output=$(cygpath -u "$1") toolchain=$(cygpath -u "$2") jobs=$3
[[ $jobs =~ ^[1-8]$ ]] || { echo "Explicit approved jobs required" >&2; exit 2; }
export PATH="$output/build/.libs:$toolchain/bin:/usr/bin" LC_ALL=C
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
cd "$output/build"
make_args=("srcdir=$output/source" "top_srcdir=$output/source"
           "abs_srcdir=$output/source" "abs_top_srcdir=$output/source" "VPATH=$output/source")
make -j"$jobs" "${make_args[@]}" check-TESTS
make -j1 "${make_args[@]}" DESTDIR="$output/stage" install
mkdir -p "$output/stage/usr/share/licenses/libxcrypt"
count=0
for license in COPYING COPYING.LIB COPYING.LIB.LIBXCRYPT COPYING.LIB.LIBCRYPT COPYING.LESSER LICENSING; do
    if [[ -f "$output/source/$license" ]]; then
        cp "$output/source/$license" "$output/stage/usr/share/licenses/libxcrypt/"
        count=$((count + 1))
    fi
done
[[ $count -gt 0 ]] || { echo "Source license payload missing" >&2; exit 4; }
