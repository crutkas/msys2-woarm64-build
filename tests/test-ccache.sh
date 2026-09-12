#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$root/.github/scripts/probe-ccache.sh"
temporary=$(mktemp -d)
trap 'rm -r -- "$temporary"' EXIT

assert_probe() {
    local expected=$1 result
    result=$(probe_ccache_entry "$temporary" woarm64-control)
    if [[ "$result" != *"$expected"* ]]; then
        printf 'FAIL: expected %s, got %s\n' "$expected" "$result" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$expected"
}

assert_probe 'ABSENT'
printf '#!/bin/sh\nexit 0\n' > "$temporary/woarm64-control"
chmod +x "$temporary/woarm64-control"
assert_probe 'RESOLVABLE+RUNNABLE'
chmod -x "$temporary/woarm64-control"
if [[ ! -x "$temporary/woarm64-control" ]]; then
    assert_probe 'PRESENT-BUT-NOT-RUNNABLE (not executable)'
else
    printf 'SKIP: this filesystem does not expose non-executable script permissions\n'
fi
rm -- "$temporary/woarm64-control"
printf 'symlink target\n' > "$temporary/target"
MSYS=winsymlinks ln -s "$temporary/target" "$temporary/woarm64-control"
rm -- "$temporary/target"
assert_probe 'PRESENT-BUT-BROKEN-SYMLINK'
rm -- "$temporary/woarm64-control"
printf 'shortcut-only control\n' > "$temporary/woarm64-control.lnk"
assert_probe 'ABSENT (only .lnk present)'
rm -- "$temporary/woarm64-control.lnk"
printf '#!/bin/sh\nexit 42\n' > "$temporary/woarm64-control"
chmod +x "$temporary/woarm64-control"
assert_probe 'PRESENT-BUT-NOT-RUNNABLE (exit 42;'
