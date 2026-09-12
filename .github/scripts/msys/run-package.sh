#!/bin/bash
set -euo pipefail

scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
output=$(cygpath -u "$WOARM64_OUTPUT_ROOT")
config=$(cygpath -u "$WOARM64_MSYS_CONFIG")
source "$scripts/../set-package-directories.sh" "$output"
export CCACHE_DIR
CCACHE_DIR=$(cygpath -u "$CCACHE_DIR")
mkdir -p "$CCACHE_DIR"
printf 'MSYS target package; bootstrap shell/make/ccache are not asserted native.\n'
makepkg --config "$config" --check --cleanbuild --log --force --noconfirm 2>&1 | tee "$output/build.log"
