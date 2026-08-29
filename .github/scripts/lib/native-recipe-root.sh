#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/path-boundary.sh"

native_recipe_root_needs_alias() {
  local recipe_root=${1:-"$PWD"}
  local recipe_root_native
  # The observed gettext libtool expansion adds 134 characters to its recipe root.
  local path_reserve=${WOARM64_NATIVE_RECIPE_PATH_RESERVE:-160}

  if [[ ! "$path_reserve" =~ ^[1-9][0-9]*$ || $path_reserve -ge 260 ]]; then
    echo "WOARM64_NATIVE_RECIPE_PATH_RESERVE must be between 1 and 259" >&2
    return 2
  fi

  if ! recipe_root_native=$(to_native_path "$recipe_root"); then
    return 2
  fi
  (( ${#recipe_root_native} + path_reserve > 259 ))
}

with_short_native_recipe_root() {
  if [[ $# -eq 0 ]]; then
    echo "with_short_native_recipe_root requires a command" >&2
    return 2
  fi

  local recipe_root
  local recipe_root_native
  local subst_native
  local subst_tool
  local drive_letter
  local drive
  local alias_root
  local command_status
  local command_pid=
  local pending_signal=
  local command_starting=0
  local alias_owned=0
  local signal
  local status
  local old_exit_trap=
  local old_hup_trap=
  local old_int_trap=
  local old_term_trap=
  local trap_state_file

  recipe_root=$(pwd -P)
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
  trap_state_file=$(mktemp "${TMPDIR:-/tmp}/native-recipe-traps.XXXXXX")
  trap -p EXIT > "$trap_state_file"
  IFS= read -r old_exit_trap < "$trap_state_file" || true
  trap -p HUP > "$trap_state_file"
  IFS= read -r old_hup_trap < "$trap_state_file" || true
  trap -p INT > "$trap_state_file"
  IFS= read -r old_int_trap < "$trap_state_file" || true
  trap -p TERM > "$trap_state_file"
  IFS= read -r old_term_trap < "$trap_state_file" || true
  rm -f "$trap_state_file"

  for drive_letter in ${WOARM64_SUBST_DRIVES:-W V U T S R Q P}; do
    if [[ ! "$drive_letter" =~ ^[A-Za-z]$ ]]; then
      echo "Invalid drive letter in WOARM64_SUBST_DRIVES: $drive_letter" >&2
      return 2
    fi

    drive="${drive_letter^^}:"
    if MSYS2_ARG_CONV_EXCL='*' \
         "$subst_tool" "$drive" "$recipe_root_native" >/dev/null 2>&1; then
      alias_root="/${drive_letter,,}"
      alias_owned=1
      break
    fi
  done

  if [[ -z "${alias_root:-}" ]]; then
    echo "No free drive letter is available for the native recipe path boundary" >&2
    return 1
  fi

  cleanup_short_native_recipe_root() {
    if [[ $alias_owned -eq 0 ]]; then
      return 0
    fi
    if [[ "$alias_root" -ef "$recipe_root" ]]; then
      cd "$recipe_root" 2>/dev/null || cd /
      MSYS2_ARG_CONV_EXCL='*' "$subst_tool" "$drive" /D >/dev/null
      alias_owned=0
    else
      echo "Refusing to remove changed native recipe alias $drive" >&2
      return 1
    fi
  }
  restore_native_recipe_traps() {
    trap - EXIT HUP INT TERM
    [[ -z "$old_exit_trap" ]] || eval "$old_exit_trap"
    [[ -z "$old_hup_trap" ]] || eval "$old_hup_trap"
    [[ -z "$old_int_trap" ]] || eval "$old_int_trap"
    [[ -z "$old_term_trap" ]] || eval "$old_term_trap"
  }
  forward_native_recipe_signal() {
    local signal=$1
    local status=$2

    trap - HUP INT TERM
    kill -s "$signal" "$command_pid" 2>/dev/null || true
    wait "$command_pid" 2>/dev/null || true
    cleanup_short_native_recipe_root || status=1
    restore_native_recipe_traps
    exit "$status"
  }
  handle_native_recipe_signal() {
    local signal=$1
    local status=$2

    if [[ $command_starting -eq 1 && -z "$command_pid" ]]; then
      pending_signal="$signal $status"
      return
    fi
    if [[ -z "$command_pid" ]]; then
      cleanup_short_native_recipe_root || status=1
      restore_native_recipe_traps
      exit "$status"
    fi
    forward_native_recipe_signal "$signal" "$status"
  }
  trap cleanup_short_native_recipe_root EXIT
  trap 'handle_native_recipe_signal HUP 129' HUP
  trap 'handle_native_recipe_signal INT 130' INT
  trap 'handle_native_recipe_signal TERM 143' TERM

  if [[ ! "$alias_root" -ef "$recipe_root" ]]; then
    echo "Native recipe alias $drive does not resolve to $recipe_root_native" >&2
    return 1
  fi

  echo "::notice::Native recipe alias: $drive -> $recipe_root_native"
  cd "$alias_root"
  command_starting=1
  MSYS2_WOARM64_RECIPE_HELPER_PID=$BASHPID "$@" <&0 &
  command_pid=$!
  command_starting=0
  if [[ -n "$pending_signal" ]]; then
    read -r signal status <<< "$pending_signal"
    forward_native_recipe_signal "$signal" "$status"
  fi
  if wait "$command_pid"; then
    command_status=0
  else
    command_status=$?
  fi

  if cleanup_short_native_recipe_root; then
    restore_native_recipe_traps
  else
    restore_native_recipe_traps
    return 1
  fi
  return "$command_status"
}
