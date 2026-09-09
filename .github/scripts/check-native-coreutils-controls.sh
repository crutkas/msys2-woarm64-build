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

[[ $# == 5 ]] || exit 2
root=$(to_posix_path "$1")
sdk=$(to_posix_path "$2")
host=$(to_posix_path "$3")
launch_contract=$(to_posix_path "$4")
native_prefix=$(to_posix_path "$5")
sha256="$host/usr/bin/sha256sum.exe"
native_shell="$native_prefix/usr/bin/bash.exe"

[[ $("$sha256" "$launch_contract") == \
    e3ab7e8f901601e327eb74f52bbd9117d40746a977bfa381d319e080bf91132f* ]]
[[ $("$sha256" "$native_shell") == \
    0937e8a6c5811b044efeb9cd1f1074bda10a913ebab345bd4a6827305f891a0c* ]]
[[ $("$sha256" "${native_shell%/*}/msys-2.0.dll") == \
    baa144d1848ea17e8dee944279f4dc707f45581bc5a5e912b451a87cbe7abd15* ]]
[[ $BASH_VERSION == 5.3.15* ]]

export PATH="$native_prefix/usr/bin:$root/build/coreutils/src:$root/stage/runtime/usr/bin:$root/stage/gmp/usr/bin:$sdk/usr/bin:$host/usr/bin"
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export LC_ALL=C MSYSTEM=CYGWIN OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export WOARM64_NATIVE_ARG_CONVERSION=none
export SHELL="$native_shell" CONFIG_SHELL="$native_shell"
unset COREUTILS_TEST_BOOTSTRAP_DD MSYS2_ARG_CONV_EXCL

work="$root/controls-work-01"
[[ ! -e $work ]]
mkdir -p "$work"
cd "$work"

dd if=/dev/urandom of=random-1.bin ibs=1 count=1 status=none
dd if=/dev/urandom of=random-4.bin ibs=4 count=1 status=none
dd if=/dev/urandom of=random-4096.bin bs=4096 count=1 \
    iflag=fullblock,nonblock status=none
[[ $(wc -c < random-1.bin) == 1 ]]
[[ $(wc -c < random-4.bin) == 4 ]]
[[ $(wc -c < random-4096.bin) == 4096 ]]

sh -c 'dd if=/dev/urandom of=nested-random.bin bs=131072 count=1 iflag=fullblock,nonblock status=none'
[[ $(wc -c < nested-random.bin) == 131072 ]]

mkdir -m 0700 mode-request
[[ -d mode-request ]]
temp_dir=$(mktemp -d "$work/temp.XXXXXX")
[[ -d $temp_dir ]]

[[ $(printf 'A' | od -An -t x1 | tr -d ' \n') == 41 ]]
[[ $(env COREUTILS_NATIVE_PARENT=qualified sh -c 'printf %s "$COREUTILS_NATIVE_PARENT"') == qualified ]]

"$sha256" random-1.bin random-4.bin random-4096.bin nested-random.bin
