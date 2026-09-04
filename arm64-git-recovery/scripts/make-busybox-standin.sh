#!/bin/bash
set +e
cd /tmp
# Re-download upstream MinGit if the zip is gone (tmp wiped between sessions)
if [ ! -f /tmp/mingit-bb-arm64.zip ]; then
  curl -sSL -o /tmp/mingit-bb-arm64.zip "https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/MinGit-2.55.0.5-busybox-arm64.zip"
fi
echo "zip size: $(stat -c %s /tmp/mingit-bb-arm64.zip)"
rm -rf /tmp/bbx; mkdir -p /tmp/bbx
unzip -o -q /tmp/mingit-bb-arm64.zip clangarm64/bin/busybox.exe clangarm64/bin/ash.exe -d /tmp/bbx
ls -la /tmp/bbx/clangarm64/bin/
# verify ARM64
python3 - <<'PY'
import struct
for f in ["/tmp/bbx/clangarm64/bin/busybox.exe","/tmp/bbx/clangarm64/bin/ash.exe"]:
    b=open(f,"rb").read(); pe=struct.unpack_from("<i",b,0x3c)[0]
    print(f.split("/")[-1], "PE machine 0x%04X"%struct.unpack_from("<H",b,pe+4)[0])
PY

# Build a stand-in busybox package from upstream's binaries (KNOWN-GOOD stand-in, labelled)
MK=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
ROOT=/tmp/bb-pkg/clangarm64
rm -rf /tmp/bb-pkg; mkdir -p "$ROOT/bin"
cp /tmp/bbx/clangarm64/bin/busybox.exe "$ROOT/bin/"
cp /tmp/bbx/clangarm64/bin/ash.exe "$ROOT/bin/"
cat > /tmp/bb-spec.json <<EOF
{
  "pkgname": "mingw-w64-clang-aarch64-busybox",
  "pkgbase": "mingw-w64-clang-aarch64-busybox",
  "pkgver": "1.37.0.upstreamstandin-1",
  "pkgdesc": "PIPELINE-TEST STAND-IN: upstream busybox.exe extracted from MinGit-busybox-arm64.zip. NOT our build. For pipeline A/B only.",
  "url": "https://github.com/git-for-windows/git",
  "license": "GPL",
  "depends": [],
  "provides": ["mingw-w64-clang-aarch64-busybox"],
  "payload_root": "$ROOT",
  "out": "/tmp/bb-pkg/mingw-w64-clang-aarch64-busybox-1.37.0.upstreamstandin-1-any.pkg"
}
EOF
python3 "$MK/mkpkg.py" /tmp/bb-spec.json
zstd -q -f /tmp/bb-pkg/*.pkg.tar -o /tmp/bb-pkg/mingw-w64-clang-aarch64-busybox-1.37.0.upstreamstandin-1-any.pkg.tar.zst
ls -la /tmp/bb-pkg/*.zst
