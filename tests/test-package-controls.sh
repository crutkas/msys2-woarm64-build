#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
temporary=$(mktemp -d)
trap 'rm -r -- "$temporary"' EXIT
mkdir -p "$temporary/hostile/build/woarm64-adapter-control/src"
printf 'must survive forced cleanbuild\n' > "$temporary/hostile/build/woarm64-adapter-control/src/sentinel"
for directory in sources source-packages logs packages; do
    mkdir -p "$temporary/hostile/$directory"
    printf 'must remain unchanged\n' > "$temporary/hostile/$directory/sentinel"
done
find "$temporary/hostile" -type f -print0 | sort -z | xargs -0 sha256sum > "$temporary/sentinels.before"

for driver in makepkg makepkg-mingw; do
for disabling in environment configuration explicit-nocheck; do
    for fail_check in 0 1; do
        output="$temporary/$driver-$disabling-$fail_check"
        mkdir -p "$output/recipe"
        cp "$root/tests/package-controls/PKGBUILD" "$output/recipe/PKGBUILD"
        {
            if [[ $driver == makepkg-mingw ]]; then
                printf 'source /etc/makepkg_mingw.conf\n'
            else
                printf 'source /etc/makepkg.conf\n'
            fi
            for binding in BUILDDIR:build SRCDEST:sources SRCPKGDEST:source-packages LOGDEST:logs PKGDEST:packages; do
                printf '%s=%q\n' "${binding%%:*}" "$temporary/hostile/${binding#*:}"
            done
            if [[ $disabling == configuration ]]; then
                printf 'BUILDENV=(!distcc color !ccache !check !sign)\n'
            fi
        } > "$output/prefix.conf"
        status=0
        (
            cd "$output/recipe"
            export BUILDDIR="$temporary/hostile/build" SRCDEST="$temporary/hostile/sources"
            export SRCPKGDEST="$temporary/hostile/source-packages" LOGDEST="$temporary/hostile/logs"
            export PKGDEST="$temporary/hostile/packages"
            export CONTROL_OUTPUT=$output CONTROL_FAIL_CHECK=$fail_check
            export FLAVOR=CROSS CLEAN_BUILD=1 RESOLVE_DEPENDENCIES=0 RUN_CHECKS=1
            unset RUN_CHECK
            if [[ $disabling == environment ]]; then export RUN_CHECK=n; fi
            check_option=--check
            if [[ $disabling == explicit-nocheck ]]; then
                export RUN_CHECK=y RUN_CHECKS=0
                check_option=--nocheck
            fi
            export MAKEPKG_CONF="$output/prefix.conf"
            source "$root/.github/scripts/set-package-directories.sh" "$output"
            if [[ $driver == makepkg-mingw ]]; then
                export FLAVOR=NATIVE_WITH_CROSS MINGW_ARCH=mingwarm64
                bash "$root/.github/scripts/with-makepkg-evidence.sh" makepkg-mingw \
                    --config "$MAKEPKG_CONF" --cleanbuild "$check_option" --force --log --noconfirm
            else
                bash "$root/.github/scripts/build-package.sh" MSYS2
            fi
        ) > "$output/driver.log" 2>&1 || status=$?
        if [[ ! -f "$output/build-reached" || ( $disabling != explicit-nocheck && ! -f "$output/check-reached" ) ]]; then
            cat "$output/driver.log"
            printf 'FAIL: requested build/check not reached for %s\n' "$disabling" >&2
            exit 1
        fi
        if [[ $disabling == explicit-nocheck ]]; then
            [[ ! -f "$output/check-reached" ]]
        fi
        if [[ $fail_check == 1 && $disabling != explicit-nocheck ]]; then
            (( status != 0 ))
            grep -F 'INTENTIONAL CHECK FAILURE' "$output/driver.log"
            [[ -z $(find "$output/packages" -type f -name '*.pkg.tar.*' -print -quit) ]]
        else
            if (( status != 0 )); then cat "$output/driver.log"; exit "$status"; fi
            [[ -n $(find "$output/packages" -type f -name '*.pkg.tar.*' -print -quit) ]]
        fi
        find "$temporary/hostile" -type f -print0 | sort -z | xargs -0 sha256sum > "$temporary/sentinels.after"
        cmp "$temporary/sentinels.before" "$temporary/sentinels.after"
        printf 'PASS: %s / %s, check-failure=%s, five destinations isolated, outside sentinels untouched\n' "$driver" "$disabling" "$fail_check"
    done
    done
done
