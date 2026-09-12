#!/usr/bin/env bash
set -euo pipefail
[[ $# == 3 ]] || { echo "usage: $0 BUILD_ROOT TOOLCHAIN ZLIB_STAGE" >&2; exit 2; }
export PATH=/usr/bin
build=$(cygpath -au "$1") compiler=$(cygpath -au "$2") zlib=$(cygpath -am "$3")
export PATH="$compiler/bin:/usr/bin"
cd "$build/build"
exec make -n -k -j1 'SHELL=/bin/bash -e' "ZLIB_LIBS=$zlib/lib/libz.dll.a" \
    "ZLIB_DIR_NATIVE=$zlib/include" "ZLIB_EXTERNAL_DIR=$zlib/bin" \
    ZLIB_DLL_FILE=libz.dll binaries tcltest
