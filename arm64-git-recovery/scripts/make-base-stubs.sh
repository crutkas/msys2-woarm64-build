#!/bin/bash
set -e
MK=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
OUT=/tmp/basestubs
rm -rf "$OUT"; mkdir -p "$OUT"

# Minimal empty stub package for a base/virtual dependency so pactree/pacman resolve.
# These are NOT our deliverables — they stand in for msys base packages absent from our clangarm64 snapshot.
mkstub () {
  local name="$1" ver="$2"
  local root=/tmp/basestubs/$name/payload/clangarm64/share/pipeline-stubs
  rm -rf /tmp/basestubs/$name; mkdir -p "$root"
  echo "empty pipeline stub for $name (not a deliverable)" > "$root/$name.stub"
  local payload=/tmp/basestubs/$name/payload/clangarm64
  cat > /tmp/basestubs/$name-spec.json <<EOF
{
  "pkgname": "$name",
  "pkgbase": "$name",
  "pkgver": "$ver-1",
  "pkgdesc": "PIPELINE-TEST STUB for $name (empty; stands in for a base/msys dep absent from the clangarm64 snapshot). Not a deliverable.",
  "url": "https://example.invalid",
  "license": "none",
  "depends": [],
  "provides": ["$name"],
  "payload_root": "$payload",
  "out": "/tmp/basestubs/$name-$ver-1-any.pkg"
}
EOF
  python3 "$MK/mkpkg.py" /tmp/basestubs/$name-spec.json >/dev/null
  zstd -q -f "/tmp/basestubs/$name-$ver-1-any.pkg.tar" -o "/tmp/basestubs/$name-$ver-1-any.pkg.tar.zst"
}

# clangarm64 virtual runtime + editor
mkstub mingw-w64-clang-aarch64-cc-libs 1.0
mkstub nano 8.0
# msys base packages hardcoded in the `packages` list (line 205-206) and pulled by pactree
mkstub msys2-runtime 3.5.0
mkstub openssh 9.8
mkstub filesystem 2024
mkstub rebase 4.5
mkstub mingw-w64-clang-aarch64-git-extra 1.0
mkstub mingw-w64-clang-aarch64-cc-libs-fallback 1.0
echo "=== base stubs ==="
ls /tmp/basestubs/*.zst | sed 's#.*/##'
