#!/bin/bash
set +e
printf '[options]\nArchitecture = any\nSigLevel = Never\n' > /tmp/leaf-pac.conf
rm -rf /tmp/leaf-repo; mkdir -p /tmp/leaf-repo; cp /tmp/leaves/*.pkg.tar.zst /tmp/leaf-repo/
echo "=== repo-add ==="
repo-add /tmp/leaf-repo/leaf.db.tar.gz /tmp/leaf-repo/*.zst >/tmp/leaf-ra.log 2>&1
echo "repo-add exit=$?"; grep -ci "adding package" /tmp/leaf-ra.log

for name in c-ares libtasn1 libffi wineditline; do
  pkg=$(ls /tmp/leaves/mingw-w64-clang-aarch64-$name-*.pkg.tar.zst)
  ROOT=/tmp/leaf-val-$name; rm -rf "$ROOT"; mkdir -p "$ROOT/var/lib/pacman"
  pacman --config /tmp/leaf-pac.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -U --noconfirm "$pkg" >/tmp/leaf-u-$name.log 2>&1
  ue=$?
  ql=$(pacman --config /tmp/leaf-pac.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Ql mingw-w64-clang-aarch64-$name 2>/dev/null | wc -l)
  echo "$name: pacman -U exit=$ue ; pacman -Ql lines=$ql"
done
