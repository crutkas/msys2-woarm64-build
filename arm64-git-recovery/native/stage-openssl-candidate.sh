#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || { echo "usage: $0 WINDOWS_BUILD WINDOWS_TOOLCHAIN" >&2; exit 2; }
export PATH=/usr/bin
build=$(cygpath -u "$1") toolchain=$(cygpath -u "$2")
export PATH="$toolchain/bin:/usr/bin" LC_ALL=C
cd "$build"
make -j1 install_sw install_ssldirs
mkdir -p ../stage/share/licenses/openssl
cp LICENSE.txt ../stage/share/licenses/openssl/
