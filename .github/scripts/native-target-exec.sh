#!/bin/bash
set -euo pipefail

: "${WOARM64_NATIVE_PYTHON:?A verified native Python interpreter is required}"
: "${WOARM64_NATIVE_PYTHON_SHA256:?The interpreter identity must be bound}"
: "${WOARM64_NATIVE_TEST_ROOT:?An owned native target root is required}"
: "${WOARM64_NATIVE_EXIT_DIR:?An owned native exit-record directory is required}"
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python=$(cygpath -u "$WOARM64_NATIVE_PYTHON")
relay=$(cygpath -am "$scripts/native-target-exec.py")
(( $# )) || { printf 'A native executable is required.\n' >&2; exit 2; }
target=$1
shift
if [[ $target == */* || $target == *\\* || $target == *:* ]]; then
  if [[ ${target,,} != *.exe && -e $target.exe ]]; then
    target=$target.exe
  fi
fi
if [[ $target != */* && $target != *\\* && $target != *:* ]]; then
  if ! resolved=$(type -P -- "$target"); then
    printf 'Native executable not found on PATH: %s\n' "$target" >&2
    exit 127
  fi
  target=$resolved
fi
case "${WOARM64_NATIVE_ARG_CONVERSION:-none}" in
  mingw)
    unset MSYS2_ARG_CONV_EXCL
    exec "$python" -I "$relay" "$target" "$@"
    ;;
  none|paths)
    export MSYS2_ARG_CONV_EXCL='*' WOARM64_NATIVE_ARG_COUNT=$#
    if [[ $WOARM64_NATIVE_ARG_CONVERSION == paths ]]; then
      export WOARM64_NATIVE_PATH_CONVERSION=1
      WOARM64_NATIVE_MSYS_ROOT=$(cygpath -am /)
      export WOARM64_NATIVE_MSYS_ROOT
    else
      unset WOARM64_NATIVE_PATH_CONVERSION WOARM64_NATIVE_MSYS_ROOT
    fi
    index=0
    for argument in "$@"; do
      printf -v name 'WOARM64_NATIVE_ARG_%d' "$index"
      printf -v "$name" 'v1:%s' "$argument"
      export "$name"
      ((index += 1))
    done
    exec "$python" -I "$relay" "$target"
    ;;
  *)
    printf 'Unsupported native argument conversion mode: %s\n' "$WOARM64_NATIVE_ARG_CONVERSION" >&2
    exit 2
    ;;
esac
