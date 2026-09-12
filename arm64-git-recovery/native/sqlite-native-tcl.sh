#!/usr/bin/env bash
set -euo pipefail
: "${TCLSH:?Explicit native MSYS Tcl required}"
: "${WOARM64_NATIVE_DRIVER_ROOT:?Qualified native relay required}"
exec /usr/bin/bash "$(cygpath -u "$WOARM64_NATIVE_DRIVER_ROOT")/native-target-exec.sh" "$TCLSH" "$@"
