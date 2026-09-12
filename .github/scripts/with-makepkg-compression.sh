#!/bin/bash
set -euo pipefail

if (( $# == 0 )); then
    printf 'Usage: %s makepkg [arguments...]\n' "$0" >&2
    exit 2
fi
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$scripts/makepkg-compression-policy.sh"
validate_woarm64_compression_policy
if [[ -z ${WOARM64_JOBS+x} ]]; then
    exec "$@"
fi
library=${MAKEPKG_LIBRARY:-/usr/share/makepkg}
if [[ ! -f "$library/util/compress.sh" ]]; then
    printf 'Missing libmakepkg compression library: %s\n' "$library" >&2
    exit 1
fi
temporary=$(mktemp -d)
trap 'rm -r -- "$temporary"' EXIT
cp -a -- "$library" "$temporary/makepkg"
install_woarm64_compression_policy "$temporary/makepkg" "$scripts"
export MAKEPKG_LIBRARY="$temporary/makepkg"
"$@"
