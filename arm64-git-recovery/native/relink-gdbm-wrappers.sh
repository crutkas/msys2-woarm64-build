#!/usr/bin/env bash
set -euo pipefail
root=$(/usr/bin/cygpath.exe -u "$1")
mode=${2:-one}
export PATH="$root/host-target-runtime/usr/bin:$root/bootstrap/usr/bin:$root/compiler/bin"
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export LC_ALL=C MAKEFLAGS=-j1 MFLAGS=-j1
export CONFIG_SHELL="$root/bootstrap/usr/bin/bash.exe"
export MAKE="$root/bootstrap/usr/bin/make.exe"
export MSYS2_ARG_CONV_EXCL='-D;../'
if [[ "$mode" == one ]]; then
    cd "$root/build/tests"
    "$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" -W gtver.o gtver.exe V=1
elif [[ "$mode" == all ]]; then
    plan=$(/usr/bin/cygpath.exe -u "$3")
    if [[ $(<"$plan/compat-relink") == yes ]]; then
        cd "$root/build/compat"
        objects=( *.lo )
        [[ -f "${objects[0]}" ]] || { echo "Missing native compatibility objects" >&2; exit 1; }
        "$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" -W "${objects[0]}" libgdbm_compat.la
    fi
    for directory in tools tests; do
        cd "$root/build/$directory"
        changed=()
        while IFS= read -r target; do
            [[ -f "$target.o" ]] || { echo "Missing native object for $target" >&2; exit 1; }
            changed+=(-W "$target.o")
        done < "$plan/$directory.targets"
        if [[ "$directory" == tests ]]; then
            "$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" "${changed[@]}" \
                --eval='.SECONDEXPANSION:' \
                --eval='woarm64-check-programs: $$(check_PROGRAMS)' woarm64-check-programs
        else
            "$MAKE" -j1 MAKE="$MAKE" SHELL="$CONFIG_SHELL" "${changed[@]}" all-am
        fi
    done
else
    echo "Unsupported wrapper regeneration scope: $mode" >&2
    exit 2
fi
