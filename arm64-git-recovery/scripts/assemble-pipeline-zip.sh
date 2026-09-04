#!/bin/bash
# Assemble a PIPELINE-TEST MinGit zip from the successful file-list, mirroring release.sh
# layout moves (libexec/git-core/*.exe -> bin) WITHOUT executing any ARM64 binary.
# CONTAINS UPSTREAM git.exe + UPSTREAM busybox + my GCM stub + my leaves -> DO NOT SHIP.
set -e
ROOT=/tmp/pipe-root
LIST=/tmp/pipe-filelist.txt
STAGE=/tmp/pipe-zip/mingit
OUT=/tmp/PIPELINE-TEST-upstream-git-DO-NOT-SHIP.zip
rm -rf /tmp/pipe-zip; mkdir -p "$STAGE"

# 1. copy every listed file from the installed root, preserving relative layout
missing=0; copied=0
while IFS= read -r rel; do
  rel="${rel#/}"
  # list entries are like  tmp/pipe-root/clangarm64/bin/git.exe  OR  clangarm64/...
  case "$rel" in
    tmp/pipe-root/*) src="/$rel"; sub="${rel#tmp/pipe-root/}" ;;
    clangarm64/*)    src="$ROOT/$rel"; sub="$rel" ;;
    *) src="$ROOT/$rel"; sub="$rel" ;;
  esac
  [ -f "$src" ] || { missing=$((missing+1)); continue; }
  mkdir -p "$STAGE/$(dirname "$sub")"
  cp "$src" "$STAGE/$sub"; copied=$((copied+1))
done < "$LIST"
echo "copied=$copied missing=$missing"

# 2. mirror release.sh layout move: libexec/git-core/*.exe that are in the list -> bin/
LX="$STAGE/clangarm64/libexec/git-core"
BIN="$STAGE/clangarm64/bin"
mkdir -p "$BIN"
moved=0
if [ -d "$LX" ]; then
  for f in "$LX"/*.exe; do
    [ -f "$f" ] || continue
    cp "$f" "$BIN/"; moved=$((moved+1))
  done
fi
echo "libexec->bin moved=$moved"

# 3. four-channel DO-NOT-SHIP labelling: a README inside the zip
cat > "$STAGE/PIPELINE-TEST-DO-NOT-SHIP.txt" <<'EOF'
PIPELINE TEST ARTEFACT — DO NOT SHIP — NOT A DELIVERABLE
========================================================
This zip was produced to validate the MinGit-arm64 ASSEMBLY PIPELINE
(sync repo -> repo-add -> pactree closure -> make-file-list.sh
MINIMAL_GIT_WITH_BUSYBOX -> layout moves -> archive) using KNOWN-GOOD
STAND-IN COMPONENTS in the two slots we are still waiting on:

  * git.exe and its transport DLLs  = UPSTREAM MSYS2 clangarm64 git 2.55.0.5
                                      (NOT built by the WoA GCC toolchain)
  * busybox.exe / ash.exe           = UPSTREAM Git-for-Windows busybox-arm64
                                      (NOT built by peer session 1e7a7fd3)

  Genuinely from THIS programme:  the GCM stub (non-functional placeholder)
                                  and the leaf packages (c-ares/libffi/
                                  libtasn1/wineditline).

Its ONLY purpose is A/B isolation: prove the pipeline with known-good parts
so that swapping in our own git.exe and busybox becomes a single-variable
change. A green pipeline here means any later failure is attributable to our
binaries, not to the assembly machinery.

THE REAL DELIVERABLE will contain git.exe built by the native WoA GCC
toolchain and busybox from session 1e7a7fd3. This file is not that.
EOF

# 4. sanity: what git/busybox landed
echo "=== git.exe present? ==="; ls "$BIN"/git.exe 2>/dev/null && echo YES || echo NO
echo "=== busybox present? ==="; ls "$BIN"/busybox.exe "$BIN"/ash.exe 2>/dev/null || true
echo "=== ca-bundle present? ==="; ls "$STAGE/clangarm64/etc/ssl/certs/ca-bundle.crt" 2>/dev/null && echo YES || echo NO

# 5. zip it (filename channel: DO-NOT-SHIP)
( cd /tmp/pipe-zip && python3 -c "import shutil; shutil.make_archive('/tmp/PIPELINE-TEST-upstream-git-DO-NOT-SHIP','zip','/tmp/pipe-zip','mingit')" )
OUT=/tmp/PIPELINE-TEST-upstream-git-DO-NOT-SHIP.zip
echo "=== artefact ==="
ls -la "$OUT"
echo "files in zip: $(python3 -c "import zipfile; print(len(zipfile.ZipFile('$OUT').namelist()))")"
cp "$OUT" /mnt/c/Users/CRUTKA~1/AppData/Local/Temp/mkpkg/
