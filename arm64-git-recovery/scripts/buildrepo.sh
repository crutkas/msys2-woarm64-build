#!/bin/bash
set +e
ROOT=/tmp/mingit-root
REPO=/tmp/localrepo
rm -rf "$REPO"; mkdir -p "$REPO"
# Build a sync repo from all reference pkgs + my packages
cp /mnt/c/Users/CRUTKA~1/AppData/Local/Temp/refpkgs/*.zst "$REPO"/ 2>/dev/null
cp /mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg/*.pkg.tar.zst "$REPO"/ 2>/dev/null
cd "$REPO"
repo-add "$REPO/woa.db.tar.gz" "$REPO"/*.pkg.tar.zst >/tmp/repoadd.log 2>&1
echo "repo-add exit=$? ; pkgs in repo: $(ls "$REPO"/*.pkg.tar.zst | wc -l)"

printf '[options]\nArchitecture = any\nSigLevel = Never\n\n[woa]\nServer = file://%s\n' "$REPO" > /tmp/pacman-sync.conf
# fresh root, sync db
rm -rf "$ROOT"; mkdir -p "$ROOT/var/lib/pacman"
pacman --config /tmp/pacman-sync.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Sy --noconfirm >/tmp/sync.log 2>&1
echo "pacman -Sy exit=$?"; tail -2 /tmp/sync.log
echo "packages visible in sync db: $(pacman --config /tmp/pacman-sync.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Sl woa 2>/dev/null | wc -l)"
echo "--- is git-credential-manager / busybox / git-extra / openssh / msys2-runtime in repo? ---"
for p in git-credential-manager busybox git-extra openssh msys2-runtime; do
  n=$(pacman --config /tmp/pacman-sync.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Sl woa 2>/dev/null | grep -c "$p")
  echo "  $p: $n"
done
