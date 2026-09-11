#!/bin/bash

buildenv_functions+=('buildenv_woarm64_evidence')

buildenv_woarm64_evidence() {
    if [[ -n ${WOARM64_NATIVE_PREFIX:-} ]]; then
        if [[ ${FLAVOR:-} != NATIVE_WITH_NATIVE || ! ${WOARM64_TOOLCHAIN_EPOCH:-} =~ ^[0-9a-f]{64}$ ]]; then
            printf 'Qualified native prefix requires NATIVE_WITH_NATIVE and a verified 64-digit epoch.\n' >&2
            exit 1
        fi
        # makepkg-mingw starts a login shell and sources its config. Set these
        # after that reset, keeping package installation separate from the compiler.
        export PATH="$WOARM64_NATIVE_PREFIX/bin:$PATH"
        if check_buildoption ccache y; then
            export PATH="/usr/lib/ccache/bin:$PATH"
        fi
        export CC=gcc CXX=g++ AR=ar AS=as LD=ld RANLIB=ranlib
        export RC=windres WINDRES=windres STRIP=strip OBJCOPY=objcopy OBJDUMP=objdump
    fi
    if [[ -n ${WOARM64_JOBS:-} ]]; then
        if [[ ! $WOARM64_JOBS =~ ^[1-9][0-9]*$ ]]; then
            printf 'Invalid WOARM64_JOBS: %s\n' "$WOARM64_JOBS" >&2
            exit 1
        fi
        export MAKEFLAGS="-j$WOARM64_JOBS"
        export CMAKE_BUILD_PARALLEL_LEVEL="$WOARM64_JOBS"
        export CTEST_PARALLEL_LEVEL="$WOARM64_JOBS"
    fi
    printf '%s\n' '::group::Actual makepkg build environment'
    printf 'FLAVOR=%s CARCH=%s CHOST=%s CC=%s CXX=%s STRIP=%s\n' \
        "${FLAVOR:-}" "${CARCH:-}" "${CHOST:-}" "${CC:-}" "${CXX:-}" "${STRIP:-}"
    declare -p BUILDENV
    if ! declare -p options 2>/dev/null; then
        printf 'Package does not override configured options.\n'
    fi
    if check_buildoption ccache y; then
        printf '%s\n' 'Effective ccache option: enabled'
    else
        printf '%s\n' 'Effective ccache option: disabled (package options override BUILDENV)'
    fi
    source "$WOARM64_SCRIPTS/probe-ccache.sh"
    WOARM64_PROBE_CONTEXT='makepkg buildenv hook, after compiler.sh' report_ccache_environment
    if [[ ${FLAVOR:-} == NATIVE_WITH_NATIVE ]]; then
        export WOARM64_CACHE_INPUTS_FILE="$MAKEPKG_LIBRARY/native-cache-inputs.txt"
        # prepare_buildenv does not propagate a failing hook's return status.
        CC="${CC:-gcc}" CXX="${CXX:-g++}" bash "$WOARM64_SCRIPTS/assert-native-toolchain.sh" || exit $?
        export CCACHE_COMPILERCHECK=content
        export CCACHE_NAMESPACE="${WOARM64_TOOLCHAIN_EPOCH:-installed}-$(sha256sum "$WOARM64_CACHE_INPUTS_FILE" | cut -d ' ' -f 1)"
        export CCACHE_EXTRAFILES="$WOARM64_CACHE_INPUTS_FILE"
        printf 'CCACHE_NAMESPACE=%s\n' "$CCACHE_NAMESPACE"
    fi
    printf '%s\n' '::endgroup::'
}
