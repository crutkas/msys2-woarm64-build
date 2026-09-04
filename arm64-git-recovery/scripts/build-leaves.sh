#!/bin/bash
set -e
SC=/mnt/c/Users/CRUTKA~1/.copilot/session-state/ea1641ea-57c0-492d-ab94-fcfddedf1091/files/staged-closure
MK=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
OUT=/tmp/leaves
rm -rf "$OUT"; mkdir -p "$OUT"

# helper: build one package. args: name ver desc "depends" srcdir
mkleaf () {
  local name="$1" ver="$2" desc="$3" deps="$4" src="$5"; shift 5
  local pkgroot=/tmp/leaves/$name/clangarm64
  rm -rf /tmp/leaves/$name; mkdir -p "$pkgroot/bin" "$pkgroot/lib" "$pkgroot/include/$name" "$pkgroot/share/licenses/$name"
  # copy DLLs -> bin, .a/.dll.a -> lib, headers -> include/<name>
  for f in "$src"/*.dll;    do [ -e "$f" ] && cp "$f" "$pkgroot/bin/"; done
  for f in "$src"/*.a;      do [ -e "$f" ] && cp "$f" "$pkgroot/lib/"; done
  for f in "$src"/*.h;      do [ -e "$f" ] && cp "$f" "$pkgroot/include/$name/"; done
  echo "Placeholder license for $name (see upstream); staged toolchain-proof build." > "$pkgroot/share/licenses/$name/LICENSE"
  # remove empty dirs
  rmdir "$pkgroot/include/$name" 2>/dev/null || true
  local depjson=""
  if [ -n "$deps" ]; then depjson=$(printf '"%s",' $deps | sed 's/,$//'); fi
  cat > /tmp/leaves/$name-spec.json <<EOF
{
  "pkgname": "mingw-w64-clang-aarch64-$name",
  "pkgbase": "mingw-w64-clang-aarch64-$name",
  "pkgver": "$ver-1",
  "pkgdesc": "$desc (WoA GCC native ARM64 build; full-git bonus, not required for minimal HTTPS MinGit)",
  "url": "https://github.com/crutkas/msys2-woarm64-build",
  "license": "custom",
  "depends": [$depjson],
  "provides": ["mingw-w64-clang-aarch64-$name"],
  "payload_root": "$pkgroot",
  "out": "/tmp/leaves/mingw-w64-clang-aarch64-$name-$ver-1-any.pkg"
}
EOF
  python3 "$MK/mkpkg.py" /tmp/leaves/$name-spec.json
  zstd -q -f "/tmp/leaves/mingw-w64-clang-aarch64-$name-$ver-1-any.pkg.tar" \
      -o "/tmp/leaves/mingw-w64-clang-aarch64-$name-$ver-1-any.pkg.tar.zst"
}

mkleaf c-ares     1.34.5  "c-ares async DNS resolver"        ""  "$SC/c-ares"
mkleaf libtasn1   4.21.0  "libtasn1 ASN.1/DER library"       ""  "$SC/libtasn1"
mkleaf libffi     3.4.6   "libffi foreign function interface" "" "$SC/libffi"
mkleaf wineditline 2.208  "wineditline BSD editline for Windows" "" "$SC/wineditline"

echo "=== built leaf packages ==="
ls -la /tmp/leaves/*.zst
