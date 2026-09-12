#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$root/.github/scripts/makepkg-compression-policy.sh"

unset WOARM64_JOBS
cmd=(custom-compressor --threads=0 -9 -)
before=$(declare -p cmd)
bound_woarm64_compression_command .pkg.tar.zst cmd
[[ $(declare -p cmd) == "$before" ]]
for jobs in '' 0 17 -1 1.5 01 invalid; do
    if WOARM64_JOBS=$jobs validate_woarm64_compression_policy 2>/dev/null; then
        printf 'Invalid job allocation accepted: %s\n' "$jobs" >&2
        exit 1
    fi
done
export WOARM64_JOBS=2
for format in xz zst; do
    program=xz
    flag=--threads=1
    if [[ $format == zst ]]; then program=zstd; flag=--single-thread; fi
    for threads in '-T0' '--threads=99'; do
        cmd=("$program" -c -9 "$threads" -)
        bound_woarm64_compression_command ".pkg.tar.$format" cmd
        [[ ${cmd[*]} == "$program $flag -c -9 -" ]]
        before=$(declare -p cmd)
        bound_woarm64_compression_command ".pkg.tar.$format" cmd
        [[ $(declare -p cmd) == "$before" ]]
    done
    cmd=("/path with spaces/$program.exe" -T 0 --threads 999 -c -7 -- -T0)
    bound_woarm64_compression_command ".src.tar.$format" cmd
    [[ ${cmd[*]} == "/path with spaces/$program.exe $flag -c -7 -- -T0" ]]
done
for option in -qT0 --threads=oops -T; do
    cmd=(xz "$option")
    if bound_woarm64_compression_command .pkg.tar.xz cmd 2>/dev/null; then
        printf 'Unbounded or invalid compressor option accepted: %s\n' "$option" >&2
        exit 1
    fi
done
cmd=(env zstd -T0)
if bound_woarm64_compression_command .pkg.tar.zst cmd 2>/dev/null; then
    printf 'Opaque compression wrapper accepted.\n' >&2
    exit 1
fi
cmd=(gzip -c -f -n)
before=$(declare -p cmd)
bound_woarm64_compression_command .pkg.tar.gz cmd
[[ $(declare -p cmd) == "$before" ]]
printf 'PASS: bounded XZ/Zstd policy preserves levels, operands and legacy defaults; invalid limits fail closed\n'
