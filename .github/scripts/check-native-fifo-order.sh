#!/usr/bin/env bash
set -euo pipefail

[[ $# == 1 ]] || exit 2
root=$1
rm -rf "$root"
mkdir -p "$root"
fifo="$root/fifo"
status="$root/writer.status"

mkfifo "$fifo"
(
    set +e
    printf 'FIFO_PAYLOAD=payload\n' >"$fifo"
    printf '%s\n' "$?" >"$status"
) &
writer=$!
sleep 2

if ! kill -0 "$writer" 2>/dev/null; then
    wait "$writer" || :
    echo "FIFO writer exited before a reader opened" >&2
    [[ -f $status ]] && cat "$status" >&2
    exit 1
fi

. "$fifo"
wait "$writer"
[[ ${FIFO_PAYLOAD:-} == payload ]]
[[ $(cat "$status") == 0 ]]
