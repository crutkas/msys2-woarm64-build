#!/usr/bin/env bash
set -euo pipefail
trap 'printf "Cross assembler staging failed at line %s (status %s)\n" "$LINENO" "$?" >&2' ERR
[[ $# == 4 ]] || {
  printf 'Usage: %s BASELINE_SDK ASSEMBLER_EPOCH ORIGINAL_POSIX_HELPER NEW_SDK\n' "$0" >&2
  exit 1
}
baseline=$(realpath "$1")
epoch=$(realpath "$2")
helper=$(realpath "$3")
output=$4
recipe=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target=aarch64-pc-cygwin
[[ $output == /root/arm64-vnext-20260905/toolchain/epochs/* && $output != *..* && ! -e $output ]]
assembler=$epoch/cross-as/bin/$target-as
test -x "$assembler"
"$assembler" --version | grep -q "target of .*aarch64-pc-cygwin"
mkdir -p "$output/identities"
for directory in bin lib libexec share include "$target"; do
  if [[ -d $baseline/$directory ]]; then
    cp -a "$baseline/$directory" "$output/"
  fi
done
sha256sum "$baseline/$target/bin/as" "$baseline/bin/$target-as" \
  > "$output/identities/baseline-assemblers.sha256"
cp "$assembler" "$output/bin/$target-as"
cp "$assembler" "$output/$target/bin/as"
cp -a "$epoch/identities" "$output/identities/assembler-source"

# The preserved cross driver's absolute DEFAULT_ASSEMBLER bypasses -B.
# Rebase only its driver/collect2 configuration, not the compiler backends.
bash "$recipe/repair-hosted-cross-drivers.sh" "$output" "$helper"
python3 -B "$recipe/test-gas-fp-unwind.py" --assembler "$output/$target/bin/as" \
  --output "$output/identities/fp-encoding"
"$output/$target/bin/as" "$recipe/probes/fp-unwind-fixtures.s" \
  -o "$output/identities/fp-unwind-fixtures.o"
sha256sum "$output/bin/$target-as" "$output/$target/bin/as" \
  "$output/identities/fp-unwind-fixtures.o" > "$output/identities/fp-outputs.sha256"
printf 'CROSS_FP_SDK=%s (native unwind execution still required)\n' "$output"
