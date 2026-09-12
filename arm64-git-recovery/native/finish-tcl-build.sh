#!/usr/bin/env bash
set -euo pipefail
[[ $# == 4 ]] || { echo "usage: $0 BUILD_ROOT TOOLCHAIN ZLIB_STAGE OUTPUT" >&2; exit 2; }
export PATH=/usr/bin
build=$(cygpath -au "$1") compiler=$(cygpath -au "$2") zlib=$(cygpath -am "$3") output=$(cygpath -am "$4")
export PATH="$compiler/bin:$build/build:/usr/bin"
cd "$build/build"
make -j1 'SHELL=/bin/bash -e' 'INSTALL=/usr/bin/install -c' "ZLIB_LIBS=$zlib/lib/libz.dll.a" \
    "ZLIB_DIR_NATIVE=$zlib/include" "ZLIB_EXTERNAL_DIR=$zlib/bin" ZLIB_DLL_FILE=libz.dll \
    "prefix=$output/stage" "exec_prefix=$output/stage" "libdir=$output/stage/lib" install
