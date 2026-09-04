#!/bin/bash
set -e
B=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
PAY=/tmp/gcm-pkg/pkgroot          # mkpkg walks payload_root's children; children must be clangarm64/...
ROOT=/tmp/gcm-pkg/pkgroot/clangarm64
rm -rf /tmp/gcm-pkg; mkdir -p "$ROOT/bin" "$ROOT/doc/git-credential-manager"
cp "$B/gcm-stub.exe" "$ROOT/bin/git-credential-manager.exe"
cp "$B/gcm-stub.exe" "$ROOT/bin/git-credential-helper-selector.exe"

cat > "$ROOT/bin/git-credential-manager.exe.config" <<'EOF'
<!-- NON-FUNCTIONAL STUB config placeholder for git-credential-manager. -->
<configuration/>
EOF

cat > "$ROOT/doc/git-credential-manager/STUB-PLACEHOLDER.txt" <<'EOF'
git-credential-manager in THIS package is a NON-FUNCTIONAL STUB.

It exists ONLY so the Git-for-Windows MinGit packaging tooling has a valid ARM64 PE
to place in the git-credential-manager slot for a TOOLCHAIN-PROOF minimal artefact.

It manages NO credentials. Running it prints a message and exits non-zero.

The real Git Credential Manager is a .NET/Avalonia application whose ARM64 build is
out of scope for this toolchain demonstration (it drags ~45 managed assemblies plus
MSAL, SkiaSharp and Avalonia UI). Do not ship this stub as if it were functional
credential storage. Replace it with the real GCM for any production distribution.
EOF

cp "$ROOT/doc/git-credential-manager/STUB-PLACEHOLDER.txt" "$ROOT/doc/git-credential-manager/NOTICE"
echo "Placeholder - see STUB-PLACEHOLDER.txt" > "$ROOT/doc/git-credential-manager/README.md"

cat > /tmp/gcm-pkg/spec.json <<EOF
{
  "pkgname": "mingw-w64-clang-aarch64-git-credential-manager",
  "pkgbase": "mingw-w64-clang-aarch64-git-credential-manager",
  "pkgver": "0-STUB.1",
  "pkgdesc": "NON-FUNCTIONAL PLACEHOLDER (toolchain-proof); manages no credentials. Stub for MinGit-arm64 packaging slot only.",
  "url": "https://github.com/git-ecosystem/git-credential-manager",
  "license": "custom:STUB",
  "depends": [],
  "provides": ["mingw-w64-clang-aarch64-git-credential-manager"],
  "payload_root": "$ROOT",
  "out": "/tmp/gcm-pkg/mingw-w64-clang-aarch64-git-credential-manager-0-STUB.1-any.pkg"
}
EOF

echo "=== payload tree ==="
find "$ROOT" -type f | sed "s#$ROOT/##"
echo "=== verify stub exe is 0xAA64 ==="
python3 - <<'PY'
b=open("/tmp/gcm-pkg/pkgroot/clangarm64/bin/git-credential-manager.exe","rb").read()
import struct
pe=struct.unpack_from("<i",b,0x3c)[0]
print("PE machine 0x%04X"%struct.unpack_from("<H",b,pe+4)[0])
PY

echo "=== assemble ==="
python3 "$B/mkpkg.py" /tmp/gcm-pkg/spec.json
zstd -q -f /tmp/gcm-pkg/*.pkg.tar -o /tmp/gcm-pkg/mingw-w64-clang-aarch64-git-credential-manager-0-STUB.1-any.pkg.tar.zst
ls -la /tmp/gcm-pkg/*.zst
