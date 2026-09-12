#!/bin/bash
set -euo pipefail

if (( $# == 0 )); then
    printf 'Usage: %s makepkg[-mingw] [arguments...]\n' "$0" >&2
    exit 2
fi

export WOARM64_SCRIPTS
WOARM64_SCRIPTS=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$WOARM64_SCRIPTS/makepkg-compression-policy.sh"
validate_woarm64_compression_policy
library=${MAKEPKG_LIBRARY:-/usr/share/makepkg}
if [[ ! -f "$library/buildenv/compiler.sh" || ! -f "$library/buildenv.sh" ]]; then
    printf 'Missing libmakepkg build environment in %s; install MSYS2 pacman first.\n' "$library" >&2
    exit 1
fi

# A per-invocation copy avoids modifying pacman's library or a sibling build.
temporary=$(mktemp -d)
trap 'rm -r -- "$temporary"' EXIT
cp -a -- "$library" "$temporary/makepkg"
install_woarm64_compression_policy "$temporary/makepkg" "$WOARM64_SCRIPTS"
install -m644 "$WOARM64_SCRIPTS/makepkg-buildenv.sh" "$temporary/makepkg/buildenv/zz-woarm64-evidence.sh"
export MAKEPKG_LIBRARY="$temporary/makepkg"
"$@"
