#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
baseline=${1:?Pass the preserved version-1 source snapshot}
[[ -f "$baseline/.github/scripts/build-package.sh" ]]
temporary=$(mktemp -d)
trap 'rm -r -- "$temporary"' EXIT
export GIT_DIR
GIT_DIR=$(git -C "$root" rev-parse --absolute-git-dir)
export GIT_WORK_TREE=$baseline
export FLAVOR=CROSS CLEAN_BUILD=1 RESOLVE_DEPENDENCIES=0 RUN_CHECKS=1 CONTROL_FAIL_CHECK=1

for disabling in environment configuration; do
    export CONTROL_OUTPUT="$temporary/$disabling"
    mkdir -p "$CONTROL_OUTPUT/recipe"
    cp "$root/tests/package-controls/PKGBUILD" "$CONTROL_OUTPUT/recipe/PKGBUILD"
    export MAKEPKG_CONF="$CONTROL_OUTPUT/prefix.conf"
    printf 'source /etc/makepkg.conf\n' > "$MAKEPKG_CONF"
    unset RUN_CHECK
    if [[ $disabling == environment ]]; then
        export RUN_CHECK=n
    else
        printf 'BUILDENV=(!distcc color !ccache !check !sign)\n' >> "$MAKEPKG_CONF"
    fi
    (
        cd "$CONTROL_OUTPUT/recipe"
        # Isolate the check bug; destination safety is controlled by the v2 binder.
        source "$root/.github/scripts/set-package-directories.sh" "$CONTROL_OUTPUT"
        bash "$baseline/.github/scripts/build-package.sh" MSYS2
    ) > "$CONTROL_OUTPUT/baseline.log" 2>&1
    [[ -f "$CONTROL_OUTPUT/build-reached" && ! -e "$CONTROL_OUTPUT/check-reached" ]]
    [[ -n $(find "$CONTROL_OUTPUT/packages" -type f -name '*.pkg.tar.*' -print -quit) ]]
    printf 'REPRODUCED: v1 silently packaged with failing check skipped under %s disabling input\n' "$disabling"
done
