#!/bin/bash

if [[ -n "${MSYS2_WOARM64_PATH_BOUNDARY_SH:-}" ]]; then
  return 0
fi
readonly MSYS2_WOARM64_PATH_BOUNDARY_SH=1

to_msys_path() {
  if [[ $# -ne 1 || -z "$1" ]]; then
    echo "to_msys_path requires one non-empty path" >&2
    return 2
  fi

  /usr/bin/cygpath -au -- "$1"
}

to_native_path() {
  if [[ $# -ne 1 || -z "$1" ]]; then
    echo "to_native_path requires one non-empty path" >&2
    return 2
  fi

  /usr/bin/cygpath -am -- "$1"
}
