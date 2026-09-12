#!/bin/bash
set -euo pipefail

source `dirname ${BASH_SOURCE[0]}`/../../config.sh

if [[ $# == 0 ]]; then
    echo "CRT bootstrap headers are staged from the prepared package source during build."
    exit 0
fi

[[ $# == 4 ]] || {
    echo "usage: $0 SOURCE_ROOT TARGET_INCLUDE RECEIPT PKGBUILD" >&2
    exit 2
}

source_root=$(cd "$1" && pwd -P)
target_include=$2
receipt=$3
pkgbuild=$4
expected_repository=https://github.com/Windows-on-ARM-Experiments/mingw-woarm64.git
expected_commit=92e63a665c6f217a41401feb69b4662928d370ba
declared_commit=9d8da7d28c75dd70bcd7b6b5f9b360ebfe13194a
headers=(pthread_signal.h pthread_unistd.h pthread_time.h pthread_compat.h)
expected_hashes=(
    46915f25fb94f61ac4bdfa9b38736e6524a5b36bc42b00f7e87526fbc24287a6
    920925577b990df78791e757b557bf83c2c4f9a6b91e87b3178a97258b011da2
    08f987b1f590419dd1e9f7b55871422aacf96b476e99b0bca9fe58743a5c8657
    f49f8f267c60f7a6ec24c3ee770bdfa7efd3aee76e2f234089e9a9f75168e4db
)

# makepkg does not clone a git source straight from its URL into $srcdir. It
# maintains a local mirror beside the recipe and clones $srcdir from that, so
# the prepared tree's origin is a local path rather than the upstream URL.
# Follow that chain to the first real URL so the repository check still
# compares against upstream instead of rejecting a correctly prepared source.
resolve_upstream_origin () {
    local repo=$1 url depth=0
    url=$(git -C "$repo" remote get-url origin 2>/dev/null) || return 1
    while [[ "$url" != *://* && $depth -lt 8 ]]; do
        repo=${url#file://}
        [[ -d "$repo" ]] || break
        url=$(git -C "$repo" remote get-url origin 2>/dev/null) || return 1
        depth=$((depth + 1))
    done
    printf '%s' "${url#file://}"
}

[[ -f "$pkgbuild" && ! -L "$pkgbuild" ]] || {
    echo "The CRT PKGBUILD must be a regular file." >&2
    exit 1
}
grep -Fq "_commit='$declared_commit'" "$pkgbuild" ||
    { echo "The CRT recipe-declared source revision changed." >&2; exit 1; }
grep -Fq 'git+https://github.com/Windows-on-ARM-Experiments/mingw-woarm64.git#branch=woarm64' "$pkgbuild" ||
    { echo "The CRT recipe source repository changed." >&2; exit 1; }

actual_commit=$(git -C "$source_root" rev-parse HEAD)
[[ "$actual_commit" == "$expected_commit" ]] ||
    { echo "The prepared CRT source revision changed: $actual_commit" >&2; exit 1; }
origin=$(resolve_upstream_origin "$source_root") ||
    { echo "Could not resolve the prepared CRT source origin." >&2; exit 1; }
origin=${origin%.git}
[[ "$origin" == "${expected_repository%.git}" ]] ||
    { echo "The prepared CRT source repository changed: $origin" >&2; exit 1; }

source_include=$source_root/mingw-w64-libraries/winpthreads/include
[[ -d "$target_include" && ! -L "$target_include" ]] ||
    { echo "The target include root must already be a regular directory." >&2; exit 1; }
[[ ! -e "$receipt" && ! -L "$receipt" ]] ||
    { echo "Refusing to replace an existing bootstrap-header receipt." >&2; exit 1; }
for index in "${!headers[@]}"; do
    header=${headers[$index]}
    source_header=$source_include/$header
    [[ -f "$source_header" && ! -L "$source_header" ]] ||
        { echo "Missing regular source header: $source_header" >&2; exit 1; }
    actual_hash=$(sha256sum "$source_header" | cut -d' ' -f1)
    [[ "$actual_hash" == "${expected_hashes[$index]}" ]] ||
        { echo "Source header changed: $header $actual_hash" >&2; exit 1; }
    [[ ! -e "$target_include/$header" && ! -L "$target_include/$header" ]] ||
        { echo "Refusing to overwrite target-owned header: $header" >&2; exit 1; }
done

for index in "${!headers[@]}"; do
    header=${headers[$index]}
    install -m 0644 "$source_include/$header" "$target_include/$header"
    [[ $(sha256sum "$target_include/$header" | cut -d' ' -f1) == "${expected_hashes[$index]}" ]] ||
        { echo "Staged header changed: $header" >&2; exit 1; }
done

mkdir -p "$(dirname "$receipt")"
cat >"$receipt.tmp" <<EOF
{
  "schema": 1,
  "status": "mingwarm64-crt-bootstrap-headers-staged",
  "sourceRepository": "$expected_repository",
  "sourceCommit": "$actual_commit",
  "recipeDeclaredCommit": "$declared_commit",
  "pkgbuildSha256": "$(sha256sum "$pkgbuild" | cut -d' ' -f1)",
  "targetInclude": "$target_include",
  "headers": {
    "pthread_signal.h": "${expected_hashes[0]}",
    "pthread_unistd.h": "${expected_hashes[1]}",
    "pthread_time.h": "${expected_hashes[2]}",
    "pthread_compat.h": "${expected_hashes[3]}"
  }
}
EOF
mv "$receipt.tmp" "$receipt"
cat "$receipt"
