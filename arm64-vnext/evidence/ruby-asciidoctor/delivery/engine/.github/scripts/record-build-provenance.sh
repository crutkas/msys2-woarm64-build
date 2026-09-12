#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
printf 'UTC=%s\nFLAVOR=%s\n' "$(date -u --iso-8601=seconds)" "${FLAVOR:-unset}"
printf 'Qualified compiler prefix=%s\nQualified toolchain epoch=%s\n' \
    "${WOARM64_NATIVE_PREFIX:-not supplied}" "${WOARM64_TOOLCHAIN_EPOCH:-not supplied}"
uname -a
printf 'Pipeline source revision: '
if [[ -n ${WOARM64_PIPELINE_REVISION:-} ]]; then
    [[ $WOARM64_PIPELINE_REVISION =~ ^[0-9a-f]{40}$ ]]
    printf '%s (invocation snapshot; exact local bytes follow)\n' "$WOARM64_PIPELINE_REVISION"
else
    git -C "$root" rev-parse HEAD
fi
printf '%s\n' 'Pipeline inputs (including local/uncommitted files):'
sha256sum "$root"/.github/scripts/*.sh "$root"/.github/scripts/*.ps1 "$root"/patches/makepkg/*
printf 'Recipe checkout: '
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git rev-parse HEAD
else
    printf '%s\n' 'UNVERSIONED (PKGBUILD hash follows; not a pinned source checkout)'
fi
sha256sum PKGBUILD
printf '%s\n' 'Installed bootstrap/dependency packages (not a native closure assertion):'
pacman -Q
for configuration in /etc/makepkg.conf /etc/makepkg_mingw.conf /etc/makepkg_mingw.d/mingwarm64.conf; do
    [[ ! -f "$configuration" ]] || sha256sum "$configuration"
done
for tool in bash make makepkg ccache gcc g++ /mingw64/bin/gh /mingw64/bin/jq; do
    if resolved=$(type -P "$tool"); then
        [[ ! -f "$resolved.exe" ]] || resolved+=.exe
        file -L "$resolved"
        sha256sum "$resolved"
    else
        printf 'Not installed/on PATH at this phase: %s\n' "$tool"
    fi
done
