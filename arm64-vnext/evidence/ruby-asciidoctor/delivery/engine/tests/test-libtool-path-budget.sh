#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
guard="$root/.github/scripts/assert-libtool-path-budget.sh"

if bash "$guard" '/c/ap06-2160/restart01/build-libtool-01/build/mingw-w64-libtool/src/libtool-2.6.2'; then
    printf 'Unsafe nested DESTDIR length was accepted.\n' >&2
    exit 1
fi
bash "$guard" '/c/ap06-2160/l2/build/mingw-w64-libtool/src/libtool-2.6.2'
if bash "$guard" 'relative/source'; then
    printf 'Relative source path was accepted.\n' >&2
    exit 1
fi
printf 'PASS: native libtool nested path budget rejects long/relative paths and accepts short layout.\n'
