#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/path-boundary.sh"
source "$(dirname "${BASH_SOURCE[0]}")/native-toolchain.sh"

# Production argument-conversion policy for the native PE compiler launchers.
#
# The launchers are native (non-MSYS) executables, so the MSYS2 runtime rewrites
# POSIX-looking arguments before they are ever seen. That heuristic is fine for
# plain operands but it does not understand the comma payloads of -Wl,, -Wp, and
# -Wa,, the two-argument -Xlinker form, -specs= or @response files. Those are
# exactly the forms libtool emits for gettext, so this lane excludes those
# payload dialects from the runtime heuristic and converts them in
# native-compiler.sh instead, where the rules are explicit and testable. Keep
# @response arguments under normal MSYS conversion: the compiler launcher turns
# the resulting Windows path back into an MSYS path before reading it, while
# direct native Binutils consumers must never inherit an unusable MSYS @ path.
#
# Every conversion in native-compiler.sh is idempotent, because cygpath -am on
# an already-native path is a no-op. The boundary therefore produces identical
# output whether or not the runtime already converted an argument.
WOARM64_MSYS2_ARG_CONV_EXCL='-Wl,;-Xlinker;-Wp,;-Wa,;-specs='

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

  printf 'launcher-identity-v3 source=%s toolchain=%s\n' \
    "$source_digest" "$toolchain_digest"
}

woarm64_launcher_output_identity() {
  local install_dir=$1
  local image
  local size
  local digest

  for image in "$install_dir/woarm64-gcc.exe" "$install_dir/woarm64-g++.exe"; do
    if ! assert_native_arm64_pe "$image" "installed ${image##*/}" >/dev/null; then
      return 1
    fi
    if ! size=$(stat -c %s -- "$image") || [[ ! "$size" =~ ^[1-9][0-9]*$ ]]; then
      echo "Unable to size installed native compiler launcher: $image" >&2
      return 1
    fi
    if ! digest=$(sha256sum -- "$image" | cut -d' ' -f1) || [[ -z "$digest" ]]; then
      echo "Unable to digest installed native compiler launcher: $image" >&2
      return 1
    fi
    printf '%s size=%s sha256=%s\n' "${image##*/}" "$size" "$digest"
  done
}

woarm64_launcher_stamp() {
  local install_dir=$1
  local identity=$2
  local output_identity

  if ! output_identity=$(woarm64_launcher_output_identity "$install_dir"); then
    return 1
  fi
  printf '%s\n%s\n' "$identity" "$output_identity"
}

woarm64_launcher_cache_is_valid() {
  local install_dir=$1
  local identity=$2
  local stamp_file="$install_dir/native-compiler-launcher.identity"
  local expected_stamp

  [[ -x "$install_dir/woarm64-gcc.exe" &&
     -x "$install_dir/woarm64-g++.exe" &&
     -f "$stamp_file" ]] || return 1

  # A matching input identity only proves the compiler and source are unchanged.
  # Bind the stamp to the exact output bytes and sizes as well, so either a
  # foreign replacement or a different-but-valid ARM64 launcher forces rebuild.
  if ! expected_stamp=$(woarm64_launcher_stamp "$install_dir" "$identity"); then
    return 1
  fi
  [[ "$(< "$stamp_file")" == "$expected_stamp" ]]
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
# of them is currently executing. Each acquisition stamps the lock with a unique
# owner token so release can tell an abandoned lock it reclaimed from a lock a
# newer owner has since taken.
_WOARM64_LAUNCHER_LOCK_TOKEN=
woarm64_acquire_launcher_lock() {
  local lock_dir=$1
  local timeout=${WOARM64_LAUNCHER_LOCK_TIMEOUT:-300}
  local stale=${WOARM64_LAUNCHER_LOCK_STALE:-900}
  local waited=0
  local reclaimed=0
  local age
  local token="$BASHPID:$(date +%s):${RANDOM}${RANDOM}"
  local reclaim_dir

  while ! mkdir "$lock_dir" 2>/dev/null; do
    if [[ $reclaimed -eq 0 ]] && age=$(woarm64_path_age_seconds "$lock_dir") &&
        (( age > stale )); then
      echo "::warning::Reclaiming a stale native launcher lock after ${age}s: $lock_dir"
      reclaimed=1
      reclaim_dir="${lock_dir}.stale.${token//:/_}"
      # Rename is atomic. Unlike rm -rf, it cannot remove a new lock acquired
      # after the stale age was measured by this contender.
      if mv -- "$lock_dir" "$reclaim_dir" 2>/dev/null; then
        rm -rf -- "$reclaim_dir" || return 1
      fi
      continue
    fi
    if (( waited >= timeout )); then
      echo "Timed out waiting for the native compiler launcher lock: $lock_dir" >&2
      return 1
    fi
    sleep 1
    waited=$(( waited + 1 ))
  done

  # Recording ownership must succeed: without it release cannot prove this shell
  # still holds the lock, so a failure here releases the directory and fails.
  _WOARM64_LAUNCHER_LOCK_TOKEN=$token
  if ! printf '%s\n' "$token" > "$lock_dir/owner"; then
    echo "Unable to record ownership of the native launcher lock: $lock_dir" >&2
    rm -rf -- "$lock_dir"
    _WOARM64_LAUNCHER_LOCK_TOKEN=
    return 1
  fi
}

# Only the shell that still owns the lock may remove it. A builder whose lock was
# reclaimed as stale while it was paused must never delete the lock a new owner
# has since taken, which unconditional rm -rf would do.
woarm64_release_launcher_lock() {
  local lock_dir=$1
  local recorded

  if [[ -z "$_WOARM64_LAUNCHER_LOCK_TOKEN" ]]; then
    return 0
  fi
  recorded=$(cat "$lock_dir/owner" 2>/dev/null) || recorded=
  if [[ "$recorded" == "$_WOARM64_LAUNCHER_LOCK_TOKEN" ]]; then
    rm -rf -- "$lock_dir"
  else
    echo "::warning::Native launcher lock changed owner before release; leaving it for its new owner: $lock_dir" >&2
  fi
  _WOARM64_LAUNCHER_LOCK_TOKEN=
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
  local stamp

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

  # Verify what is actually on disk, not just what was built. A partial install
  # that replaced one launcher and not the other must not reach the stamp.
  if ! stamp=$(woarm64_launcher_stamp "$install_dir" "$identity"); then
    return 1
  fi

  if ! printf '%s' "$stamp" > "$stamp_file.staged.$$" ||
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

  woarm64_release_launcher_lock "$lock_dir"
  return "$status"
}
