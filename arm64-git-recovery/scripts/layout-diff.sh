#!/bin/bash
# Diff our assembled pipeline-test layout against the upstream 403-file manifest.
set -e
UP=/mnt/c/Users/crutkasLocal/.copilot/session-state/ea1641ea-57c0-492d-ab94-fcfddedf1091/files/evidence/upstream-mingit-busybox-arm64-manifest.txt
STAGE=/tmp/pipe-zip/mingit
OUT=/mnt/c/Users/crutkasLocal/.copilot/session-state/ea1641ea-57c0-492d-ab94-fcfddedf1091/files/evidence/B9-LAYOUT-DIFF.txt

# normalise: files only (drop dir entries ending /), strip to clangarm64-relative
grep -v '/$' "$UP" | sort -u > /tmp/up-files.txt
( cd "$STAGE" && find clangarm64 -type f | sort -u ) > /tmp/our-files.txt

up=$(wc -l < /tmp/up-files.txt); our=$(wc -l < /tmp/our-files.txt)

{
echo "B9 — LAYOUT DIFF: our pipeline-test assembly vs upstream MinGit-busybox-arm64"
echo "=============================================================================="
echo "MEASURED against upstream manifest (403 entries; $up files after dropping dirs)"
echo "Our assembled layout: $our files."
echo "NOTE: our layout is the PIPELINE-TEST assembly (upstream git+busybox stand-ins"
echo "+ our GCM stub + our leaves). This diff validates LAYOUT COMPLETENESS, i.e."
echo "whether the pipeline places files where upstream does."
echo
echo "### UPSTREAM-PRESENT, OURS-ABSENT (candidates: capability delta OR gap) ###"
comm -23 /tmp/up-files.txt /tmp/our-files.txt
echo
echo "### OURS-PRESENT, UPSTREAM-ABSENT (extra files we carry) ###"
comm -13 /tmp/up-files.txt /tmp/our-files.txt | head -80
echo "... (truncated; full count below)"
echo
echo "counts: upstream_only=$(comm -23 /tmp/up-files.txt /tmp/our-files.txt | wc -l)  ours_only=$(comm -13 /tmp/up-files.txt /tmp/our-files.txt | wc -l)  common=$(comm -12 /tmp/up-files.txt /tmp/our-files.txt | wc -l)"
} > "$OUT"
cat "$OUT" | head -60
echo "... written to B9-LAYOUT-DIFF.txt"
