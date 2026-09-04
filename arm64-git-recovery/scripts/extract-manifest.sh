#!/bin/bash
cd /tmp
unzip -l mingit-bb-arm64.zip | awk 'NR>3 {print $4}' | grep -v '^$' | grep -v '^----' | grep -v 'files$' > /tmp/upstream-mingit-manifest.txt
echo "lines: $(wc -l < /tmp/upstream-mingit-manifest.txt)"
echo "=== libexec/git-core exe count ==="
grep -c 'libexec/git-core/.*\.exe$' /tmp/upstream-mingit-manifest.txt
echo "=== DLLs in clangarm64/bin ==="
grep 'clangarm64/bin/.*\.dll$' /tmp/upstream-mingit-manifest.txt | sed 's#.*/##' | sort
cp /tmp/upstream-mingit-manifest.txt /mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg/upstream-mingit-manifest.txt
