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

    echo "::group::Verify native ARM64 tool closure"
        verify_native_tool_closure
    echo "::endgroup::"

    ensure_native_compiler_launchers
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
            with_short_native_recipe_root makepkg-mingw $ARGUMENTS
        else
            makepkg-mingw $ARGUMENTS
        fi
    else
        makepkg $ARGUMENTS
    fi
echo "::endgroup::"

# The alias drive letter is whichever candidate happened to be free, so any path
# recorded under it is both dangling and irreproducible across runs.
if [[ -n "$WOARM64_LAST_RECIPE_ALIAS_LETTER" ]]; then
    echo "::group::Scan staged output for native recipe alias residue"
        assert_no_native_recipe_alias_residue "$WOARM64_LAST_RECIPE_ALIAS_LETTER" "$PWD/pkg"
    echo "::endgroup::"
fi

if command -v ccache &> /dev/null; then
    echo "::group::Ccache statistics after build"
        ccache -svv || true
    echo "::endgroup::"
fi
