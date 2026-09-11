#!/usr/bin/env bash
set -euo pipefail

makeinfo=$(command -v makeinfo) || {
    echo "A genuine makeinfo from texinfo is required for cross-toolchain documentation." >&2
    exit 1
}
version=$("$makeinfo" --version)
if [[ "$version" != *"GNU texinfo"* ]]; then
    echo "Selected makeinfo is not GNU Texinfo: $makeinfo" >&2
    exit 1
fi
printf 'makeinfo=%s\n%s\n' "$makeinfo" "$version"

directory=$(mktemp -d "${TMPDIR:-/tmp}/toolchain-texinfo.XXXXXX")
trap 'rm -f -- "$directory/probe.texi" "$directory/probe.info"; rmdir -- "$directory"' EXIT
cat > "$directory/probe.texi" <<'EOF'
\input texinfo
@setfilename probe.info
@settitle Cross-toolchain Texinfo dependency
@node Top
@top Cross-toolchain Texinfo dependency
Real Info documentation generation is required.
@bye
EOF
"$makeinfo" --no-split -o "$directory/probe.info" "$directory/probe.texi"
test -s "$directory/probe.info"
grep -Fq 'File: probe.info,' "$directory/probe.info"
grep -Fq 'Real Info documentation generation is required.' "$directory/probe.info"
echo 'GNU Texinfo generated a nonempty Info document.'
