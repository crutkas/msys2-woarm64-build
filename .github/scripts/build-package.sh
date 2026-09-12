#!/bin/bash

source "$(dirname -- "${BASH_SOURCE[0]}")/../../config.sh"
SCRIPTS_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export CCACHE_DIR=${CCACHE_DIR:-"$SCRIPTS_DIR/../../ccache"}

PACKAGE_REPOSITORY=$1

ARGUMENTS=(--noconfirm --noprogressbar --force --log)
case ${VERIFY_SOURCE_SIGNATURES:-0} in
    0) ARGUMENTS+=(--skippgpcheck) ;;
    1) ;;
    *) printf 'VERIFY_SOURCE_SIGNATURES must be 0 or 1.\n' >&2; exit 1 ;;
esac
if [[ ${RESOLVE_DEPENDENCIES:-1} == 1 ]]; then
    ARGUMENTS+=(--syncdeps --rmdeps)
fi
if [[ ${RUN_CHECKS:-0} == 1 ]]; then ARGUMENTS+=(--check); else ARGUMENTS+=(--nocheck); fi
if [[ $NO_EXTRACT == 1 ]]; then ARGUMENTS+=(--noextract); fi
if [[ $CLEAN_BUILD == 1 ]]; then ARGUMENTS+=(--cleanbuild); fi
if [[ $INSTALL_PACKAGE == 1 ]]; then ARGUMENTS+=(--install); fi

bash "$SCRIPTS_DIR/record-build-provenance.sh"

if command -v ccache &> /dev/null; then
    echo "::group::Ccache statistics before build"
        ccache -svv  || true
    echo "::endgroup::"
fi

echo "::group::Build package"
    if [[ "$PACKAGE_REPOSITORY" == *MINGW* ]]; then
        bash "$SCRIPTS_DIR/with-makepkg-evidence.sh" makepkg-mingw "${ARGUMENTS[@]}"
    else
        bash "$SCRIPTS_DIR/with-makepkg-evidence.sh" makepkg "${ARGUMENTS[@]}"
    fi
echo "::endgroup::"

if command -v ccache &> /dev/null; then
    echo "::group::Ccache statistics after build"
        ccache -svv || true
    echo "::endgroup::"
fi
