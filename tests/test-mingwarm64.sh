#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
for flavor in NATIVE_WITH_NATIVE NATIVE_WITH_CROSS; do
    (
        export FLAVOR=$flavor
        PATH=/usr/bin:/bin
        source "$root/patches/makepkg/MINGWARM64"
        source "$root/patches/makepkg/mingwarm64.conf"
        [[ $CARCH == aarch64 && $CHOST == aarch64-w64-mingw32 ]]
        [[ $MINGW_PREFIX == /mingwarm64 && $MINGW_PACKAGE_PREFIX == mingw-w64-aarch64 ]]
        if [[ $flavor == NATIVE_WITH_NATIVE ]]; then
            [[ $CC == gcc && $CXX == g++ && $PATH == /usr/bin:/bin ]]
        else
            [[ $CC == aarch64-w64-mingw32-gcc && $CXX == aarch64-w64-mingw32-g++ ]]
            [[ $PATH == /opt/aarch64-w64-mingw32/bin:/opt/bin:/mingw64/bin:/usr/bin:/bin ]]
            bash -c '[[ $STRIP == aarch64-w64-mingw32-strip && $OBJCOPY == aarch64-w64-mingw32-objcopy ]]'
        fi
        printf 'PASS: %s configuration and exported tools\n' "$flavor"
    )
done

if (FLAVOR=invalid source "$root/patches/makepkg/mingwarm64.conf"); then
    printf 'FAIL: invalid flavor was accepted\n' >&2
    exit 1
fi
printf 'PASS: invalid flavor rejected\n'
