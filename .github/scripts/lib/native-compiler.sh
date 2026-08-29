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

declare -a converted
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
    @?*)
      if [[ "${argument#@}" == "-" ]]; then
        converted+=("$argument")
      else
        converted+=("@$(to_native_path "${argument#@}")")
      fi
      ;;
    -*)
      converted+=("$argument")
      ;;
    *)
      if [[ -e "$argument" ]]; then
        converted+=("$(to_native_path "$argument")")
      else
        converted+=("$argument")
      fi
      ;;
  esac
done

native_temp=$(to_native_path "${TMPDIR:-/tmp}")
export TMP="$native_temp" TEMP="$native_temp" TMPDIR="$native_temp"
export PATH="/mingwarm64/bin:$PATH"
exec "$compiler" "${converted[@]}"
