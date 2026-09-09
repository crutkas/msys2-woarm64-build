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
host=$(to_posix_path "$3")
native_prefix=$(to_posix_path "$4")
output=$(to_posix_path "$5")
runtime_sha256=$6
shift 6

sha256="$host/usr/bin/sha256sum.exe"
native_shell="$native_prefix/usr/bin/bash.exe"
[[ $("$sha256" "$native_shell") == \
    0937e8a6c5811b044efeb9cd1f1074bda10a913ebab345bd4a6827305f891a0c* ]]
[[ $("$sha256" "${native_shell%/*}/msys-2.0.dll") == "$runtime_sha256 "* ]]
[[ $BASH_VERSION == 5.3.15* ]]

source_root="$root/source/coreutils-8.32"
build_root="$root/build/coreutils"
[[ -f "$source_root/tests/init.sh" ]]
[[ -f "$build_root/lib/config.h" ]]
[[ ! -e $output ]]
mkdir -p "$output"

programs=
for executable in "$root"/stage/coreutils/usr/bin/*.exe; do
    name=${executable##*/}
    name=${name%.exe}
    case "$name" in
        bash | sh | environment-handoff)
            continue
            ;;
        install)
            name=ginstall
            ;;
        gkill)
            name=kill
            ;;
    esac
    programs="$programs $name"
done

export PATH="$native_prefix/usr/bin:$sdk/usr/bin:$host/usr/bin"
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export LC_ALL=C MSYSTEM=CYGWIN MSYS=winsymlinks:sys
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export WOARM64_NATIVE_ARG_CONVERSION=none
export MSYS2_ENV_CONV_EXCL=COREUTILS_TEST_PROGRAM_DIR
export SHELL="$native_shell" CONFIG_SHELL="$native_shell"
export COREUTILS_TEST_PROGRAM_DIR=/usr/bin
export srcdir="$source_root" top_srcdir="$source_root"
export abs_srcdir="$source_root" abs_top_srcdir="$source_root"
export abs_top_builddir="$build_root"
export CONFIG_HEADER="$build_root/lib/config.h"
export VERSION=8.32 PACKAGE_VERSION=8.32
export host_os=cygwin host_triplet=aarch64-pc-cygwin EXEEXT=.exe
export built_programs="[ $programs "
export AWK="$host/usr/bin/gawk.exe"
export EGREP="$host/usr/bin/grep.exe -E"
export PERL="$host/usr/bin/perl.exe"
unset COREUTILS_TEST_BOOTSTRAP_DD MSYS2_ARG_CONV_EXCL

status_file="$output/results.tsv"
printf 'test\traw_exit\n' > "$status_file"
failed=0
cd "$build_root"
for test_name in "$@"; do
    test_path="$source_root/$test_name"
    [[ -f $test_path ]]
    log_name=${test_name//\//-}
    deadline=180
    case "$test_name" in
        tests/tail-2/*)
            deadline=90
            ;;
    esac
    shell_args=(--noprofile --norc)
    if [[ ${COREUTILS_TEST_TRACE:-0} == 1 ]]; then
        shell_args+=(-x)
    fi
    set +e
    timeout --foreground --signal=TERM --kill-after=10 "$deadline" \
        "$native_shell" --noprofile --norc -c \
        'cd "$1" && shift && exec "$@"' native-test "$build_root" \
        "$native_shell" "${shell_args[@]}" "$test_path" \
        > "$output/$log_name.log" 2>&1
    raw_exit=$?
    set -e
    printf '%s\t%s\n' "$test_name" "$raw_exit" >> "$status_file"
    if ((raw_exit != 0)); then
        failed=1
    fi
done

exit "$failed"
