#!/bin/bash
set -euo pipefail

scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -n ${WOARM64_CACHE_INPUTS_FILE:-} ]]; then
    : > "$WOARM64_CACHE_INPUTS_FILE"
fi
printf '%s\n' 'Checking compiler executables, not claiming the MSYS shell/ccache/gh/jq are native.'

# Resolve real tools, not the ccache masquerade entry at the front of PATH.
IFS=: read -r -a directories <<< "$PATH"
tool_path=
for directory in "${directories[@]}"; do
    [[ "$directory" == /usr/lib/ccache/bin ]] && continue
    tool_path+="${tool_path:+:}$directory"
done

assert_tool() {
    local tool=$1 resolved
    if ! resolved=$(PATH="$tool_path" type -P "$tool"); then
        printf 'Required compiler tool not found: %s\n' "$tool" >&2
        return 1
    fi
    [[ -f "$resolved.exe" ]] && resolved+=.exe
    resolved=$(readlink -f -- "$resolved")
    powershell.exe -NoProfile -NonInteractive -File \
        "$(cygpath -w "$scripts/assert-arm64-pe.ps1")" -Path "$(cygpath -w "$resolved")"
    if [[ -n ${WOARM64_CACHE_INPUTS_FILE:-} ]]; then
        sha256sum "$resolved" >> "$WOARM64_CACHE_INPUTS_FILE"
    fi
}

for role in CC CXX; do
    if [[ $role == CC ]]; then
        compiler=${CC:-gcc}
        programs=(cc1 as ld)
    else
        compiler=${CXX:-g++}
        programs=(cc1plus)
    fi
    assert_tool "$compiler"
    target=$(PATH="$tool_path" "$compiler" -dumpmachine)
    if [[ "$target" != aarch64-w64-mingw32 ]]; then
        printf 'Expected aarch64-w64-mingw32 target, got %s from %s\n' "$target" "$compiler" >&2
        exit 1
    fi
    PATH="$tool_path" "$compiler" --version
    for program in "${programs[@]}"; do
        assert_tool "$(PATH="$tool_path" "$compiler" "-print-prog-name=$program")"
    done
done

if [[ -n ${WOARM64_CACHE_INPUTS_FILE:-} ]]; then
    for library in libgcc.a crt2.o libstdc++.a libmingw32.a libmingwex.a libwinpthread.a; do
        path=$(PATH="$tool_path" "${CC:-gcc}" "-print-file-name=$library")
        path=$(cygpath -u "$path")
        if [[ ! -f $path || $path == "$library" ]]; then
            printf 'Native compiler link input not found: %s\n' "$library" >&2
            exit 1
        fi
        sha256sum "$path" >> "$WOARM64_CACHE_INPUTS_FILE"
    done
fi
