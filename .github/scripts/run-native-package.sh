#!/bin/bash
set -euo pipefail

scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export WOARM64_NATIVE_PREFIX
WOARM64_NATIVE_PREFIX=$(cygpath -u "$WOARM64_NATIVE_PREFIX")
export CCACHE_DIR
CCACHE_DIR=$(cygpath -u "$CCACHE_DIR")
source "$scripts/set-package-directories.sh" "$(cygpath -u "$WOARM64_OUTPUT_ROOT")"
log=$(cygpath -u "$WOARM64_BUILD_LOG")
bash "$scripts/build-package.sh" MINGW 2>&1 | tee "$log"
