#!/usr/bin/env bash
set -euo pipefail
trap 'printf "SDK driver stage failed at line %s (status %s)\n" "$LINENO" "$?" >&2' ERR
[[ $# == 2 ]] || { printf 'Usage: %s STAGED_CROSS_PREFIX ORIGINAL_POSIX_HELPER\n' "$0" >&2; exit 1; }
prefix=$(realpath "$1")
helper=$(realpath "$2")
root=/root/arm64-vnext-20260905/toolchain
source_dir=$root/sources/gcc
target=aarch64-pc-cygwin
recipe=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
build=$root/build/hosted-cross-drivers-$(date -u +%Y%m%dT%H%M%S)-$$
[[ $prefix == "$root/epochs/"* && ! -e $build ]]
mkdir "$build"
exec > >(tee "$build/build.log") 2>&1
exec 9>"$root/bootstrap.lock"
flock -n 9 || { printf 'Another original-root toolchain stage is running\n' >&2; exit 1; }
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
python3 - "$prefix/share/toolchain/source-lock.json" "$recipe" > "$build/patches.txt" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
lock = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
if lock["sources"]["gcc"]["revision"] != "5688a17320e775944bbe795010ebe7e89fc7a628":
    raise SystemExit("Unexpected original SDK source revision")
for patch in lock["sources"]["gcc"]["patches"]:
    path = Path(sys.argv[2]) / patch["file"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != patch["sha256"]:
        raise SystemExit(f"Patch differs from the SDK source lock: {path}")
    print(path)
PY
[[ $(git -C "$source_dir" rev-parse HEAD) == 5688a17320e775944bbe795010ebe7e89fc7a628 ]]
index=$build/expected.index
GIT_INDEX_FILE=$index git -C "$source_dir" read-tree HEAD
while IFS= read -r patch; do
  GIT_INDEX_FILE=$index git -C "$source_dir" apply --cached "$patch"
done < "$build/patches.txt"
GIT_INDEX_FILE=$index git -C "$source_dir" diff --exit-code
[[ -z $(GIT_INDEX_FILE=$index git -C "$source_dir" ls-files --others --exclude-standard) ]]
git -C "$source_dir" diff --binary HEAD > "$build/source.patch"

cd "$build"
# Retain the frontend's configured prefix so GCC's normal relocation logic
# passes its new -iprefix automatically. No application include-path override.
"$source_dir/configure" --target="$target" --prefix="$helper" \
  --with-sysroot="$prefix/$target" --with-native-system-header-dir=/include \
  --with-as="$prefix/$target/bin/as" --with-ld="$prefix/$target/bin/ld" \
  --with-headers=yes --with-newlib --enable-languages=c,c++ --enable-threads=posix \
  --disable-multilib --disable-nls --disable-shared --disable-bootstrap --disable-werror \
  --disable-libstdcxx --disable-libssp --disable-libgomp --disable-libatomic --disable-libquadmath
# DEFAULT_ASSEMBLER/DEFAULT_LINKER bypass -B in the preserved helper. Rebuild
# only its driver/collect2 closure; keep the already-built cc1/cc1plus intact.
make -j1 all-gcc 'TARGET-gcc=xgcc xg++ cpp collect2'
version=$("$prefix/bin/$target-gcc" -dumpversion)
mkdir -p "$build/prior-drivers"
cp "$prefix/bin/"{"$target-gcc","$target-g++","$target-cpp"} "$build/prior-drivers/"
cp "$prefix/libexec/gcc/$target/$version/collect2" "$build/prior-drivers/"
install -m 755 gcc/xgcc "$prefix/bin/$target-gcc"
install -m 755 gcc/xg++ "$prefix/bin/$target-g++"
install -m 755 gcc/cpp "$prefix/bin/$target-cpp"
if [[ -f $prefix/bin/$target-c++ ]]; then
  install -m 755 gcc/xg++ "$prefix/bin/$target-c++"
fi
install -m 755 gcc/collect2 "$prefix/libexec/gcc/$target/$version/collect2"
python3 "$recipe/generate-msys-specs.py" --compiler "$prefix/bin/$target-gcc" \
  --output "$prefix/lib/gcc/$target/$version/msys2.specs" \
  --manifest "$prefix/identities/msys-profile.json"
for program in cc1plus as ld; do
  selected=$("$prefix/bin/msys2-g++" "-print-prog-name=$program")
  [[ $(realpath "$selected") == "$prefix/"* ]]
  sha256sum "$selected"
done > "$prefix/identities/selected-tools.sha256"
"$prefix/bin/msys2-g++" -std=c++17 -O2 -c "$recipe/probes/msys-ctype.cc" \
  -o "$prefix/identities/msys-ctype.o"
"$prefix/bin/msys2-g++" "$prefix/identities/msys-ctype.o" \
  -o "$prefix/identities/msys-ctype.exe"
sha256sum "$prefix/identities/msys-ctype."{o,exe} > "$prefix/identities/consumer.sha256"
printf 'Hosted SDK driver relocation repaired; native target execution remains required.\n'
