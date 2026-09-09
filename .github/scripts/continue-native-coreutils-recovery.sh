#!/usr/bin/env bash
set -euo pipefail

to_posix_path()
{
    local path=${1//\\//}
    case "$path" in
        [A-Za-z]:/*)
            local drive=${path:0:1}
            printf '/proc/cygdrive/%s%s\n' "${drive,,}" "${path:2}"
            ;;
        *)
            printf '%s\n' "$path"
            ;;
    esac
}

[[ $# -ge 7 ]] || exit 2
root=$(to_posix_path "$1")
sdk=$(to_posix_path "$2")
jobs=$3
launch_contract=$(to_posix_path "$4")
host=$(to_posix_path "$5")
native_prefix=$(to_posix_path "$6")
shift 6
sha256="$host/usr/bin/sha256sum.exe"
[[ $jobs =~ ^[1-6]$ ]] || exit 2
[[ $("$sha256" "$launch_contract") == \
    e3ab7e8f901601e327eb74f52bbd9117d40746a977bfa381d319e080bf91132f* ]]
native_shell="$native_prefix/usr/bin/bash.exe"
[[ $("$sha256" "$native_shell") == \
    0937e8a6c5811b044efeb9cd1f1074bda10a913ebab345bd4a6827305f891a0c* ]]
[[ $("$sha256" "${native_shell%/*}/msys-2.0.dll") == \
    baa144d1848ea17e8dee944279f4dc707f45581bc5a5e912b451a87cbe7abd15* ]]
[[ $BASH_VERSION == 5.3.15* ]]
[[ -f "$root/build/coreutils/Makefile" ]]
[[ -x "$root/build/coreutils/src/dd.exe" ]]
[[ -f "$root/stage/runtime/usr/bin/msys-2.0.dll" ]]
[[ $("$sha256" "$root/stage/runtime/usr/bin/msys-2.0.dll") == \
    baa144d1848ea17e8dee944279f4dc707f45581bc5a5e912b451a87cbe7abd15* ]]

for test_name in "$@"; do
    case "$test_name" in
        tests/tail-2/*)
            [[ $jobs == 1 ]] || {
                printf 'tail/follow tests require jobs=1: %s\n' "$test_name" >&2
                exit 2
            }
            ;;
    esac
done

export PATH="$native_prefix/usr/bin:$root/build/coreutils/src:$root/stage/runtime/usr/bin:$root/stage/gmp/usr/bin:$sdk/usr/bin:$host/usr/bin"
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export LC_ALL=C MSYSTEM=CYGWIN OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export WOARM64_NATIVE_ARG_CONVERSION=none
export SHELL="$native_shell" CONFIG_SHELL="$native_shell"
export COREUTILS_TEST_PROGRAM_DIR="$native_prefix/usr/bin"
unset COREUTILS_TEST_BOOTSTRAP_DD MSYS2_ARG_CONV_EXCL

cd "$root/build/coreutils"
"$host/usr/bin/make.exe" SHELL="$native_shell" -j"$jobs" check TESTS="$*"
