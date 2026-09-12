#!/usr/bin/env bash
set -euo pipefail
[[ $# -gt 0 ]] || { echo "An explicit upstream test command is required" >&2; exit 2; }
if [[ ${1,,} == *.exe ]]; then
    : "${WOARM64_NATIVE_DRIVER_ROOT:?Need the qualified native target driver}"
    driver=$(cygpath -u "$WOARM64_NATIVE_DRIVER_ROOT")
    exec /usr/bin/bash "$driver/native-target-exec.sh" "$@"
fi
exec "$@"
