#!/bin/bash
set -euo pipefail

source_root=${1:?Pass the absolute libtool source/build directory}
case $source_root in
    /*) ;;
    *) printf 'Libtool path-budget check requires an absolute MSYS path.\n' >&2; exit 1 ;;
esac

# The low-command-length suite nests another suite and repeats its absolute
# installation prefix underneath DESTDIR. Native binutils still use MAX_PATH.
inner="$source_root/tests/testsuite.dir/187/tests/testsuite.dir/110"
candidate="$inner/dest$inner/inst/lib/liba1dep.dll.a"
windows_path=$(cygpath -am "$candidate")
if (( ${#windows_path} > 240 )); then
    printf 'Libtool nested DESTDIR path would be %d characters (limit 240 with native-tool margin).\n' "${#windows_path}" >&2
    printf 'Choose a shorter fresh package OutputDirectory; inputs and tests must not be altered.\n' >&2
    exit 1
fi
printf 'Libtool nested DESTDIR path budget: %d/240 characters.\n' "${#windows_path}"
