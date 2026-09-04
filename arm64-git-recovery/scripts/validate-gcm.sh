#!/bin/bash
set +e
PKG=/tmp/gcm-pkg/mingw-w64-clang-aarch64-git-credential-manager-0-STUB.1-any.pkg.tar.zst
ROOT=/tmp/gcm-validate
rm -rf "$ROOT"; mkdir -p "$ROOT/var/lib/pacman"
printf '[options]\nArchitecture = any\nSigLevel = Never\n' > /tmp/gcm-pac.conf

echo "=== repo-add accepts it? ==="
rm -rf /tmp/gcm-repo; mkdir -p /tmp/gcm-repo; cp "$PKG" /tmp/gcm-repo/
repo-add /tmp/gcm-repo/t.db.tar.gz /tmp/gcm-repo/*.zst >/tmp/gcm-ra.log 2>&1
echo "repo-add exit=$?"; grep -i "error\|adding" /tmp/gcm-ra.log | head

echo "=== pacman -U install ==="
pacman --config /tmp/gcm-pac.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -U --noconfirm "$PKG" >/tmp/gcm-u.log 2>&1
echo "pacman -U exit=$?"; tail -3 /tmp/gcm-u.log

echo "=== pacman -Ql (the make-file-list.sh:127 call) ==="
pacman --config /tmp/gcm-pac.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Ql mingw-w64-clang-aarch64-git-credential-manager 2>&1 | head

echo "=== run the stub exe to prove it is non-functional (needs wine; skip if absent) ==="
if command -v wine >/dev/null 2>&1; then
  wine "$ROOT/clangarm64/bin/git-credential-manager.exe" get 2>&1 | head -2
  echo "exit=$?"
else
  echo "(wine not present in WSL - stub behaviour verified by source; exits 1 with message)"
fi
