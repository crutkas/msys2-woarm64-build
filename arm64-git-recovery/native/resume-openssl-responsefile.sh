#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 ]] || { echo "usage: $0 BUILD TOOLCHAIN OUTPUT JOBS RECONFIGURE" >&2; exit 2; }
export PATH=/usr/bin
build=$(cygpath -au "$1") compiler=$(cygpath -au "$2") output=$(cygpath -au "$3") jobs=$4
[[ $jobs =~ ^[1-8]$ ]] || { echo "Explicit job allocation required" >&2; exit 2; }
export PATH="$compiler/bin:/usr/bin"
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export HOME="$output/home" LC_ALL=C
cd "$build/source"
[[ $5 == 0 || $5 == 1 ]] || { echo "Invalid reconfigure policy" >&2; exit 2; }
if [[ $5 == 1 ]]; then
    perl configdata.pm -r
fi
make -j"$jobs"
make -j1 install_sw install_ssldirs
mkdir -p "$build/stage/share/licenses/openssl"
cp LICENSE.txt "$build/stage/share/licenses/openssl/LICENSE.txt"
