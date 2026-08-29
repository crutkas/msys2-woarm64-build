#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/path-boundary.sh"

ensure_native_compiler_launchers() {
  local install_dir=/usr/local/libexec/msys2-woarm64
  local source_file="$install_dir/native-compiler-launcher.c"
  local stamp_file="$install_dir/native-compiler-launcher.sha256"
  local gcc_launcher="$install_dir/woarm64-gcc.exe"
  local gxx_launcher="$install_dir/woarm64-g++.exe"
  local source_digest
  local build_directory
  local temporary_source
  local temporary_object
  local temporary_executable
  local native_temp

  if [[ ! -x /mingwarm64/bin/gcc.exe ]]; then
    echo "Native ARM64 GCC must be installed before building compiler launchers" >&2
    return 1
  fi

  source_digest=$(sha256sum "$source_file" | cut -d' ' -f1)
  if [[ -x "$gcc_launcher" && -x "$gxx_launcher" &&
        -f "$stamp_file" && "$(< "$stamp_file")" == "$source_digest" ]]; then
    return 0
  fi

  build_directory=$(mktemp -d "${TMPDIR:-/tmp}/wl.XXXXXX") || return 1
  temporary_source="$build_directory/l.c"
  temporary_object="$build_directory/l.o"
  temporary_executable="$build_directory/l.exe"
  if ! (
    set -e
    cleanup_launcher_build() {
      rm -f "$temporary_source" "$temporary_object" "$temporary_executable"
      rmdir "$build_directory" 2>/dev/null || true
    }
    trap cleanup_launcher_build EXIT

    cp -f "$source_file" "$temporary_source"
    native_temp=$(to_native_path "${TMPDIR:-/tmp}")
    PATH="/mingwarm64/bin:$PATH" \
      TMP="$native_temp" TEMP="$native_temp" TMPDIR="$native_temp" \
      /mingwarm64/bin/gcc.exe -c \
      "$(to_native_path "$temporary_source")" \
      -o "$(to_native_path "$temporary_object")"
    PATH="/mingwarm64/bin:$PATH" \
      TMP="$native_temp" TEMP="$native_temp" TMPDIR="$native_temp" \
      /mingwarm64/bin/gcc.exe -s \
      "$(to_native_path "$temporary_object")" \
      -o "$(to_native_path "$temporary_executable")"
    mv -f "$temporary_executable" "$gcc_launcher"
  ); then
    return 1
  fi

  cp -f "$gcc_launcher" "$gxx_launcher"
  chmod 0755 "$gcc_launcher" "$gxx_launcher"
  printf '%s\n' "$source_digest" > "$stamp_file"
}
