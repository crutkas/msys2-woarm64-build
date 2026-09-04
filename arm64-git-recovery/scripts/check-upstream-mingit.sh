#!/bin/bash
# Download upstream busybox-arm64 MinGit and list its contents to settle the GCM question empirically.
set -e
cd /tmp
URL="https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/MinGit-2.55.0.5-busybox-arm64.zip"
echo "downloading $URL"
curl -sSL -o mingit-bb-arm64.zip "$URL"
echo "size: $(stat -c %s mingit-bb-arm64.zip) bytes"
echo "=== does it contain git-credential-manager? ==="
unzip -l mingit-bb-arm64.zip | grep -i "credential" || echo "NO credential-manager files"
echo "=== does it contain any credential helper at all? ==="
unzip -l mingit-bb-arm64.zip | grep -i "git-credential" || echo "NO git-credential* files"
echo "=== busybox / ash present? ==="
unzip -l mingit-bb-arm64.zip | grep -iE "busybox|ash\.exe" || echo "no busybox"
echo "=== top-level structure ==="
unzip -l mingit-bb-arm64.zip | awk '{print $4}' | grep -oE "^[^/]+/[^/]+/" | sort -u | head -30
echo "=== total entries ==="
unzip -l mingit-bb-arm64.zip | tail -1
