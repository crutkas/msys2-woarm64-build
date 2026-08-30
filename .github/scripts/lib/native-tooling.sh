#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/path-boundary.sh"
source "$(dirname "${BASH_SOURCE[0]}")/native-toolchain.sh"

# Production argument-conversion policy for the native PE compiler launchers.
#
# The launchers are native (non-MSYS) executables, so the MSYS2 runtime rewrites
# POSIX-looking arguments before they are ever seen. That heuristic is fine for
# plain operands but it does not understand the comma payloads of -Wl,, -Wp, and
# -Wa,, the two-argument -Xlinker form, -specs= or @response files. Those are
# exactly the forms libtool emits for gettext, so this lane excludes them from
# the runtime heuristic and converts them in native-compiler.sh instead, where
# the rules are explicit and testable.
#
# Every conversion in native-compiler.sh is idempotent, because cygpath -am on
# an already-native path is a no-op. The boundary therefore produces identical
# output whether or not the runtime already converted an argument.
WOARM64_MSYS2_ARG_CONV_EXCL='-Wl,;-Xlinker;-Wp,;-Wa,;-specs=;@'

woarm64_launcher_install_dir() {
  printf '%s\n' "${WOARM64_LAUNCHER_INSTALL_DIR:-/usr/local/libexec/msys2-woarm64}"
}

# The cache key covers the launcher source *and* the toolchain that turns it
# into a PE. Keying on the source alone lets a launcher emitted by a revoked
# assembler or linker survive a binutils replacement, because the .c file is
# unchanged. The v2 prefix guarantees a stamp written by the old source-only
# scheme can never compare equal.
native_launcher_identity() {
  local install_dir=$1
  local source_file="$install_dir/native-compiler-launcher.c"
  local source_digest
  local toolchain_digest

  if [[ ! -f "$source_file" ]]; then
    echo "Native compiler launcher source is missing: $source_file" >&2
    return 1
  fi
  if ! source_digest=$(sha256sum -- "$source_file" | cut -d' ' -f1) ||
      [[ -z "$source_digest" ]]; then
    echo "Unable to digest the native compiler launcher source" >&2
    return 1
  fi
  if ! toolchain_digest=$(native_toolchain_identity_digest); then
    return 1
  fi

  printf 'launcher-identity-v2 source=%s toolchain=%s\n' \
    "$source_digest" "$toolchain_digest"
}

woarm64_launcher_cache_is_valid() {
  local install_dir=$1
  local identity=$2
  local stamp_file="$install_dir/native-compiler-launcher.identity"

  [[ -x "$install_dir/woarm64-gcc.exe" &&
     -x "$install_dir/woarm64-g++.exe" &&
     -f "$stamp_file" &&
     "$(< "$stamp_file")" == "$identity" ]]
}

woarm64_path_age_seconds() {
  local target=$1
  local modified

  modified=$(stat -c %Y -- "$target" 2>/dev/null) || return 1
  [[ "$modified" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "$(( $(date +%s) - modified ))"
}

# mkdir is atomic on every filesystem this lane runs on, so it serialises
# concurrent package builds that would otherwise race to replace a launcher one
# of them is currently executing.
woarm64_acquire_launcher_lock() {
  local lock_dir=$1
  local timeout=${WOARM64_LAUNCHER_LOCK_TIMEOUT:-300}
  local stale=${WOARM64_LAUNCHER_LOCK_STALE:-900}
  local waited=0
  local reclaimed=0
  local age

  while ! mkdir "$lock_dir" 2>/dev/null; do
    if [[ $reclaimed -eq 0 ]] && age=$(woarm64_path_age_seconds "$lock_dir") &&
        (( age > stale )); then
      echo "::warning::Reclaiming a stale native launcher lock after ${age}s: $lock_dir"
      reclaimed=1
      rm -rf -- "$lock_dir" || return 1
      continue
    fi
    if (( waited >= timeout )); then
      echo "Timed out waiting for the native compiler launcher lock: $lock_dir" >&2
      return 1
    fi
    sleep 1
    waited=$(( waited + 1 ))
  done

  printf '%s\n' "$BASHPID" > "$lock_dir/owner" 2>/dev/null || true
}

# Windows refuses to replace a mapped image, so a launcher being executed by a
# parallel recipe makes the rename fail rather than corrupt anything. Retry
# briefly, then fail loudly instead of leaving a half-updated private toolchain.
woarm64_install_launcher_image() {
  local source=$1
  local target=$2
  local attempts=${WOARM64_LAUNCHER_INSTALL_ATTEMPTS:-10}
  local attempt=0
  local staged="$target.staged.$$"

  if ! cp -f -- "$source" "$staged"; then
    return 1
  fi
  if ! chmod 0755 -- "$staged"; then
    rm -f -- "$staged"
    return 1
  fi

  while :; do
    if mv -f -- "$staged" "$target"; then
      return 0
    fi
    attempt=$(( attempt + 1 ))
    if (( attempt >= attempts )); then
      rm -f -- "$staged"
      echo "Unable to replace the native compiler launcher; it may be running: $target" >&2
      return 1
    fi
    sleep 1
  done
}

woarm64_build_and_install_launchers() {
  local install_dir=$1
  local identity=$2
  local source_file="$install_dir/native-compiler-launcher.c"
  local stamp_file="$install_dir/native-compiler-launcher.identity"
  local gcc_launcher="$install_dir/woarm64-gcc.exe"
  local gxx_launcher="$install_dir/woarm64-g++.exe"
  local compiler
  local build_directory
  local built
  local status=0

  compiler=$(native_launcher_compiler_path)
  if ! build_directory=$(mktemp -d "${TMPDIR:-/tmp}/wl.XXXXXX"); then
    return 1
  fi
  built="$build_directory/launcher.exe"

  if ! (
    set -e
    native_temp=$(to_native_path "${TMPDIR:-/tmp}")
    cp -f -- "$source_file" "$build_directory/l.c"
    PATH="$(native_tool_bindir):$PATH" \
      TMP="$native_temp" TEMP="$native_temp" TMPDIR="$native_temp" \
      "$compiler" -c \
      "$(to_native_path "$build_directory/l.c")" \
      -o "$(to_native_path "$build_directory/l.o")"
    PATH="$(native_tool_bindir):$PATH" \
      TMP="$native_temp" TEMP="$native_temp" TMPDIR="$native_temp" \
      "$compiler" -s \
      "$(to_native_path "$build_directory/l.o")" \
      -o "$(to_native_path "$built")"
  ); then
    rm -rf -- "$build_directory"
    return 1
  fi

  # A launcher that is not itself a pure ARM64 image would silently reintroduce
  # an emulated hop into every compile, so refuse to install one.
  if ! assert_native_arm64_pe "$built" "native compiler launcher"; then
    rm -rf -- "$build_directory"
    return 1
  fi

  # Invalidate before mutating. An interrupted install then leaves an obviously
  # stale cache instead of launchers that silently disagree with their stamp.
  if ! rm -f -- "$stamp_file"; then
    rm -rf -- "$build_directory"
    return 1
  fi

  if ! woarm64_install_launcher_image "$built" "$gcc_launcher" ||
      ! woarm64_install_launcher_image "$built" "$gxx_launcher"; then
    status=1
  fi
  rm -rf -- "$build_directory"
  if [[ $status -ne 0 ]]; then
    return 1
  fi

  if ! printf '%s\n' "$identity" > "$stamp_file.staged.$$" ||
      ! mv -f -- "$stamp_file.staged.$$" "$stamp_file"; then
    rm -f -- "$stamp_file.staged.$$"
    return 1
  fi
}

ensure_native_compiler_launchers() {
  local install_dir
  local lock_dir
  local compiler
  local identity
  local status

  install_dir=$(woarm64_launcher_install_dir)
  lock_dir="$install_dir/.launcher-lock"
  compiler=$(native_launcher_compiler_path)

  if [[ ! -x "$compiler" ]]; then
    echo "Native ARM64 GCC must be installed before building compiler launchers: $compiler" >&2
    return 1
  fi
  if ! identity=$(native_launcher_identity "$install_dir"); then
    return 1
  fi
  if woarm64_launcher_cache_is_valid "$install_dir" "$identity"; then
    return 0
  fi

  if ! woarm64_acquire_launcher_lock "$lock_dir"; then
    return 1
  fi

  # Recompute under the lock: a concurrent build may have installed launchers
  # for a different toolchain while this one waited.
  if identity=$(native_launcher_identity "$install_dir"); then
    if woarm64_launcher_cache_is_valid "$install_dir" "$identity"; then
      status=0
    else
      woarm64_build_and_install_launchers "$install_dir" "$identity"
      status=$?
    fi
  else
    status=1
  fi

  rm -rf -- "$lock_dir"
  return "$status"
}
