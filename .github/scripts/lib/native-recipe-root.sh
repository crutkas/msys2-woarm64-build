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
WOARM64_RECIPE_OUTPUT_SCAN_ROOTS=()
WOARM64_RECIPE_EFFECTIVE_OUTPUT_DESTINATIONS=()
WOARM64_RECIPE_OUTPUT_DESTINATION_NAMES=(
  PKGDEST SRCDEST SRCPKGDEST LOGDEST BUILDDIR
)

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
_WOARM64_ALIAS_CALLER_ROOT=
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

_woarm64_remove_native_recipe_alias_mapping() {
  local timeout=${WOARM64_ALIAS_CLEANUP_WAIT_SECONDS:-10}
  local status

  if [[ ! "$timeout" =~ ^[1-9][0-9]*$ ]]; then
    echo "WOARM64_ALIAS_CLEANUP_WAIT_SECONDS must be a positive integer" >&2
    return 2
  fi
  if timeout --foreground --kill-after=2s "${timeout}s" \
      env MSYS2_ARG_CONV_EXCL='*' \
      "$_WOARM64_ALIAS_SUBST_TOOL" "$_WOARM64_ALIAS_DRIVE" /D >/dev/null; then
    return 0
  else
    status=$?
  fi
  echo "Failed to remove native recipe alias $_WOARM64_ALIAS_DRIVE (status $status)" >&2
  return 1
}

# The mapping itself is the owned resource. Its original target can disappear
# during a failed build, but that must never prevent the stored mapping from
# being removed.
cleanup_short_native_recipe_root() {
  local status=0

  if [[ "$_WOARM64_ALIAS_OWNED" != "1" ]]; then
    return 0
  fi

  # A mapped drive cannot be removed while the shell is sitting on it. Prefer
  # the original root, but move to / if that root was deleted by the build.
  if ! cd "$_WOARM64_ALIAS_RECIPE_ROOT" 2>/dev/null && ! cd /; then
    echo "Failed to leave the native recipe alias before cleanup" >&2
    status=1
  fi
  if ! _woarm64_remove_native_recipe_alias_mapping; then
    status=1
  fi

  _WOARM64_ALIAS_OWNED=0
  if [[ -n "$_WOARM64_ALIAS_CALLER_ROOT" ]] &&
      ! cd "$_WOARM64_ALIAS_CALLER_ROOT" 2>/dev/null; then
    echo "Failed to restore the caller directory after native recipe alias cleanup" >&2
    status=1
  fi
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
  _WOARM64_ALIAS_CALLER_ROOT=
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

  if ! trap -p EXIT > "$state_file"; then
    return 1
  fi
  _WOARM64_ALIAS_TRAP_EXIT=$(< "$state_file")
  if ! trap -p HUP > "$state_file"; then
    return 1
  fi
  _WOARM64_ALIAS_TRAP_HUP=$(< "$state_file")
  if ! trap -p INT > "$state_file"; then
    return 1
  fi
  _WOARM64_ALIAS_TRAP_INT=$(< "$state_file")
  if ! trap -p TERM > "$state_file"; then
    return 1
  fi
  _WOARM64_ALIAS_TRAP_TERM=$(< "$state_file")
}

_woarm64_wait_for_native_recipe_child() {
  local pid=$1
  local timeout=${WOARM64_ALIAS_SIGNAL_WAIT_SECONDS:-10}
  local deadline

  if [[ ! "$timeout" =~ ^[1-9][0-9]*$ ]]; then
    echo "WOARM64_ALIAS_SIGNAL_WAIT_SECONDS must be a positive integer" >&2
    return 2
  fi
  deadline=$((SECONDS + timeout))
  while kill -0 -- "-$pid" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for native recipe process group $pid after $timeout seconds; terminating it" >&2
      kill -KILL -- "-$pid" 2>/dev/null || true
      break
    fi
    sleep 1
  done
  wait "$pid" 2>/dev/null || true
}

forward_native_recipe_signal() {
  local signal=$1
  local status=$2

  trap - HUP INT TERM
  if [[ -n "$_WOARM64_ALIAS_COMMAND_PID" ]]; then
    kill -s "$signal" -- "-$_WOARM64_ALIAS_COMMAND_PID" 2>/dev/null || true
    _woarm64_wait_for_native_recipe_child "$_WOARM64_ALIAS_COMMAND_PID" || true
  fi
  # Signal status is the caller-visible contract. Cleanup errors are reported
  # but never turn HUP/INT/TERM into an unrelated status.
  cleanup_short_native_recipe_root || true
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

_woarm64_file_has_native_recipe_alias_residue() {
  local file=$1
  local drive_letter=$2
  local ascii_pattern
  local utf16le_pattern
  local scan_status

  # Keep URL schemes and identifier fragments out of scope while accepting all
  # joined compiler path forms native-compiler.sh supports, plus a bare bounded
  # drive token. Libtool can emit both short (-B) and long (-isystem) forms.
  ascii_pattern="(^|[^[:alnum:]_]|-([ILB]|iquote|isystem|idirafter|include|imacros|o|MF))${drive_letter}:($|[^[:alnum:]_])"
  utf16le_pattern="(?:^|(?:[^A-Za-z0-9_]\x00)|(?:-\x00(?:[ILB]\x00|i\x00q\x00u\x00o\x00t\x00e\x00|i\x00s\x00y\x00s\x00t\x00e\x00m\x00|i\x00d\x00i\x00r\x00a\x00f\x00t\x00e\x00r\x00|i\x00n\x00c\x00l\x00u\x00d\x00e\x00|i\x00m\x00a\x00c\x00r\x00o\x00s\x00|o\x00|M\x00F\x00)))${drive_letter}\x00:\x00(?:$|[^A-Za-z0-9_]\x00)"

  if LC_ALL=C grep -a -i -E -q -- "$ascii_pattern" "$file"; then
    return 0
  else
    scan_status=$?
  fi
  if [[ $scan_status -ne 1 ]]; then
    echo "Unable to scan native recipe alias residue in $file" >&2
    return 2
  fi
  if LC_ALL=C grep -a -i -P -q -- "$utf16le_pattern" "$file"; then
    return 0
  else
    scan_status=$?
  fi
  if [[ $scan_status -ne 1 ]]; then
    echo "Unable to scan UTF-16LE native recipe alias residue in $file" >&2
    return 2
  fi
  return 1
}

_woarm64_archive_has_native_recipe_alias_residue() {
  local archive=$1
  local drive_letter=$2
  local member_list
  local member
  local extracted
  local scan_status
  local status=1

  if ! member_list=$(mktemp "${TMPDIR:-/tmp}/woarm64-archive-members.XXXXXX"); then
    return 2
  fi
  if ! tar --list --file="$archive" > "$member_list"; then
    if ! rm -f -- "$member_list"; then
      echo "Unable to remove failed native recipe archive member list: $member_list" >&2
    fi
    echo "Unable to list archive for native recipe alias residue: $archive" >&2
    return 2
  fi
  while IFS= read -r member || [[ -n "$member" ]]; do
    [[ "$member" == */ || -z "$member" ]] && continue
    if ! extracted=$(mktemp "${TMPDIR:-/tmp}/woarm64-archive-member.XXXXXX"); then
      status=2
      break
    fi
    if ! tar --extract --to-stdout --file="$archive" -- "$member" > "$extracted"; then
      if ! rm -f -- "$extracted"; then
        echo "Unable to remove failed native recipe archive extraction: $extracted" >&2
      fi
      echo "Unable to extract archive member for native recipe alias residue: $archive:$member" >&2
      status=2
      break
    fi
    if _woarm64_file_has_native_recipe_alias_residue "$extracted" "$drive_letter"; then
      if ! rm -f -- "$extracted"; then
        echo "Unable to remove native recipe archive extraction: $extracted" >&2
        status=2
      else
        status=0
      fi
      break
    else
      scan_status=$?
    fi
    if ! rm -f -- "$extracted"; then
      status=2
      break
    fi
    if [[ $scan_status -ne 1 ]]; then
      status=2
      break
    fi
  done < "$member_list"
  if ! rm -f -- "$member_list"; then
    status=2
  fi
  return "$status"
}

_woarm64_path_is_scannable_archive() {
  case "$1" in
    *.tar|*.tar.gz|*.tar.bz2|*.tar.xz|*.tar.zst|*.tar.lz4|*.pkg.tar.*)
      return 0
      ;;
  esac
  return 1
}

_woarm64_append_recipe_output_scan_root() {
  local candidate=$1
  local existing

  for existing in "${WOARM64_RECIPE_OUTPUT_SCAN_ROOTS[@]}"; do
    if [[ "$candidate" -ef "$existing" ]]; then
      return 0
    fi
  done
  WOARM64_RECIPE_OUTPUT_SCAN_ROOTS+=("$candidate")
}

load_native_makepkg_output_destinations() {
  local makepkg_config=$1
  local destination_values
  local value
  local cleanup_status=0

  if [[ $# -ne 1 || -z "$makepkg_config" || ! -f "$makepkg_config" ]]; then
    echo "load_native_makepkg_output_destinations requires one readable makepkg configuration" >&2
    return 2
  fi
  if [[ -z "${MSYSTEM:-}" ]]; then
    echo "MSYSTEM is required to resolve native makepkg output destinations" >&2
    return 2
  fi
  if ! destination_values=$(mktemp "${TMPDIR:-/tmp}/woarm64-makepkg-destinations.XXXXXX"); then
    return 2
  fi
  if ! bash -c '
      set -e
      config=$1
      shift
      source "$config"
      for destination_name in "$@"; do
        printf "%s\0" "${!destination_name:-}" >&3
      done
    ' native-makepkg-output-destinations "$makepkg_config" \
      "${WOARM64_RECIPE_OUTPUT_DESTINATION_NAMES[@]}" \
      3> "$destination_values" >/dev/null; then
    if ! rm -f -- "$destination_values"; then
      cleanup_status=1
    fi
    echo "Unable to load native makepkg output destinations: $makepkg_config" >&2
    return "$(( cleanup_status == 0 ? 2 : cleanup_status ))"
  fi
  WOARM64_RECIPE_EFFECTIVE_OUTPUT_DESTINATIONS=()
  while IFS= read -r -d '' value; do
    WOARM64_RECIPE_EFFECTIVE_OUTPUT_DESTINATIONS+=("$value")
  done < "$destination_values"
  if ! rm -f -- "$destination_values"; then
    echo "Unable to remove native makepkg destination capture: $destination_values" >&2
    return 2
  fi
  if [[ ${#WOARM64_RECIPE_EFFECTIVE_OUTPUT_DESTINATIONS[@]} -ne \
      ${#WOARM64_RECIPE_OUTPUT_DESTINATION_NAMES[@]} ]]; then
    echo "Native makepkg destination capture is incomplete: $makepkg_config" >&2
    return 2
  fi
}

# Resolves only output locations explicitly selected for this makepkg run. The
# recipe root is scanned recursively because it contains build, stage and
# metadata trees. External destinations are constrained to a real non-root
# directory that the user explicitly named; they are scanned only as artifact
# destinations, never by walking a broad host parent.
resolve_native_recipe_output_scan_roots() {
  local recipe_root=$1
  shift
  local canonical_recipe_root
  local configured
  local configured_name
  local configured_index
  local candidate
  local canonical_candidate

  WOARM64_RECIPE_OUTPUT_SCAN_ROOTS=()
  if [[ -z "$recipe_root" || ! -d "$recipe_root" ]]; then
    echo "resolve_native_recipe_output_scan_roots requires one existing recipe root" >&2
    return 2
  fi
  if [[ $# -ne 0 && $# -ne ${#WOARM64_RECIPE_OUTPUT_DESTINATION_NAMES[@]} ]]; then
    echo "resolve_native_recipe_output_scan_roots requires either no destinations or every configured destination" >&2
    return 2
  fi
  if ! canonical_recipe_root=$(cd "$recipe_root" && pwd -P); then
    echo "Unable to canonicalize native recipe output root: $recipe_root" >&2
    return 2
  fi
  _woarm64_append_recipe_output_scan_root "$canonical_recipe_root"

  for configured_index in "${!WOARM64_RECIPE_OUTPUT_DESTINATION_NAMES[@]}"; do
    configured_name=${WOARM64_RECIPE_OUTPUT_DESTINATION_NAMES[$configured_index]}
    if [[ $# -eq 0 ]]; then
      configured=${!configured_name:-}
    else
      configured=${1:-}
      shift
    fi
    [[ -n "$configured" ]] || continue
    case "$configured" in
      /*|[A-Za-z]:[\\/]*|\\\\*)
        candidate=$configured
        ;;
      *)
        candidate="$canonical_recipe_root/$configured"
        ;;
    esac
    if ! candidate=$(to_msys_path "$candidate"); then
      echo "Unable to resolve $configured_name for native recipe residue scanning" >&2
      return 2
    fi
    # A destination that was never created cannot contain an artifact. Existing
    # non-directories, however, make the scan incomplete and fail closed.
    [[ -e "$candidate" ]] || continue
    if [[ ! -d "$candidate" ]]; then
      echo "Configured native recipe artifact destination is not a directory: $configured_name=$candidate" >&2
      return 2
    fi
    if ! canonical_candidate=$(cd "$candidate" && pwd -P); then
      echo "Unable to canonicalize $configured_name for native recipe residue scanning: $candidate" >&2
      return 2
    fi
    case "$canonical_candidate" in
      /|/[A-Za-z])
        echo "Refusing to broadly scan host root configured by $configured_name: $canonical_candidate" >&2
        return 2
        ;;
    esac
    if [[ "$(dirname "$canonical_candidate")" == / ]]; then
      echo "Refusing to broadly scan host top-level directory configured by $configured_name: $canonical_candidate" >&2
      return 2
    fi
    _woarm64_append_recipe_output_scan_root "$canonical_candidate"
  done
}

# Fails the build when the temporary alias drive leaked into build trees,
# staged files, package metadata, or the contents of produced package
# archives. The drive letter is whichever candidate was free, so every form
# of that path is dangling and non-reproducible.
assert_no_native_recipe_alias_residue() {
  local drive_letter=$1
  shift
  local root
  local file_list
  local file
  local scan_status
  local -a matches=()

  if [[ ! "$drive_letter" =~ ^[A-Za-z]$ || $# -eq 0 ]]; then
    echo "assert_no_native_recipe_alias_residue requires a drive letter and at least one root" >&2
    return 2
  fi
  drive_letter=${drive_letter^^}

  for root in "$@"; do
    [[ -e "$root" ]] || continue
    if [[ -f "$root" ]]; then
      file_list=$(mktemp "${TMPDIR:-/tmp}/woarm64-residue-files.XXXXXX") || return 2
      printf '%s\0' "$root" > "$file_list" || {
        rm -f -- "$file_list" || true
        return 2
      }
    elif [[ -d "$root" ]]; then
      file_list=$(mktemp "${TMPDIR:-/tmp}/woarm64-residue-files.XXXXXX") || return 2
      if ! find "$root" -type f -print0 > "$file_list"; then
        rm -f -- "$file_list" || true
        echo "Unable to enumerate native recipe output for residue scanning: $root" >&2
        return 2
      fi
    else
      echo "Unsupported native recipe residue scan root: $root" >&2
      return 2
    fi

    while IFS= read -r -d '' file; do
      if _woarm64_file_has_native_recipe_alias_residue "$file" "$drive_letter"; then
        matches+=("$file")
        continue
      else
        scan_status=$?
      fi
      if [[ $scan_status -ne 1 ]]; then
        rm -f -- "$file_list" || true
        return "$scan_status"
      fi
      if _woarm64_path_is_scannable_archive "$file"; then
        if _woarm64_archive_has_native_recipe_alias_residue "$file" "$drive_letter"; then
          matches+=("$file (archive contents)")
          continue
        else
          scan_status=$?
        fi
        if [[ $scan_status -ne 1 ]]; then
          rm -f -- "$file_list" || true
          return "$scan_status"
        fi
      fi
    done < "$file_list"
    if ! rm -f -- "$file_list"; then
      return 2
    fi
  done

  if [[ ${#matches[@]} -gt 0 ]]; then
    echo "Native recipe alias ${drive_letter}: leaked into build or package output:" >&2
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
  local monitor_was_enabled=0

  if [[ $# -eq 0 ]]; then
    echo "with_short_native_recipe_root requires a command" >&2
    return 2
  fi
  if [[ "$_WOARM64_ALIAS_ACTIVE" == "1" ]]; then
    echo "with_short_native_recipe_root is already active in this shell" >&2
    return 2
  fi

  WOARM64_LAST_RECIPE_ALIAS_LETTER=
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
  if ! _woarm64_capture_traps "$trap_state_file" || ! rm -f "$trap_state_file"; then
    rm -f -- "$trap_state_file" || true
    return 2
  fi

  _WOARM64_ALIAS_ACTIVE=1
  _WOARM64_ALIAS_SUBST_TOOL="$subst_tool"
  _WOARM64_ALIAS_RECIPE_ROOT="$recipe_root"
  _WOARM64_ALIAS_RECIPE_ROOT_NATIVE="$recipe_root_native"
  _WOARM64_ALIAS_CALLER_ROOT="$recipe_root"

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
    _woarm64_recipe_abort 1
    return $?
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
  # MSYS Bash can inherit SIGINT as ignored from a non-interactive launcher.
  # Run the managed command through a tiny relay with its HUP/INT/TERM
  # dispositions explicitly reset. It is the signal endpoint exposed to the
  # command, forwards to the real child with a bounded wait, and returns the
  # conventional signal status to this helper.
  if ! env --default-signal=HUP,INT,TERM true 2>/dev/null; then
    echo "env with --default-signal is required for native recipe signal handling" >&2
    abort_status=1
    _woarm64_recipe_abort "$abort_status"
    return $?
  fi
  if [[ "$-" == *m* ]]; then
    monitor_was_enabled=1
  elif ! set -m; then
    echo "Bash job control is required for native recipe signal handling" >&2
    abort_status=1
    _woarm64_recipe_abort "$abort_status"
    return $?
  fi
  env --default-signal=HUP,INT,TERM bash -c '
    child_pid=
    child_starting=0
    pending_signal=
    relay_pid=$BASHPID
    set -m

    wait_for_child() {
      local pid=$1
      local timeout=${WOARM64_ALIAS_SIGNAL_WAIT_SECONDS:-10}
      local deadline
      [[ "$timeout" =~ ^[1-9][0-9]*$ ]] || exit 2
      deadline=$((SECONDS + timeout))
      while kill -0 -- "-$pid" 2>/dev/null; do
        if (( SECONDS >= deadline )); then
          kill -KILL -- "-$pid" 2>/dev/null || true
          break
        fi
        sleep 1
      done
      wait "$pid" 2>/dev/null || true
    }

    forward_signal() {
      local signal=$1
      local status=$2
      trap - HUP INT TERM
      if [[ -n "$child_pid" ]]; then
        kill -s "$signal" -- "-$child_pid" 2>/dev/null || true
        wait_for_child "$child_pid"
      fi
      exit "$status"
    }

    receive_signal() {
      local signal=$1
      local status=$2
      if [[ $child_starting -eq 1 && -z "$child_pid" ]]; then
        pending_signal="$signal $status"
        return
      fi
      forward_signal "$signal" "$status"
    }

    trap "receive_signal HUP 129" HUP
    trap "receive_signal INT 130" INT
    trap "receive_signal TERM 143" TERM
    child_starting=1
    MSYS2_WOARM64_RECIPE_HELPER_PID=$relay_pid \
      env --default-signal=HUP,INT,TERM "$@" <&0 &
    child_pid=$!
    child_starting=0
    if [[ -n "$pending_signal" ]]; then
      read -r signal status <<< "$pending_signal"
      forward_signal "$signal" "$status"
    fi
    if wait "$child_pid"; then
      child_status=0
    else
      child_status=$?
    fi
    exit "$child_status"
  ' native-recipe-signal-relay "$@" <&0 &
  _WOARM64_ALIAS_COMMAND_PID=$!
  if [[ $monitor_was_enabled -eq 0 ]]; then
    set +m
  fi
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
