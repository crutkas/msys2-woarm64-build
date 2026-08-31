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
# unchanged. The v4 prefix also makes prior stamps incompatible because each
# launcher pair must be byte-for-byte identical copies of one generated image.
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

  printf 'launcher-identity-v4 source=%s toolchain=%s\n' \
    "$source_digest" "$toolchain_digest"
}

woarm64_launcher_output_identity() {
  local install_dir=$1
  local gcc_launcher="$install_dir/woarm64-gcc.exe"
  local gxx_launcher="$install_dir/woarm64-g++.exe"
  local size
  local digest
  local gcc_size
  local gcc_digest

  if ! assert_native_arm64_pe "$gcc_launcher" "installed ${gcc_launcher##*/}" >/dev/null ||
      ! assert_native_arm64_pe "$gxx_launcher" "installed ${gxx_launcher##*/}" >/dev/null; then
    return 1
  fi
  if ! gcc_size=$(stat -c %s -- "$gcc_launcher") ||
      [[ ! "$gcc_size" =~ ^[1-9][0-9]*$ ]] ||
      ! gcc_digest=$(sha256sum -- "$gcc_launcher" | cut -d' ' -f1) ||
      [[ -z "$gcc_digest" ]]; then
    echo "Unable to identify installed native GCC launcher: $gcc_launcher" >&2
    return 1
  fi
  if ! size=$(stat -c %s -- "$gxx_launcher") ||
      [[ ! "$size" =~ ^[1-9][0-9]*$ ]] ||
      ! digest=$(sha256sum -- "$gxx_launcher" | cut -d' ' -f1) ||
      [[ -z "$digest" ]]; then
    echo "Unable to identify installed native G++ launcher: $gxx_launcher" >&2
    return 1
  fi
  if [[ "$gcc_size" != "$size" || "$gcc_digest" != "$digest" ]]; then
    echo "Native compiler launchers differ; refusing a mixed generated pair" >&2
    return 1
  fi
  printf 'launcher-pair size=%s sha256=%s\n' "$gcc_size" "$gcc_digest"
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
# of them is currently executing. Each acquisition creates a unique ownership
# marker. Release only unlinks that marker and then non-recursively removes an
# empty lock directory, so an old owner cannot delete a lock recreated by a
# reclaimer.
_WOARM64_LAUNCHER_LOCK_TOKEN=

woarm64_launcher_lock_markers() {
  local lock_dir=$1
  local nullglob_was_enabled=0
  local marker
  local -a markers=()

  if shopt -q nullglob; then
    nullglob_was_enabled=1
  else
    shopt -s nullglob
  fi
  markers=("$lock_dir"/owner "$lock_dir"/owner.*)
  if [[ $nullglob_was_enabled -eq 0 ]]; then
    shopt -u nullglob
  fi
  for marker in "${markers[@]}"; do
    [[ -f "$marker" ]] || continue
    printf '%s\n' "$marker"
  done
}

woarm64_launcher_lock_is_owned() {
  local lock_dir=$1
  local owner_marker
  local recorded

  if [[ -z "$_WOARM64_LAUNCHER_LOCK_TOKEN" ]]; then
    return 1
  fi
  owner_marker="${lock_dir}/owner.${_WOARM64_LAUNCHER_LOCK_TOKEN//:/_}"
  if [[ ! -f "$owner_marker" ]]; then
    echo "Native launcher lock ownership was lost: $lock_dir" >&2
    return 1
  fi
  recorded=$(< "$owner_marker")
  if [[ "$recorded" != "$_WOARM64_LAUNCHER_LOCK_TOKEN" ]]; then
    echo "Native launcher lock ownership marker is invalid: $owner_marker" >&2
    return 1
  fi
}

woarm64_launcher_lock_owner_is_dead() {
  local owner_marker=$1
  local recorded
  local owner_pid

  if [[ ! -f "$owner_marker" ]]; then
    return 1
  fi
  recorded=$(< "$owner_marker")
  if [[ ! "$recorded" =~ ^([1-9][0-9]*):[0-9]+:[0-9]+$ ]]; then
    echo "Native launcher lock owner marker is not a valid process token: $owner_marker" >&2
    return 1
  fi
  owner_pid=${BASH_REMATCH[1]}
  if kill -0 "$owner_pid" 2>/dev/null; then
    echo "Native launcher lock is still owned by live process $owner_pid: $owner_marker" >&2
    return 1
  fi
}

woarm64_remove_stale_launcher_lock() {
  local stale_lock_dir=$1
  local marker
  local nullglob_was_enabled=0
  local -a markers=()

  if shopt -q nullglob; then
    nullglob_was_enabled=1
  else
    shopt -s nullglob
  fi
  markers=(
    "$stale_lock_dir"/owner
    "$stale_lock_dir"/owner.*
    "$stale_lock_dir"/reclaim.*
  )
  if [[ $nullglob_was_enabled -eq 0 ]]; then
    shopt -u nullglob
  fi
  for marker in "${markers[@]}"; do
    if ! rm -f -- "$marker"; then
      echo "Unable to remove stale native launcher lock marker: $marker" >&2
      return 1
    fi
  done
  if ! rmdir -- "$stale_lock_dir"; then
    echo "Unable to remove stale native launcher lock directory: $stale_lock_dir" >&2
    return 1
  fi
}

woarm64_acquire_launcher_lock() {
  local lock_dir=$1
  local timeout=${WOARM64_LAUNCHER_LOCK_TIMEOUT:-300}
  local stale=${WOARM64_LAUNCHER_LOCK_STALE:-900}
  local waited=0
  local reclaimed=0
  local age
  local token="$BASHPID:$(date +%s):${RANDOM}${RANDOM}"
  local reclaim_dir
  local owner_marker
  local cleanup_status
  local stale_marker
  local reclaim_marker
  local -a stale_markers=()

  while ! mkdir "$lock_dir" 2>/dev/null; do
    if [[ $reclaimed -eq 0 ]] && age=$(woarm64_path_age_seconds "$lock_dir") &&
        (( age > stale )); then
      mapfile -t stale_markers < <(woarm64_launcher_lock_markers "$lock_dir")
      if (( ${#stale_markers[@]} != 1 )); then
        echo "Refusing to reclaim a native launcher lock without exactly one owner marker: $lock_dir" >&2
        return 1
      fi
      stale_marker=${stale_markers[0]}
      if ! woarm64_launcher_lock_owner_is_dead "$stale_marker"; then
        echo "Refusing to reclaim a native launcher lock with a live or unverifiable owner: $lock_dir" >&2
        return 1
      fi
      echo "::warning::Reclaiming a stale native launcher lock after ${age}s: $lock_dir"
      reclaimed=1
      reclaim_dir="${lock_dir}.stale.${token//:/_}"
      reclaim_marker="${lock_dir}/reclaim.${token//:/_}"
      # Claim the precise stale owner atomically before moving the directory.
      # If it released and a new owner acquired the path after the age check,
      # this rename fails because its distinct marker is no longer present.
      if mv -- "$stale_marker" "$reclaim_marker" 2>/dev/null; then
        # Subsequent cleanup addresses only this detached old directory rather
        # than a fresh lock a new owner creates after this atomic move.
        if ! mv -- "$lock_dir" "$reclaim_dir"; then
          echo "Unable to detach claimed stale native launcher lock: $lock_dir" >&2
          return 1
        fi
        if ! woarm64_remove_stale_launcher_lock "$reclaim_dir"; then
          return 1
        fi
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

  # An unowned lock is never reclaimed, closing the unavoidable mkdir-to-marker
  # interval. A marked lock is reclaimed only after its owner PID is dead, so a
  # paused owner cannot resume after reclamation and publish output.
  _WOARM64_LAUNCHER_LOCK_TOKEN=$token
  owner_marker="${lock_dir}/owner.${token//:/_}"
  if ! printf '%s\n' "$token" > "$owner_marker"; then
    echo "Unable to record ownership of the native launcher lock: $lock_dir" >&2
    cleanup_status=0
    if [[ -e "$owner_marker" ]] && ! rm -f -- "$owner_marker"; then
      cleanup_status=1
    fi
    if ! rmdir -- "$lock_dir"; then
      cleanup_status=1
    fi
    _WOARM64_LAUNCHER_LOCK_TOKEN=
    return "$(( cleanup_status == 0 ? 1 : cleanup_status ))"
  fi
}

# Only the shell that still owns the unique marker may remove it. A builder
# whose lock was reclaimed while paused finds no marker at its original path and
# therefore never attempts to remove the new owner's directory.
woarm64_release_launcher_lock() {
  local lock_dir=$1
  local owner_marker
  local status=0

  if [[ -z "$_WOARM64_LAUNCHER_LOCK_TOKEN" ]]; then
    return 0
  fi

  owner_marker="${lock_dir}/owner.${_WOARM64_LAUNCHER_LOCK_TOKEN//:/_}"
  if [[ ! -e "$owner_marker" ]]; then
    echo "::warning::Native launcher lock changed owner before release; leaving it for its new owner: $lock_dir" >&2
    _WOARM64_LAUNCHER_LOCK_TOKEN=
    return 0
  fi
  if ! rm -- "$owner_marker"; then
    echo "Unable to remove native launcher ownership marker: $owner_marker" >&2
    status=1
  elif ! rmdir -- "$lock_dir"; then
    echo "Unable to remove native launcher lock directory: $lock_dir" >&2
    status=1
  fi
  _WOARM64_LAUNCHER_LOCK_TOKEN=
  return "$status"
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
  local lock_dir=$3
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
  if ! woarm64_launcher_lock_is_owned "$lock_dir" ||
      ! rm -f -- "$stamp_file"; then
    rm -rf -- "$build_directory"
    return 1
  fi

  if ! woarm64_launcher_lock_is_owned "$lock_dir" ||
      ! woarm64_install_launcher_image "$built" "$gcc_launcher" ||
      ! woarm64_launcher_lock_is_owned "$lock_dir" ||
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

  if ! woarm64_launcher_lock_is_owned "$lock_dir" ||
      ! printf '%s' "$stamp" > "$stamp_file.staged.$$" ||
      ! woarm64_launcher_lock_is_owned "$lock_dir" ||
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
  local release_status

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
  # for a different toolchain while this one waited. A stale owner resumed after
  # reclamation must stop before it can invalidate or publish either launcher.
  if ! woarm64_launcher_lock_is_owned "$lock_dir"; then
    status=1
  elif identity=$(native_launcher_identity "$install_dir"); then
    if woarm64_launcher_cache_is_valid "$install_dir" "$identity"; then
      status=0
    else
      woarm64_build_and_install_launchers "$install_dir" "$identity" "$lock_dir"
      status=$?
    fi
  else
    status=1
  fi

  release_status=0
  if woarm64_release_launcher_lock "$lock_dir"; then
    :
  else
    release_status=$?
    if [[ $status -eq 0 ]]; then
      status=$release_status
    fi
  fi
  return "$status"
}
