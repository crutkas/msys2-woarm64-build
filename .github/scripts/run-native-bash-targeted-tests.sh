#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/bin:$PATH

[[ $# -ge 6 ]] || exit 2
root=$(cygpath -u "$1")
output=$(cygpath -u "$2")
base_runtime=$(cygpath -u "$3")
sdk=$(cygpath -u "$4")
tc=$(cygpath -u "$5")
shift 5

[[ -f "$root/stage/usr/bin/bash.exe" ]]
[[ -f "$base_runtime/usr/bin/msys-2.0.dll" ]]
[[ ! -e "$output/runtime" && ! -e "$output/cases" ]]
mkdir -p "$output/cases"
cp -a "$base_runtime" "$output/runtime"
cp "$root/stage/usr/bin/bash.exe" "$output/runtime/usr/bin/bash.exe"
cp "$root/stage/usr/bin/sh.exe" "$output/runtime/usr/bin/sh.exe"
for helper in printenv recho xcase zecho; do
    [[ -f "$root/source/tests/$helper.exe" ]]
    cp "$root/source/tests/$helper.exe" "$output/runtime/usr/bin/$helper.exe"
done
mkdir -p "$output/runtime/etc"
if [[ ! -f "$output/runtime/etc/passwd" ]]; then
    printf 'root:x:0:0:root:/root:/usr/bin/bash\n' > "$output/runtime/etc/passwd"
fi

export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export LC_ALL=C.UTF-8 MSYSTEM=CYGWIN MSYS=winsymlinks:sys
export WOARM64_NATIVE_ARG_CONVERSION=none TERMINFO="$sdk/usr/share/terminfo"
export MSYS2_ENV_CONV_EXCL=NATIVE_BASH_TEST_HELPERS
export PATH="$output/runtime/usr/bin:$sdk/usr/bin:$tc/bin"
export NATIVE_BASH_TEST_HELPERS="$output/runtime/usr/bin"
export THIS_SH="$output/runtime/usr/bin/bash.exe"
export BUILD_DIR="$root/source"
unset BASH_ENV ENV
mkdir -p "$HOME" "$TMPDIR"

status=0
: > "$output/results.tsv"
for test_case in "$@"; do
    [[ $test_case == run-* && -f "$root/source/tests/$test_case" ]]
    export BASH_TSTOUT="$output/cases/$test_case.output"
    deadline=900
    [[ $test_case == run-builtins ]] && deadline=180
    timeout_args=(--signal=TERM --kill-after=10 "$deadline")
    [[ $test_case == run-jobs ]] && timeout_args=(--foreground "${timeout_args[@]}")
    case_status=0
    (
        cd "$root/source/tests"
        timeout "${timeout_args[@]}" \
            "$output/runtime/usr/bin/sh.exe" "$test_case"
    ) >"$output/cases/$test_case.log" 2>&1 || case_status=$?
    printf '%s\t%s\n' "$test_case" "$case_status" >> "$output/results.tsv"
    (( case_status == 0 )) || status=1
done
exit "$status"
