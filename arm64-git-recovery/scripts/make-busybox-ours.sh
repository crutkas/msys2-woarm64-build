#!/bin/bash
set +e
# ALL-OURS busybox package: built from 1e7a7fd3's handover busybox.exe
# (our WoA GCC 15.0.1, aarch64-w64-mingw32, busybox-w32 d8d8bb397 unmodified).
# ash.exe is a byte-copy of busybox.exe (argv[0] applet dispatch), same as upstream.
MK=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
SRC=/mnt/c/Users/crutkasLocal/.copilot/session-state/1e7a7fd3-02e7-432a-a09c-5502ed8992a6/files/handover/busybox.exe
EXPECT=67665b44db934b574c95a600955482d35f1bb421a9498998df3e5baa96313aa8

echo "=== verify source busybox before packaging (hash + PE machine) ==="
GOT=$(sha256sum "$SRC" | cut -d' ' -f1)
echo "  sha256: $GOT"
[ "$GOT" = "$EXPECT" ] || { echo "  FATAL: busybox hash mismatch (expected $EXPECT)"; exit 3; }
python3 "$MK/pe-machine.py" "$SRC" | grep -q "0xAA64" || { echo "  FATAL: busybox not 0xAA64"; exit 4; }
echo "  PIN-OK: busybox 67665b44, 0xAA64"

ROOT=/tmp/bb-pkg/clangarm64
rm -rf /tmp/bb-pkg; mkdir -p "$ROOT/bin"
cp "$SRC" "$ROOT/bin/busybox.exe"
cp "$SRC" "$ROOT/bin/ash.exe"        # argv[0] applet dispatch -> ash
echo "  staged busybox.exe + ash.exe (identical bytes)"

cat > /tmp/bb-spec.json <<EOF
{
  "pkgname": "mingw-w64-clang-aarch64-busybox",
  "pkgbase": "mingw-w64-clang-aarch64-busybox",
  "pkgver": "1.37.0-1",
  "pkgdesc": "BusyBox for Windows (ARM64), built with our Windows-on-Arm GCC toolchain from busybox-w32 d8d8bb397 (unmodified). 179 applets; UCRT-only, runtime-free.",
  "url": "https://github.com/git-for-windows/busybox-w32",
  "license": "GPL",
  "depends": [],
  "provides": ["mingw-w64-clang-aarch64-busybox"],
  "payload_root": "$ROOT",
  "out": "/tmp/bb-pkg/mingw-w64-clang-aarch64-busybox-1.37.0-1-any.pkg"
}
EOF
python3 "$MK/mkpkg.py" /tmp/bb-spec.json
zstd -q -f /tmp/bb-pkg/*.pkg.tar -o /tmp/bb-pkg/mingw-w64-clang-aarch64-busybox-1.37.0-1-any.pkg.tar.zst
ls -la /tmp/bb-pkg/*.zst
