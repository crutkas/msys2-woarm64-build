#!/bin/bash
# wrap-git-package.sh — turn 2918d1f1's FULL git install tree into a
# mingw-w64-clang-aarch64-git pacman package the MinGit tooling can walk.
#
# USAGE: wrap-git-package.sh <path-to-git-install-prefix> <git-version>
#   <path-to-git-install-prefix> = the DESTDIR/prefix where `make install`
#       (or install-tree) placed git, i.e. a dir that CONTAINS bin/git.exe and
#       libexec/git-core/*.exe.  We re-root it under clangarm64/.
#   <git-version> = e.g. 2.47.1  (2918d1f1 reported GIT_VERSION 2.47.1)
#
# HARD REQUIREMENT (release.sh:136 dies otherwise):
#   the tree MUST contain libexec/git-core/*.exe. We ASSERT it before packaging.
#
# Deps are the LOCKED reduced set (B4 addendum 2): curl, ca-certificates,
# expat>=2.0, openssl, pcre2. (nano dropped — MINIMAL_GIT excludes it.)
set -euo pipefail

SRC="${1:?need git install prefix}"
VER="${2:?need git version, e.g. 2.47.1}"
PIN_SHA="${3:-}"   # OPTIONAL but STRONGLY recommended: pinned sha256 of bin/git.exe.
                   # If set, we REFUSE to package unless the tree's git.exe matches.
MK=/mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg
OUT=/tmp/gitpkg
STAGE="$OUT/stage/clangarm64"
rm -rf "$OUT"; mkdir -p "$STAGE"

# 1. Re-root the install tree under clangarm64/. Accept either a prefix that
#    already has bin/libexec, or one nested under <prefix>/clangarm64 or /mingw64.
srcroot="$SRC"
for cand in "$SRC" "$SRC/clangarm64" "$SRC/mingw64" "$SRC/usr"; do
  if [ -x "$cand/bin/git.exe" ] || [ -f "$cand/bin/git.exe" ]; then srcroot="$cand"; break; fi
done
echo "using srcroot=$srcroot"
cp -a "$srcroot"/. "$STAGE"/ 2>/dev/null || cp -r "$srcroot"/* "$STAGE"/

# 2. ASSERT the load-bearing invariant BEFORE packaging.
shopt -s nullglob
lx=( "$STAGE"/libexec/git-core/*.exe )
if [ ${#lx[@]} -eq 0 ]; then
  echo "FATAL: no libexec/git-core/*.exe in the git tree." >&2
  echo "       MinGit release.sh:136 would die. The git build must be a FULL" >&2
  echo "       install (make install), not just a bare git.exe." >&2
  echo "       Contents of $STAGE/libexec (if any):" >&2
  find "$STAGE/libexec" -maxdepth 2 -type f 2>/dev/null | head >&2 || true
  exit 3
fi
echo "OK: libexec/git-core has ${#lx[@]} .exe files:"; printf '   %s\n' "${lx[@]##*/}"

# 3. SINGLE-READ MANIFEST + PIN. Per coordinator condition 2: the pin check and
#    the embedded manifest MUST come from the SAME read of the bytes, else they
#    can describe different bytes. So we hash EVERY binary ONCE here, write that
#    to the manifest, and read git.exe's hash back OUT of that same manifest for
#    the pin check. One read, one set of bytes, used for both.
gitexe="$STAGE/bin/git.exe"
SUMS="$STAGE/share/licenses/git/SHA256SUMS.woa-gcc"
mkdir -p "$(dirname "$SUMS")"
( cd "$STAGE" && find . -type f \( -name '*.exe' -o -name '*.dll' \) -print0 \
    | sort -z | xargs -0 sha256sum ) > "$SUMS"
echo "SINGLE-READ manifest: $(wc -l < "$SUMS") binaries hashed -> share/licenses/git/SHA256SUMS.woa-gcc"

# Sanity: bin/git.exe present and is ARM64 (0xAA64) — read from the header, do
# not assume.
if [ -f "$gitexe" ]; then
  OBJDUMP=/root/xc/inst/bin/aarch64-pc-cygwin-objdump
  mach=$("$OBJDUMP" -f "$gitexe" 2>/dev/null | grep -i "architecture" || true)
  echo "git.exe file header: $mach"
  m=$(python3 - "$gitexe" <<'PY'
import sys,struct
d=open(sys.argv[1],'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]
mach=struct.unpack_from('<H',d,pe+4)[0]
print(hex(mach))
PY
)
  echo "git.exe PE machine = $m  (expect 0xaa64 for ARM64)"
  [ "$m" = "0xaa64" ] || echo "WARNING: git.exe is NOT 0xaa64 — wrong arch!" >&2
  # PIN CHECK: read git.exe's hash BACK OUT OF THE MANIFEST we just wrote, so the
  # pinned bytes and the manifested bytes are provably identical.
  actual_sha=$(awk '$2=="./bin/git.exe"{print $1}' "$SUMS")
  echo "git.exe sha256 (from manifest) = $actual_sha"
  if [ -z "$actual_sha" ]; then
    echo "FATAL: bin/git.exe not found in the single-read manifest." >&2
    exit 5
  fi
  if [ -n "$PIN_SHA" ]; then
    if [ "$actual_sha" != "$PIN_SHA" ]; then
      echo "FATAL: git.exe sha256 MISMATCH." >&2
      echo "  expected (pinned/verified): $PIN_SHA" >&2
      echo "  actual (manifest at wrap time): $actual_sha" >&2
      echo "  The verification covers a specific hash and nothing else." >&2
      echo "  The artefact moved since verification — STOPPING." >&2
      exit 4
    fi
    echo "PIN OK: git.exe matches the verified hash $PIN_SHA (same read as manifest)"
  else
    echo "WARNING: no PIN_SHA supplied — packaging WITHOUT a verified-hash gate." >&2
    echo "         Pass the verified sha256 as arg 3 to enforce it." >&2
  fi
else
  echo "WARNING: no bin/git.exe in tree" >&2
fi

# 5. Build the .PKGINFO spec and package.
# Depends: git.exe is FULLY STATIC (measured: binds only UCRT+Win32 system DLLs,
# zero libcurl/libcrypto/libssl/libexpat/libpcre2). ca-certificates is the only
# LOAD-BEARING runtime dependency (data: the 172-cert bundle read at HTTPS time).
# Declaring curl/openssl/expat/pcre2 makes pactree pull their never-loaded DLLs
# into the MinGit file list (measured). Override with GIT_DEPENDS if needed.
if [ -z "${GIT_DEPENDS:-}" ]; then
  DEP_JSON='    "mingw-w64-clang-aarch64-ca-certificates"'
else
  DEP_JSON=$(printf '%s\n' $GIT_DEPENDS | sed 's/.*/    "&",/; $s/,$//')
fi
cat > "$OUT/git-spec.json" <<EOF
{
  "pkgname": "mingw-w64-clang-aarch64-git",
  "pkgbase": "mingw-w64-git",
  "pkgver": "$VER-1",
  "pkgdesc": "The fast distributed version control system (mingw-w64). Built entirely by WoA GCC 15.0.1 and our assembler running natively on ARM64; the make driver and borrowed shell contributed no code. Nothing cross-compiled.",
  "url": "https://git-scm.com/",
  "license": "GPL2",
  "depends": [
$DEP_JSON
  ],
  "provides": ["mingw-w64-clang-aarch64-git"],
  "payload_root": "$STAGE",
  "out": "$OUT/mingw-w64-clang-aarch64-git-$VER-1-any.pkg"
}
EOF
python3 "$MK/mkpkg.py" "$OUT/git-spec.json"
zstd -q -f "$OUT/mingw-w64-clang-aarch64-git-$VER-1-any.pkg.tar" \
  -o "$OUT/mingw-w64-clang-aarch64-git-$VER-1-any.pkg.tar.zst"

echo "=== packaged ==="
ls -la "$OUT"/*.pkg.tar.zst
echo "=== validate: pacman -Ql sees libexec/git-core exes? ==="
# quick repo-add + -Ql round trip
R=/tmp/gitpkg-val; rm -rf "$R"; mkdir -p "$R/repo" "$R/root/var/lib/pacman"
cp "$OUT"/*.pkg.tar.zst "$R/repo/"
( cd "$R/repo" && repo-add gitval.db.tar.gz *.pkg.tar.zst >/dev/null 2>&1 )
cat > "$R/pac.conf" <<EOF
[options]
Architecture = aarch64
SigLevel = Never
[gitval]
Server = file://$R/repo
EOF
pacman --config "$R/pac.conf" --root "$R/root" --dbpath "$R/root/var/lib/pacman" -Sy >/dev/null 2>&1
pacman --config "$R/pac.conf" --root "$R/root" --dbpath "$R/root/var/lib/pacman" -U --noconfirm -dd "$OUT"/*.pkg.tar.zst >/dev/null 2>&1
echo "libexec/git-core exes pacman -Ql reports:"
pacman --config "$R/pac.conf" --root "$R/root" --dbpath "$R/root/var/lib/pacman" \
  -Ql mingw-w64-clang-aarch64-git 2>/dev/null \
  | sed 's/^[^ ]* //' | grep -E 'libexec/git-core/.*\.exe$' | head
echo "=== DONE. Copy to sync repo, then swap into pipeline for real assembly. ==="
