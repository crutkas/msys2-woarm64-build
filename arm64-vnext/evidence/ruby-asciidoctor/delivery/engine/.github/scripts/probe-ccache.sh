#!/bin/bash

# Sourceable so the same discriminator runs in makepkg and in its controls.
probe_ccache_entry() {
    local directory=$1 name=$2 status
    if [[ -L "$directory/$name" && ! -e "$directory/$name" ]]; then
        printf '%s: PRESENT-BUT-BROKEN-SYMLINK\n' "$name"
    elif [[ -x "$directory/$name" ]]; then
        if env PATH="$directory:$PATH" "$name" --version; then
            printf '%s: RESOLVABLE+RUNNABLE\n' "$name"
        else
            status=$?
            printf '%s: PRESENT-BUT-NOT-RUNNABLE (exit %s; inspect target/compiler errors above)\n' "$name" "$status"
        fi
    elif [[ -e "$directory/$name" ]]; then
        printf '%s: PRESENT-BUT-NOT-RUNNABLE (not executable)\n' "$name"
    elif [[ -e "$directory/$name.lnk" || -L "$directory/$name.lnk" ]]; then
        printf '%s: ABSENT (only .lnk present)\n' "$name"
    else
        printf '%s: ABSENT\n' "$name"
    fi
}

report_ccache_environment() {
    local directory=${1:-/usr/lib/ccache/bin} name
    printf 'Context: %s\nMSYS=%s\nMSYSTEM=%s\nPATH=%s\n' \
        "${WOARM64_PROBE_CONTEXT:-standalone forced-PATH probe, not makepkg}" \
        "${MSYS:-}" "${MSYSTEM:-}" "$PATH"
    if [[ -d "$directory" ]]; then
        ls -la "$directory"
    else
        printf 'DIRECTORY MISSING: %s\n' "$directory"
    fi
    for name in makeinfo aarch64-w64-mingw32-gcc; do
        printf '%s original PATH lookup: ' "$name"
        type -P "$name" || printf 'NOT FOUND\n'
        probe_ccache_entry "$directory" "$name"
    done
    printf '%s\n' 'A ccache compiler wrapper can fail because its real compiler is not installed yet.'
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    set -euo pipefail
    report_ccache_environment "${1:-/usr/lib/ccache/bin}"
fi
