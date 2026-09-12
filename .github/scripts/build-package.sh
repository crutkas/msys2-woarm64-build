#!/bin/bash

source `dirname ${BASH_SOURCE[0]}`/../../config.sh

PACKAGE_REPOSITORY=$1

if [[ "$FLAVOR" == "CROSS" ]]; then
    bash "$(dirname "${BASH_SOURCE[0]}")/verify-texinfo.sh"
fi

MAKEPKG=(makepkg)
if [[ "$PACKAGE_REPOSITORY" == *MINGW* ]]; then
    MAKEPKG=(makepkg-mingw)
fi

COMMON_ARGUMENTS=(
    --syncdeps
    --noconfirm
    --noprogressbar
    --nocheck
    --skippgpcheck
    --force
)
BUILD_ARGUMENTS=("${COMMON_ARGUMENTS[@]}" --rmdeps)

if [[ "$INSTALL_PACKAGE" = 1 ]]; then
    BUILD_ARGUMENTS+=(--install)
fi

package_name=$(basename "$PWD")
if [[ "$package_name" == "mingw-w64-cross-mingwarm64-crt" ]]; then
    PREPARE_ARGUMENTS=("${COMMON_ARGUMENTS[@]}")
    if [[ "$CLEAN_BUILD" = 1 ]]; then
        PREPARE_ARGUMENTS+=(--cleanbuild)
    fi

    echo "::group::Prepare exact CRT source"
        "${MAKEPKG[@]}" "${PREPARE_ARGUMENTS[@]}" --nobuild
    echo "::endgroup::"

    bash "$(dirname "${BASH_SOURCE[0]}")/pthread-headers-hack-before.sh" \
        "$PWD/src/mingw-w64" \
        "${WOARM64_CRT_TARGET_INCLUDE:-/opt/aarch64-w64-mingw32/include}" \
        "${WOARM64_CRT_HEADER_RECEIPT:-$PWD/crt-bootstrap-headers.json}" \
        "$PWD/PKGBUILD"
    BUILD_ARGUMENTS+=(--noextract)
elif [[ "$NO_EXTRACT" = 1 ]]; then
    BUILD_ARGUMENTS+=(--noextract)
elif [[ "$CLEAN_BUILD" = 1 ]]; then
    BUILD_ARGUMENTS+=(--cleanbuild)
fi

if command -v ccache &> /dev/null; then
    echo "::group::Ccache statistics before build"
        ccache -svv  || true
    echo "::endgroup::"
fi

echo "::group::Build package"
    "${MAKEPKG[@]}" "${BUILD_ARGUMENTS[@]}"
echo "::endgroup::"

if command -v ccache &> /dev/null; then
    echo "::group::Ccache statistics after build"
        ccache -svv || true
    echo "::endgroup::"
fi
