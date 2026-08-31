#!/bin/bash

# This is an ARM64-runtime fixture, intentionally separate from run.sh's
# host-independent admission suite. Status 77 is a blocked capability, never
# a passing diagnostic result.
set -euo pipefail
export PATH="/usr/bin:/bin${PATH:+:$PATH}"

repo_root=$(realpath "$(dirname "${BASH_SOURCE[0]}")/../..")
source "$repo_root/.github/scripts/lib/path-boundary.sh"

native_make=${NATIVE_MAKE:-/clangarm64/bin/mingw32-make.exe}
if [[ ! -x "$native_make" ]]; then
  echo "BLOCKED: admitted native Make is unavailable: $native_make" >&2
  exit 77
fi

temporary_root=$(mktemp -d)
trap 'rm -rf "$temporary_root"' EXIT
make_root="$temporary_root/native-make-path"
mkdir -p "$make_root"
printf 'VALUE=converted\n' > "$make_root/included.mk"
posix_include=$(to_msys_path "$make_root/included.mk")
native_include=$(to_native_path "$make_root/included.mk")
makefile="$make_root/Makefile"

printf 'include %s\nall:\n\t@echo $(VALUE)\n' "$posix_include" > "$makefile"
if "$native_make" --no-print-directory -f "$(to_native_path "$makefile")" all >/dev/null 2>&1; then
  echo "Assertion failed: native Make unexpectedly accepted an MSYS path" >&2
  exit 1
fi

printf 'include %s\nall:\n\t@echo $(VALUE)\n' "$native_include" > "$makefile"
if [[ "$("$native_make" --no-print-directory -f "$(to_native_path "$makefile")" all)" != "converted" ]]; then
  echo "Assertion failed: native Make rejected centralized Windows conversion" >&2
  exit 1
fi

echo "native Make runtime regression passed"
