#!/bin/bash
set -e
PKG="$1"
ROOT=/tmp/pacroot
rm -rf "$ROOT"
mkdir -p "$ROOT/var/lib/pacman" "$ROOT/var/cache/pacman/pkg"
cat > /tmp/pacman.conf <<EOF
[options]
Architecture = any
SigLevel = Never
EOF
echo '=== pacman -U (install into isolated root) ==='
pacman --config /tmp/pacman.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -U "$PKG" --noconfirm 2>&1 | tail -8
echo '=== pacman -Q (installed?) ==='
pacman --config /tmp/pacman.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Q 2>&1
echo '=== pacman -Ql mingw-w64-clang-aarch64-brotli (make-file-list.sh call) ==='
pacman --config /tmp/pacman.conf --root "$ROOT" --dbpath "$ROOT/var/lib/pacman" -Ql mingw-w64-clang-aarch64-brotli 2>&1 | head -25
echo '=== pactree -u ==='
if which pactree >/dev/null 2>&1; then
  pactree --config /tmp/pacman.conf --dbpath "$ROOT/var/lib/pacman" -u mingw-w64-clang-aarch64-brotli 2>&1 | head
else
  echo "pactree NOT installed (part of pacman-contrib)"
fi
