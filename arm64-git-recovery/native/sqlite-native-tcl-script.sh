#!/usr/bin/env bash
set -euo pipefail
: "${TCLSH:?Explicit native MSYS Tcl required}"
: "${WOARM64_NATIVE_DRIVER_ROOT:?Qualified native relay required}"
# Only the first argument is the interpreter's script filename. Do not
# reinterpret application arguments, SQL, options, or test data.
if [[ $# -gt 0 && $1 =~ ^[A-Za-z]:[/\\] ]]; then
    script=$(cygpath -u "$1")
    shift
    set -- "$script" "$@"
fi
args=("$@")
if [[ $# -gt 0 ]]; then
    case "${1##*/}" in
        mksqlite3h.tcl|mksqlite3internalh.tcl)
            # These generators' first positional argument is their source directory.
            if [[ $# -gt 1 && ${args[1]} =~ ^[A-Za-z]:[/\\] ]]; then
                args[1]=$(cygpath -u "${args[1]}")
            fi
            ;;
        mkcombo.tcl)
            # mkcombo accepts input filenames and an optional -o output filename.
            for ((i=1; i<${#args[@]}; i++)); do
                if [[ ${args[i]} =~ ^[A-Za-z]:[/\\] ]]; then
                    args[i]=$(cygpath -u "${args[i]}")
                fi
            done
            ;;
    esac
fi
python=$(cygpath -u "$WOARM64_NATIVE_PYTHON")
relay="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sqlite_tcl_relay.py"
export MSYS2_ARG_CONV_EXCL='*'
exec "$python" -B "$(cygpath -m "$relay")" "$TCLSH" "${args[@]}"
