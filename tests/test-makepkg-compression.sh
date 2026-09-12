#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
output=${1:?Pass a new owned absolute MSYS output directory}
entry=${2:-evidence}
[[ $entry == evidence || $entry == msys || $entry == mingw ]]
[[ $output == /* && ! -e $output ]]
command -v makepkg
command -v xz
command -v zstd
mkdir -p "$output"
original=$(sha256sum /usr/share/makepkg/util/compress.sh)
wrapper="$root/.github/scripts/with-makepkg-compression.sh"
export WOARM64_JOBS=2 SOURCE_DATE_EPOCH=1788000000
export XZ_OPT=-T0 XZ_DEFAULTS=-T0 ZSTD_NBTHREADS=99

for format in xz zst; do
    for iteration in 1 2; do
        invocation="$output/$format"
        mkdir -p "$invocation/recipe" "$invocation/home" "$invocation/tmp" "$invocation/packages" "$invocation/sources"
        cp "$root/tests/compression/PKGBUILD" "$invocation/recipe"
        (
            cd "$invocation/recipe"
            export HOME="$invocation/home" TMPDIR="$invocation/tmp"
            export PKGDEST="$invocation/packages" SRCPKGDEST="$invocation/sources"
            export PKGEXT=".pkg.tar.$format" SRCEXT=".src.tar.$format"
            # Cross bootstrap flavor exercises the actual evidence wrapper
            # without claiming any native compiler/toolchain qualification.
            if [[ $entry == evidence ]]; then
                FLAVOR=CROSS bash "$root/.github/scripts/with-makepkg-evidence.sh" \
                    makepkg --config /etc/makepkg.conf --check --force --noconfirm > "$invocation/package-$iteration.log" 2>&1
            elif [[ $entry == mingw ]]; then
                FLAVOR=NATIVE_WITH_CROSS MINGW_ARCH=mingwarm64 \
                    bash "$root/.github/scripts/with-makepkg-evidence.sh" \
                    makepkg-mingw --check --force --noconfirm > "$invocation/package-$iteration.log" 2>&1
            else
                export WOARM64_OUTPUT_ROOT=$invocation WOARM64_MSYS_CONFIG=/etc/makepkg.conf CCACHE_DIR="$invocation/ccache"
                bash "$root/.github/scripts/msys/run-package.sh" > "$invocation/package-$iteration.log" 2>&1
            fi
            bash "$wrapper" makepkg --config /etc/makepkg.conf --source --force --noconfirm > "$invocation/source-$iteration.log" 2>&1
        )
        for kind in package source; do
            grep -F 'WOARM64 compression (' "$invocation/$kind-$iteration.log"
            if grep -E '^WOARM64 compression .* (-T0|--threads=0)( |$)' "$invocation/$kind-$iteration.log"; then
                printf 'Unbounded compressor reached archive creation.\n' >&2
                exit 1
            fi
        done
        archive=("$invocation/packages/"*.pkg.tar."$format")
        source_archive=("$invocation/sources/"*.src.tar."$format")
        [[ ${#archive[@]} == 1 && ${#source_archive[@]} == 1 ]]
        bsdtar -xOf "${archive[0]}" usr/share/woarm64-compression-control/payload.txt |
            grep -Fx 'real makepkg archive payload'
        bsdtar -xOf "${source_archive[0]}" woarm64-compression-control/PKGBUILD |
            cmp - "$root/tests/compression/PKGBUILD"
        if [[ $format == xz ]]; then
            xz --test "${archive[0]}" "${source_archive[0]}"
        else
            zstd --quiet --test "${archive[0]}" "${source_archive[0]}"
        fi
        if [[ $iteration == 1 ]]; then
            mkdir "$invocation/first"
            cp "${archive[0]}" "${source_archive[0]}" "$invocation/first"
        else
            cmp "${archive[0]}" "$invocation/first/${archive[0]##*/}"
        fi
    done
done
(
    cd "$output/xz/recipe"
    export HOME="$output/xz/home" TMPDIR="$output/xz/tmp"
    export SRCEXT=.src.tar.xz SRCPKGDEST="$output/rejected"
    mkdir "$SRCPKGDEST"
    status=0
    PROBE_OPAQUE_COMPRESSOR=1 bash "$wrapper" makepkg --config /etc/makepkg.conf \
        --source --force --noconfirm > "$output/rejected.log" 2>&1 || status=$?
    (( status != 0 ))
    grep -F 'Cannot bound xz compression through an unrecognized command: env' "$output/rejected.log"
    for rejected in "$SRCPKGDEST/"*; do
        if [[ -s "$rejected" ]]; then
            printf 'Rejected compressor yielded a nonempty fallback archive.\n' >&2
            exit 1
        fi
    done
)
[[ $(sha256sum /usr/share/makepkg/util/compress.sh) == "$original" ]]
printf 'PASS: real package/source archives use bounded compressors and round-trip; fixed-path binary packages repeat byte-for-byte\n'
