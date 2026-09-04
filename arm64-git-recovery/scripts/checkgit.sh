#!/bin/bash
cache=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/refpkgs
gitpkg=$(ls "$cache"/*git-2*.pkg.tar.zst 2>/dev/null | head -1)
echo "git pkg: $(basename "$gitpkg" 2>/dev/null || echo NONE)"
if [ -n "$gitpkg" ]; then
  echo "--- libexec/git-core exe count in reference git package ---"
  bsdtar -tf "$gitpkg" | grep -c 'clangarm64/libexec/git-core/.*\.exe$'
  echo "--- sample libexec exes ---"
  bsdtar -tf "$gitpkg" | grep 'clangarm64/libexec/git-core/.*\.exe$' | head -5
  echo "--- top-level git exe ---"
  bsdtar -tf "$gitpkg" | grep 'clangarm64/bin/git.*\.exe$' | head
fi
