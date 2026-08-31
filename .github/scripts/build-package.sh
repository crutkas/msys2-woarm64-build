#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/../../config.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/stage0-git.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/native-tooling.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/native-recipe-root.sh"

PACKAGE_REPOSITORY=$1

configure_stage0_git
if [[ "$FLAVOR" == "NATIVE_WITH_NATIVE" ]]; then
    # The MSYS2 runtime rewrites POSIX-looking arguments on the way into a
    # native PE. Exclude exactly the forms native-compiler.sh converts itself,
    # so the payload dialects have one explicit, testable owner instead of an
    # unauditable heuristic.
    export MSYS2_ARG_CONV_EXCL="$WOARM64_MSYS2_ARG_CONV_EXCL"

    # Package builds use the installed native closure only. Test fixtures may
    # exercise library helpers with isolated paths, but this production driver
    # must not accept an environment-provided toolchain or launcher location.
    for protected_setting in WOARM64_NATIVE_BIN WOARM64_NATIVE_LAUNCHER_COMPILER \
        WOARM64_NATIVE_CXX WOARM64_LAUNCHER_INSTALL_DIR; do
        if [[ -n "${!protected_setting:-}" ]]; then
            echo "Refusing $protected_setting override during a native package build" >&2
            exit 2
        fi
    done
    unset WOARM64_TOOL_VERSION_PROBE

    echo "::group::Verify native ARM64 tool closure"
        if ! verify_native_tool_closure; then
            exit 1
        fi
    echo "::endgroup::"

    if ! ensure_native_compiler_launchers; then
        exit 1
    fi
fi

ARGUMENTS="--syncdeps \
    --rmdeps \
    --noconfirm \
    --noprogressbar \
    --nocheck \
    --skippgpcheck \
    --force \
    $([ "$NO_EXTRACT" = 1 ] && echo "--noextract" || echo "") \
    $([ "$CLEAN_BUILD" = 1 ] && echo "--cleanbuild" || echo "") \
    $([ "$INSTALL_PACKAGE" = 1 ] && echo "--install" || echo "")"

if command -v ccache &> /dev/null; then
    echo "::group::Ccache statistics before build"
        ccache -svv  || true
    echo "::endgroup::"
fi

echo "::group::Build package"
makepkg_status=0
    if [[ "$PACKAGE_REPOSITORY" == *MINGW* ]]; then
        USE_SHORT_NATIVE_RECIPE_ROOT=0
        if [[ "$FLAVOR" == "NATIVE_WITH_NATIVE" ]]; then
            if native_recipe_root_needs_alias; then
                USE_SHORT_NATIVE_RECIPE_ROOT=1
            else
                ALIAS_STATUS=$?
                if [[ $ALIAS_STATUS -ne 1 ]]; then
                    exit "$ALIAS_STATUS"
                fi
            fi
        fi

        if [[ $USE_SHORT_NATIVE_RECIPE_ROOT -eq 1 ]]; then
            with_short_native_recipe_root makepkg-mingw $ARGUMENTS || makepkg_status=$?
        else
            makepkg-mingw $ARGUMENTS || makepkg_status=$?
        fi
    else
        makepkg $ARGUMENTS || makepkg_status=$?
    fi
echo "::endgroup::"

# The alias drive letter is whichever candidate happened to be free, so scan
# the complete recipe root: build trees, staged payloads, metadata and produced
# archives all count as ship or support surfaces. Scan even after makepkg fails
# so a partial output cannot hide a residue incident.
residue_status=0
if [[ -n "$WOARM64_LAST_RECIPE_ALIAS_LETTER" ]]; then
    echo "::group::Scan staged output for native recipe alias residue"
        assert_no_native_recipe_alias_residue "$WOARM64_LAST_RECIPE_ALIAS_LETTER" "$PWD" ||
            residue_status=$?
    echo "::endgroup::"
fi

if command -v ccache &> /dev/null; then
    echo "::group::Ccache statistics after build"
        ccache -svv || true
    echo "::endgroup::"
fi

if [[ $makepkg_status -ne 0 ]]; then
    exit "$makepkg_status"
fi
if [[ $residue_status -ne 0 ]]; then
    exit "$residue_status"
fi
