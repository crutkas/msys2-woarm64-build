#!/bin/bash

set -e

source "$(dirname "${BASH_SOURCE[0]}")/path-boundary.sh"

compiler_name=${WOARM64_NATIVE_COMPILER_NAME:-${0##*/}}
case "$compiler_name" in
  woarm64-gcc)
    compiler=/mingwarm64/bin/gcc.exe
    ;;
  woarm64-g++)
    compiler=/mingwarm64/bin/g++.exe
    ;;
  *)
    echo "Unsupported native compiler launcher name: $compiler_name" >&2
    exit 2
    ;;
esac
compiler=${WOARM64_NATIVE_COMPILER:-$compiler}

# Options whose value is a filesystem path, per payload dialect. Anything not
# listed here is passed through untouched, so linker flags, symbol names and
# numeric values can never be mangled into paths.
woarm64_linker_path_options=(
  -o --out-implib --output-def -Map --Map -T --script --version-script
  --dynamic-list --retain-symbols-file --just-symbols -rpath -rpath-link
  -L --library-path --sysroot
)
woarm64_preprocessor_path_options=(
  -MF -MD -MMD -I -isystem -include -imacros -idirafter -iquote -o --sysroot
)
woarm64_assembler_path_options=(-I -o --MD)

# Joined single-token forms that are real in the payload dialects above.
woarm64_joined_path_options=(-MF -I -L -T)

declare -a converted=()
declare -a response_temporaries=()

woarm64_cleanup() {
  if [[ ${#response_temporaries[@]} -gt 0 ]]; then
    rm -f -- "${response_temporaries[@]}"
  fi
}

# A rewritten response file must not outlive this process on any path, and a
# signal must not be reported as a clean exit.
woarm64_on_signal() {
  local status=$1

  trap - EXIT HUP INT TERM
  woarm64_cleanup
  exit "$status"
}
trap woarm64_cleanup EXIT
trap 'woarm64_on_signal 129' HUP
trap 'woarm64_on_signal 130' INT
trap 'woarm64_on_signal 143' TERM

woarm64_is_listed() {
  local needle=$1
  shift

  local candidate
  for candidate in "$@"; do
    if [[ "$candidate" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

# A value that is known to be a path is converted unconditionally, matching how
# the top-level -o and -I forms already behave. "-" keeps its stdio meaning.
woarm64_convert_required_path() {
  local value=$1

  if [[ -z "$value" || "$value" == "-" ]]; then
    printf '%s' "$value"
    return 0
  fi
  printf '%s' "$(to_native_path "$value")"
}

# A bare operand is converted only when it actually looks like a path. This is
# what keeps -Wl,--exclude-libs,ALL and -Wl,--wrap,malloc intact.
woarm64_convert_optional_path() {
  local value=$1

  if [[ -z "$value" ]]; then
    printf '%s' "$value"
    return 0
  fi
  case "$value" in
    */*|*\\*) ;;
    *)
      printf '%s' "$value"
      return 0
      ;;
  esac
  if [[ "$value" == /* || -e "$value" ]]; then
    printf '%s' "$(to_native_path "$value")"
    return 0
  fi
  printf '%s' "$value"
}

# Converts one field of a comma payload, or one -Xlinker operand. The result is
# published in a global instead of on stdout: a command substitution would run
# this in a subshell and lose the "next field is a path" state, silently
# dropping the conversion of -Wl,--out-implib,<path>.
_woarm64_expect_path=0
_woarm64_field=
woarm64_convert_field() {
  local field=$1
  shift
  local -a options=("$@")
  local name
  local value

  if [[ $_woarm64_expect_path -eq 1 ]]; then
    _woarm64_expect_path=0
    _woarm64_field=$(woarm64_convert_required_path "$field")
    return 0
  fi
  if woarm64_is_listed "$field" "${options[@]}"; then
    _woarm64_expect_path=1
    _woarm64_field=$field
    return 0
  fi
  if [[ "$field" == -?*=* ]]; then
    name=${field%%=*}
    value=${field#*=}
    if woarm64_is_listed "$name" "${options[@]}"; then
      _woarm64_field="$name=$(woarm64_convert_required_path "$value")"
      return 0
    fi
    _woarm64_field=$field
    return 0
  fi
  for name in "${woarm64_joined_path_options[@]}"; do
    if [[ "$field" == "$name"?* ]] && woarm64_is_listed "$name" "${options[@]}"; then
      _woarm64_field="$name$(woarm64_convert_required_path "${field#"$name"}")"
      return 0
    fi
  done
  if [[ "$field" == -* ]]; then
    _woarm64_field=$field
    return 0
  fi
  _woarm64_field=$(woarm64_convert_optional_path "$field")
}

_woarm64_payload=
woarm64_convert_payload() {
  local prefix=$1
  local payload=$2
  shift 2
  local -a options=("$@")
  local -a fields=()
  local -a result=()
  local field
  local saved=$_woarm64_expect_path

  IFS=',' read -r -a fields <<< "$payload"
  _woarm64_expect_path=0
  for field in "${fields[@]}"; do
    woarm64_convert_field "$field" "${options[@]}"
    result+=("$_woarm64_field")
  done
  _woarm64_expect_path=$saved
  _woarm64_payload="$prefix$(IFS=','; printf '%s' "${result[*]}")"
}

# Rewrites the *contents* of a response file into a temporary copy. The caller's
# file is only ever read. Files using quoting this rewriter cannot round-trip
# exactly, and files that nest a further @response, are passed through untouched
# rather than corrupted or silently flattened.
_woarm64_response=
woarm64_convert_response_file() {
  local original=$1
  local converted_file
  local line
  local rest
  local token
  local -a tokens=()

  _woarm64_response=$(to_native_path "$original")
  if [[ ! -f "$original" ]]; then
    return 0
  fi
  if grep -q -F -e "'" -e '\' -- "$original"; then
    echo "::warning::Response file uses quoting this boundary cannot rewrite; passing it through: $original" >&2
    return 0
  fi
  if grep -q -E '(^|[[:space:]])@' -- "$original"; then
    echo "::warning::Response file nests a further response file; passing it through: $original" >&2
    return 0
  fi
  if ! converted_file=$(mktemp "${TMPDIR:-/tmp}/woarm64-response.XXXXXX"); then
    return 0
  fi
  response_temporaries+=("$converted_file")

  : > "$converted_file"
  # The "next token is a path" state has to survive both token and line
  # boundaries, because --out-implib and its value are often on separate lines.
  _woarm64_expect_path=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    # A response file written by a native tool can use CRLF. A trailing carriage
    # return would otherwise become part of the last token on the line.
    line=${line%$'\r'}
    tokens=()
    rest=$line
    while [[ -n "$rest" ]]; do
      case "$rest" in
        [$' \t']*)
          rest=${rest#?}
          continue
          ;;
        '"'*)
          rest=${rest#\"}
          token=${rest%%\"*}
          if [[ "$token" == "$rest" ]]; then
            rest=
          else
            rest=${rest#"$token"}
            rest=${rest#\"}
          fi
          ;;
        *)
          token=${rest%%[$' \t']*}
          rest=${rest#"$token"}
          ;;
      esac
      tokens+=("$token")
    done

    for token in "${tokens[@]}"; do
      woarm64_convert_field "$token" "${woarm64_linker_path_options[@]}"
      printf '"%s"\n' "${_woarm64_field//\"/\\\"}" >> "$converted_file"
    done
  done < "$original"
  _woarm64_expect_path=0

  _woarm64_response=$(to_native_path "$converted_file")
}

while [[ $# -gt 0 ]]; do
  argument=$1
  shift

  case "$argument" in
    -I|-L|-B|-iquote|-isystem|-idirafter|-include|-imacros|-o|-MF|--sysroot)
      if [[ $# -eq 0 ]]; then
        echo "Compiler option $argument requires a path" >&2
        exit 2
      fi
      if [[ "$1" == "-" ]]; then
        converted+=("$argument" "$1")
      else
        converted+=("$argument" "$(to_native_path "$1")")
      fi
      shift
      ;;
    -I-)
      converted+=("$argument")
      ;;
    -I?*|-L?*|-B?*)
      converted+=("${argument:0:2}$(to_native_path "${argument:2}")")
      ;;
    -include?*)
      converted+=("-include$(to_native_path "${argument#-include}")")
      ;;
    -isystem?*)
      converted+=("-isystem$(to_native_path "${argument#-isystem}")")
      ;;
    -idirafter?*)
      converted+=("-idirafter$(to_native_path "${argument#-idirafter}")")
      ;;
    -imacros?*)
      converted+=("-imacros$(to_native_path "${argument#-imacros}")")
      ;;
    -MF?*)
      converted+=("-MF$(to_native_path "${argument#-MF}")")
      ;;
    -o?*)
      converted+=("-o$(to_native_path "${argument#-o}")")
      ;;
    --sysroot=?*)
      converted+=("--sysroot=$(to_native_path "${argument#--sysroot=}")")
      ;;
    -specs=?*)
      converted+=("-specs=$(to_native_path "${argument#-specs=}")")
      ;;
    -Wl,*)
      woarm64_convert_payload '-Wl,' "${argument#-Wl,}" \
        "${woarm64_linker_path_options[@]}"
      converted+=("$_woarm64_payload")
      ;;
    -Wp,*)
      woarm64_convert_payload '-Wp,' "${argument#-Wp,}" \
        "${woarm64_preprocessor_path_options[@]}"
      converted+=("$_woarm64_payload")
      ;;
    -Wa,*)
      woarm64_convert_payload '-Wa,' "${argument#-Wa,}" \
        "${woarm64_assembler_path_options[@]}"
      converted+=("$_woarm64_payload")
      ;;
    -Xlinker)
      if [[ $# -eq 0 ]]; then
        echo "Compiler option $argument requires a value" >&2
        exit 2
      fi
      woarm64_convert_field "$1" "${woarm64_linker_path_options[@]}"
      converted+=("$argument" "$_woarm64_field")
      shift
      ;;
    @?*)
      if [[ "${argument#@}" == "-" ]]; then
        converted+=("$argument")
      else
        woarm64_convert_response_file "${argument#@}"
        converted+=("@$_woarm64_response")
      fi
      ;;
    -*)
      converted+=("$argument")
      ;;
    *[\\/]*)
      if [[ -e "$argument" ]]; then
        converted+=("$(to_native_path "$argument")")
      else
        converted+=("$argument")
      fi
      ;;
    *)
      converted+=("$argument")
      ;;
  esac
done

native_temp=$(to_native_path "${TMPDIR:-/tmp}")
export TMP="$native_temp" TEMP="$native_temp" TMPDIR="$native_temp"
export PATH="/mingwarm64/bin:$PATH"

# exec would skip the cleanup of any rewritten response file, so only take that
# path when there is nothing to remove.
if [[ ${#response_temporaries[@]} -eq 0 ]]; then
  trap - EXIT HUP INT TERM
  exec "$compiler" "${converted[@]}"
fi

set +e
"$compiler" "${converted[@]}"
compiler_status=$?
set -e
# Cleanup runs from the EXIT trap. An explicit exit status is what the shell
# reports, so a failing rm can never turn a failed compile into a success.
exit "$compiler_status"
