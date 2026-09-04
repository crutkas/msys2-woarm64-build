#!/bin/bash
set +e
cache=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/refpkgs
cd /tmp
# find the busybox package name/version in the clangarm64 db
UA="Mozilla/5.0"
echo "=== querying clangarm64.db for busybox ==="
curl -sSL -A "$UA" -o /tmp/clangarm64.db "https://repo.msys2.org/mingw/clangarm64/clangarm64.db"
mkdir -p /tmp/dbx; tar -xf /tmp/clangarm64.db -C /tmp/dbx 2>/dev/null
bb=$(ls -d /tmp/dbx/mingw-w64-clang-aarch64-busybox-* 2>/dev/null | head -1)
echo "busybox db entry: $(basename "$bb" 2>/dev/null || echo NONE)"
if [ -n "$bb" ]; then
  fn=$(grep -A1 '%FILENAME%' "$bb/desc" | tail -1)
  echo "filename: $fn"
  curl -sSL -A "$UA" -o "$cache/$fn" "https://repo.msys2.org/mingw/clangarm64/$fn"
  echo "downloaded: $(ls -la "$cache/$fn" 2>&1 | awk '{print $5, $NF}')"
fi
