#!/usr/bin/env bash
# Documentation/catalog generation uses existing ARM64 Linux host tools only.
# No compiler, runtime DLL or native configuration is invoked by this stage.
set -euo pipefail
[[ $# == 1 && $1 == /mnt/c/agtc-libs-* && $1 != *..* ]] ||
  { echo "Use the explicitly owned shared-runtime build root under /mnt/c" >&2; exit 2; }
root=$1
mkdir -p "$root/dev/usr/share/info" "$root/logs/docs"
for tool in makeinfo msgfmt; do
  command -v "$tool"
  "$tool" --version | head -n 1
done
for library in libgomp libquadmath; do
  [[ -f $root/build/aarch64-pc-cygwin/$library/Makefile ]] || continue
  if [[ $library == libquadmath ]] &&
     grep -q "^libquad_cv_have_float128=no$" "$root/build/aarch64-pc-cygwin/libquadmath/config.log"; then
    echo "libquadmath is target-disabled by its real __float128 probe; no manual installed."
    continue
  fi
  [[ -f $root/source/$library/$library.texi ]] ||
    { echo "Missing real $library Texinfo source" >&2; exit 1; }
  # These are the upstream info-rule include paths, not substituted content.
  makeinfo -I "$root/source/gcc/doc/include" -I "$root/source/$library" \
    -I "$root/build/aarch64-pc-cygwin/$library" \
    -o "$root/dev/usr/share/info/$library.info" "$root/source/$library/$library.texi" \
    > "$root/logs/docs/$library.stdout" 2> "$root/logs/docs/$library.stderr"
done
for language in de fr; do
  directory=$root/dev/usr/share/locale/$language/LC_MESSAGES
  mkdir -p "$directory"
  msgfmt --check -o "$directory/libstdc++.mo" "$root/source/libstdc++-v3/po/$language.po" \
    > "$root/logs/docs/$language.stdout" 2> "$root/logs/docs/$language.stderr"
done
find "$root/dev/usr/share/info" "$root/dev/usr/share/locale" -type f -print0 |
  sort -z | xargs -0 sha256sum > "$root/logs/docs/generated.sha256"
