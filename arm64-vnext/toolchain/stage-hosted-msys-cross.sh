#!/usr/bin/env bash
set -euo pipefail
trap 'printf "Hosted SDK staging failed at line %s (status %s)\n" "$LINENO" "$?" >&2' ERR
[[ $# == 5 ]] || {
  printf 'Usage: %s RUNTIME_PREFIX POSIX_HELPER NATIVE_SDK NEW_CROSS_PREFIX NATIVE_MANIFEST\n' "$0" >&2
  exit 1
}
runtime=$(realpath "$1")
helper=$(realpath "$2")
native=$(realpath "$3")
output=$4
manifest=$(realpath "$5")
recipe=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target=aarch64-pc-cygwin
[[ $output == /root/arm64-vnext-20260905/toolchain/epochs/* &&
   $output != *..* && ! -e $output ]] || {
  printf 'Choose a new dedicated toolchain epoch prefix: %s\n' "$output" >&2
  exit 1
}
[[ $("$helper/bin/$target-g++" -dumpmachine) == "$target" ]]
version=$("$helper/bin/$target-g++" -dumpversion)
"$helper/bin/$target-g++" -v 2>&1 | grep -q '^Thread model: posix$'
test -s "$native/$target/include/c++/$version/iostream"
test -s "$native/$target/lib/libstdc++.a"
python3 - "$native" "$manifest" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
if data["SchemaVersion"] != 1 or data["Status"] != "qualified":
    raise SystemExit("The native SDK has not completed its independent acceptance")
if data["Target"]["Triple"] != "aarch64-pc-cygwin" or data["Target"]["Profile"] != "MSYS":
    raise SystemExit("Not a qualified MSYS-target SDK")
expected = set()
for entry in data["Files"]:
    file = root / entry["Path"].replace("\\", "/")
    if not file.resolve().is_relative_to(root) or file in expected:
        raise SystemExit("Invalid SDK inventory path")
    expected.add(file)
    if hashlib.sha256(file.read_bytes()).hexdigest() != entry["SHA256"]:
        raise SystemExit(f"SDK inventory changed: {file}")
if expected != {file for file in root.rglob("*") if file.is_file()}:
    raise SystemExit("SDK file set differs from its qualified inventory")
PY
cmp "$runtime/bin/msys-2.0.dll" "$native/bin/msys-2.0.dll"
cmp "$runtime/$target/lib/libmsys-2.0.a" "$native/$target/lib/libmsys-2.0.a"
cmp "$runtime/$target/lib/crt0.o" "$native/$target/lib/crt0.o"

mkdir -p "$output"
cp -a "$helper/." "$output/"
mkdir -p "$output/$target/bin" "$output/lib/gcc/$target/$version" "$output/identities"
# Host tools stay ELF/Linux; target development files come from the
# already-qualified native MSYS SDK, never a MinGW sysroot.
cp -a "$runtime/$target/bin/." "$output/$target/bin/"
cp -a "$native/$target/include" "$native/$target/lib" "$output/$target/"
cp "$native/bin/msys-2.0.dll" "$output/bin/"
for program in ar as dlltool ld ld.bfd nm objcopy objdump ranlib readelf size strings strip windres; do
  if [[ -x $runtime/bin/$target-$program ]]; then
    cp "$runtime/bin/$target-$program" "$output/bin/"
  fi
done
for file in "$native/lib/gcc/$target/$version/"*.a "$native/lib/gcc/$target/$version/"*.o; do
  test -s "$file"
  cp "$file" "$output/lib/gcc/$target/$version/"
done
for header in gcov.h unwind.h; do
  install -m 644 "$native/lib/gcc/$target/$version/include/$header" \
    "$output/lib/gcc/$target/$version/include/$header"
done
cp -a "$native/share/toolchain" "$output/share/"
cp "$manifest" "$output/identities/native-sdk-manifest.json"
python3 "$recipe/generate-msys-specs.py" --compiler "$output/bin/$target-gcc" \
  --output "$output/lib/gcc/$target/$version/msys2.specs" \
  --manifest "$output/identities/msys-profile.json"
install -m 755 "$recipe/msys2-hosted-driver.sh" "$output/bin/msys2-gcc"
install -m 755 "$recipe/msys2-hosted-driver.sh" "$output/bin/msys2-g++"

needs_driver_repair=false
for program in as ld; do
  selected=$("$output/bin/msys2-g++" "-print-prog-name=$program")
  if [[ $(realpath "$selected") != "$output/"* ]]; then
    needs_driver_repair=true
  fi
done
if $needs_driver_repair; then
  bash "$recipe/repair-hosted-cross-drivers.sh" "$output" "$helper"
fi

for library in libstdc++.a libsupc++.a libgcc.a libmsys-2.0.a crt0.o; do
  selected=$("$output/bin/msys2-g++" "-print-file-name=$library")
  [[ $(realpath "$selected") == "$output/"* ]]
  sha256sum "$selected"
done > "$output/identities/selected-libraries.sha256"
for program in cc1plus as ld; do
  selected=$("$output/bin/msys2-g++" "-print-prog-name=$program")
  [[ $(realpath "$selected") == "$output/"* ]]
  sha256sum "$selected"
done > "$output/identities/selected-tools.sha256"
"$output/bin/msys2-g++" -std=c++17 -O2 -c "$recipe/probes/msys-ctype.cc" \
  -o "$output/identities/msys-ctype.o"
"$output/bin/msys2-g++" "$output/identities/msys-ctype.o" \
  -o "$output/identities/msys-ctype.exe"
sha256sum "$output/identities/msys-ctype."{o,exe} > "$output/identities/consumer.sha256"
printf 'HOSTED_MSYS_CROSS_PREFIX=%s (execute the retained consumer on Windows next)\n' "$output"
