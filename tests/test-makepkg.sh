#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
command -v makepkg
temporary=$(mktemp -d)
trap 'rm -r -- "$temporary"' EXIT
cp "$root/tests/ccache/PKGBUILD" "$temporary/PKGBUILD"
cd "$temporary"
export FLAVOR=CROSS
command=(bash "$root/.github/scripts/with-makepkg-evidence.sh" makepkg --nodeps --nocheck --force --noconfirm)
if [[ ${1:-} == --build-wrapper ]]; then
    command=(bash "$root/.github/scripts/build-package.sh" MSYS2)
fi

for disabled in 0 1; do
    printf '=== Real makepkg, package !ccache=%s ===\n' "$disabled"
    status=0
    PROBE_DISABLE_CCACHE=$disabled PROBE_REQUIRE_MAKEINFO=1 \
        "${command[@]}" > "$temporary/build.log" 2>&1 || status=$?
    cat "$temporary/build.log"
    if [[ ${1:-} == --expect-missing-makeinfo && $disabled == 1 ]]; then
        (( status != 0 ))
        grep -F 'Inside actual PKGBUILD build()' "$temporary/build.log"
        grep -F 'makeinfo: command not found' "$temporary/build.log"
        printf '%s\n' 'PASS: reproduced missing makeinfo after package !ccache overrode BUILDENV'
    else
        if (( status != 0 )); then
            exit "$status"
        fi
        grep -F 'Inside actual PKGBUILD build()' "$temporary/build.log"
        printf '%s\n' 'PASS: real makepkg completed, makeinfo runnable'
    fi
done
