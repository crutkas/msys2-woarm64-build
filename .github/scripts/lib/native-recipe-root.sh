#!/bin/bash

if [[ -n "${MSYS2_WOARM64_NATIVE_RECIPE_ROOT_SH:-}" ]]; then
  return 0
fi
readonly MSYS2_WOARM64_NATIVE_RECIPE_ROOT_SH=1

source "$(dirname "${BASH_SOURCE[0]}")/path-boundary.sh"

# Single source of truth for the headroom a native recipe root must leave below
# the legacy Win32 boundary. The regression fixtures size themselves from this
# value instead of repeating the number.
WOARM64_NATIVE_RECIPE_PATH_RESERVE_DEFAULT=160

# Survives state release so a caller can scan build output for residue from the
# alias drive that was actually used.
WOARM64_LAST_RECIPE_ALIAS_LETTER=

# Alias bookkeeping lives in namespaced globals rather than in locals of
# with_short_native_recipe_root. The EXIT trap can fire long after that function
# has returned, and locals are gone by then: an emptied ownership flag made the
# cleanup silently decide it owned nothing and leak the mapped drive.
_WOARM64_ALIAS_ACTIVE=0
_WOARM64_ALIAS_OWNED=0
_WOARM64_ALIAS_DRIVE=
_WOARM64_ALIAS_DRIVE_LETTER=
_WOARM64_ALIAS_ROOT=
_WOARM64_ALIAS_RECIPE_ROOT=
_WOARM64_ALIAS_RECIPE_ROOT_NATIVE=
_WOARM64_ALIAS_SUBST_TOOL=
_WOARM64_ALIAS_COMMAND_PID=
_WOARM64_ALIAS_COMMAND_STARTING=0
_WOARM64_ALIAS_PENDING_SIGNAL=
_WOARM64_ALIAS_TRAP_EXIT=
_WOARM64_ALIAS_TRAP_HUP=
_WOARM64_ALIAS_TRAP_INT=
_WOARM64_ALIAS_TRAP_TERM=

native_recipe_root_needs_alias() {
  local recipe_root=${1:-}
  local recipe_root_native
  # The observed gettext libtool expansion adds 134 characters to its recipe root.
  local path_reserve=${WOARM64_NATIVE_RECIPE_PATH_RESERVE:-$WOARM64_NATIVE_RECIPE_PATH_RESERVE_DEFAULT}

  if [[ ! "$path_reserve" =~ ^[1-9][0-9]*$ || $path_reserve -ge 260 ]]; then
    echo "WOARM64_NATIVE_RECIPE_PATH_RESERVE must be between 1 and 259" >&2
    return 2
  fi

  # Default to the physical directory, because that is the path the alias is
  # created for. Deciding on a logical path and mapping a physical one lets a
  # symlinked recipe root take the wrong branch.
  if [[ -z "$recipe_root" ]]; then
    if ! recipe_root=$(pwd -P); then
      return 2
    fi
  fi

  if ! recipe_root_native=$(to_native_path "$recipe_root"); then
    return 2
  fi
  (( ${#recipe_root_native} + path_reserve > 259 ))
}

# Refuses to remove a mapping that no longer resolves to the recipe root it was
# created for, but always releases ownership so the deferred EXIT trap cannot
# re-report or wedge later builds.
cleanup_short_native_recipe_root() {
  local status=0

  if [[ "$_WOARM64_ALIAS_OWNED" != "1" ]]; then
    return 0
  fi

  if [[ "$_WOARM64_ALIAS_ROOT" -ef "$_WOARM64_ALIAS_RECIPE_ROOT" ]]; then
    cd "$_WOARM64_ALIAS_RECIPE_ROOT" 2>/dev/null || cd /
    if ! MSYS2_ARG_CONV_EXCL='*' \
        "$_WOARM64_ALIAS_SUBST_TOOL" "$_WOARM64_ALIAS_DRIVE" /D >/dev/null; then
      echo "Failed to remove native recipe alias $_WOARM64_ALIAS_DRIVE" >&2
      status=1
    fi
  else
    echo "Refusing to remove changed native recipe alias $_WOARM64_ALIAS_DRIVE" >&2
    status=1
  fi

  _WOARM64_ALIAS_OWNED=0
  return "$status"
}

restore_native_recipe_traps() {
  trap - EXIT HUP INT TERM
  [[ -z "$_WOARM64_ALIAS_TRAP_EXIT" ]] || eval "$_WOARM64_ALIAS_TRAP_EXIT"
  [[ -z "$_WOARM64_ALIAS_TRAP_HUP" ]] || eval "$_WOARM64_ALIAS_TRAP_HUP"
  [[ -z "$_WOARM64_ALIAS_TRAP_INT" ]] || eval "$_WOARM64_ALIAS_TRAP_INT"
  [[ -z "$_WOARM64_ALIAS_TRAP_TERM" ]] || eval "$_WOARM64_ALIAS_TRAP_TERM"
  _WOARM64_ALIAS_TRAP_EXIT=
  _WOARM64_ALIAS_TRAP_HUP=
  _WOARM64_ALIAS_TRAP_INT=
  _WOARM64_ALIAS_TRAP_TERM=
}

_woarm64_recipe_release_state() {
  _WOARM64_ALIAS_ACTIVE=0
  _WOARM64_ALIAS_DRIVE=
  _WOARM64_ALIAS_DRIVE_LETTER=
  _WOARM64_ALIAS_ROOT=
  _WOARM64_ALIAS_RECIPE_ROOT=
  _WOARM64_ALIAS_RECIPE_ROOT_NATIVE=
  _WOARM64_ALIAS_SUBST_TOOL=
  _WOARM64_ALIAS_COMMAND_PID=
  _WOARM64_ALIAS_COMMAND_STARTING=0
  _WOARM64_ALIAS_PENDING_SIGNAL=
}

# Every failure path after the traps are armed must go through here, otherwise
# the alias stays mapped and the traps stay installed.
_woarm64_recipe_abort() {
  local status=$1

  cleanup_short_native_recipe_root || status=1
  restore_native_recipe_traps
  _woarm64_recipe_release_state
  return "$status"
}

# Captures a complete trap definition. Reading only the first line truncated a
# multi-line trap body and then re-installed it as a syntax error. The trap -p
# runs in the current shell and the whole file is read back.
_woarm64_capture_traps() {
  local state_file=$1

  trap -p EXIT > "$state_file"
  _WOARM64_ALIAS_TRAP_EXIT=$(cat "$state_file")
  trap -p HUP > "$state_file"
  _WOARM64_ALIAS_TRAP_HUP=$(cat "$state_file")
  trap -p INT > "$state_file"
  _WOARM64_ALIAS_TRAP_INT=$(cat "$state_file")
  trap -p TERM > "$state_file"
  _WOARM64_ALIAS_TRAP_TERM=$(cat "$state_file")
}

forward_native_recipe_signal() {
  local signal=$1
  local status=$2

  trap - HUP INT TERM
  kill -s "$signal" "$_WOARM64_ALIAS_COMMAND_PID" 2>/dev/null || true
  wait "$_WOARM64_ALIAS_COMMAND_PID" 2>/dev/null || true
  cleanup_short_native_recipe_root || status=1
  restore_native_recipe_traps
  _woarm64_recipe_release_state
  exit "$status"
}

handle_native_recipe_signal() {
  local signal=$1
  local status=$2

  if [[ $_WOARM64_ALIAS_COMMAND_STARTING -eq 1 && -z "$_WOARM64_ALIAS_COMMAND_PID" ]]; then
    _WOARM64_ALIAS_PENDING_SIGNAL="$signal $status"
    return
  fi
  if [[ -z "$_WOARM64_ALIAS_COMMAND_PID" ]]; then
    cleanup_short_native_recipe_root || status=1
    restore_native_recipe_traps
    _woarm64_recipe_release_state
    exit "$status"
  fi
  forward_native_recipe_signal "$signal" "$status"
}

# Fails the build when the temporary alias drive leaked into staged package
# content. The drive letter is whichever of the candidates was free, so any
# recorded path under it is both dangling and non-reproducible.
assert_no_native_recipe_alias_residue() {
  local drive_letter=$1
  local root=$2
  local -a matches=()
  local pattern

  if [[ -z "$drive_letter" || -z "$root" ]]; then
    echo "assert_no_native_recipe_alias_residue requires a drive letter and a root" >&2
    return 2
  fi
  if [[ "${WOARM64_SKIP_ALIAS_RESIDUE_SCAN:-0}" == "1" ]]; then
    echo "::warning::Skipping the native recipe alias residue scan by request"
    return 0
  fi
  if [[ ! -d "$root" ]]; then
    return 0
  fi

  # The drive letter must not be preceded by another letter. An unanchored
  # "<letter>:/" matches inside ordinary URLs, and both collisions land on
  # candidate drives: "http://" contains "p:/" and "https://" contains "s:/".
  # gettext bakes its homepage and bug-report URLs into staged artifacts, so the
  # unanchored form would fail exactly the build this alias exists to enable.
  pattern="(^|[^A-Za-z])${drive_letter}:[/\\\\]"
  mapfile -t matches < <(
    grep -r -l -a -i -E -e "$pattern" -- "$root" 2>/dev/null
  )
  if [[ ${#matches[@]} -gt 0 ]]; then
    echo "Native recipe alias ${drive_letter^^}: leaked into staged build output:" >&2
    printf '  %s\n' "${matches[@]}" >&2
    return 1
  fi
}

with_short_native_recipe_root() {
  local recipe_root
  local recipe_root_native
  local subst_native
  local subst_tool
  local drive_letter
  local drive
  local command_status
  local signal
  local status
  local abort_status
  local trap_state_file

  if [[ $# -eq 0 ]]; then
    echo "with_short_native_recipe_root requires a command" >&2
    return 2
  fi
  if [[ "$_WOARM64_ALIAS_ACTIVE" == "1" ]]; then
    echo "with_short_native_recipe_root is already active in this shell" >&2
    return 2
  fi

  if ! recipe_root=$(pwd -P); then
    return 2
  fi
  if ! recipe_root_native=$(to_native_path "$recipe_root"); then
    return 2
  fi
  subst_native="${SYSTEMROOT:-C:\\Windows}\\System32\\subst.exe"
  if ! subst_tool=$(to_msys_path "$subst_native"); then
    return 2
  fi
  if [[ ! -x "$subst_tool" ]]; then
    echo "Native subst.exe is required for the native recipe path boundary" >&2
    return 1
  fi

  if ! trap_state_file=$(mktemp "${TMPDIR:-/tmp}/native-recipe-traps.XXXXXX"); then
    return 2
  fi
  _woarm64_capture_traps "$trap_state_file"
  rm -f "$trap_state_file"

  _WOARM64_ALIAS_ACTIVE=1
  _WOARM64_ALIAS_SUBST_TOOL="$subst_tool"
  _WOARM64_ALIAS_RECIPE_ROOT="$recipe_root"
  _WOARM64_ALIAS_RECIPE_ROOT_NATIVE="$recipe_root_native"

  for drive_letter in ${WOARM64_SUBST_DRIVES:-W V U T S R Q P}; do
    if [[ ! "$drive_letter" =~ ^[A-Za-z]$ ]]; then
      echo "Invalid drive letter in WOARM64_SUBST_DRIVES: $drive_letter" >&2
      restore_native_recipe_traps
      _woarm64_recipe_release_state
      return 2
    fi

    drive="${drive_letter^^}:"
    if MSYS2_ARG_CONV_EXCL='*' \
         "$subst_tool" "$drive" "$recipe_root_native" >/dev/null 2>&1; then
      _WOARM64_ALIAS_DRIVE="$drive"
      _WOARM64_ALIAS_DRIVE_LETTER="${drive_letter,,}"
      _WOARM64_ALIAS_ROOT="/${drive_letter,,}"
      _WOARM64_ALIAS_OWNED=1
      WOARM64_LAST_RECIPE_ALIAS_LETTER="${drive_letter,,}"
      break
    fi
  done

  if [[ -z "$_WOARM64_ALIAS_ROOT" ]]; then
    echo "No free drive letter is available for the native recipe path boundary" >&2
    restore_native_recipe_traps
    _woarm64_recipe_release_state
    return 1
  fi

  trap cleanup_short_native_recipe_root EXIT
  trap 'handle_native_recipe_signal HUP 129' HUP
  trap 'handle_native_recipe_signal INT 130' INT
  trap 'handle_native_recipe_signal TERM 143' TERM

  if [[ ! "$_WOARM64_ALIAS_ROOT" -ef "$recipe_root" ]]; then
    echo "Native recipe alias $drive does not resolve to $recipe_root_native" >&2
    abort_status=1
    _woarm64_recipe_abort 1 || abort_status=$?
    return "$abort_status"
  fi

  echo "::notice::Native recipe alias: $drive -> $recipe_root_native"
  if ! cd "$_WOARM64_ALIAS_ROOT"; then
    abort_status=1
    _woarm64_recipe_abort 1 || abort_status=$?
    return "$abort_status"
  fi

  _WOARM64_ALIAS_COMMAND_STARTING=1
  MSYS2_WOARM64_RECIPE_HELPER_PID=$BASHPID "$@" <&0 &
  _WOARM64_ALIAS_COMMAND_PID=$!
  _WOARM64_ALIAS_COMMAND_STARTING=0
  if [[ -n "$_WOARM64_ALIAS_PENDING_SIGNAL" ]]; then
    read -r signal status <<< "$_WOARM64_ALIAS_PENDING_SIGNAL"
    forward_native_recipe_signal "$signal" "$status"
  fi
  if wait "$_WOARM64_ALIAS_COMMAND_PID"; then
    command_status=0
  else
    command_status=$?
  fi

  if ! cleanup_short_native_recipe_root; then
    # Never overwrite a real failure from the build with the cleanup status.
    if [[ $command_status -eq 0 ]]; then
      command_status=1
    fi
  fi
  restore_native_recipe_traps
  _woarm64_recipe_release_state
  return "$command_status"
}
