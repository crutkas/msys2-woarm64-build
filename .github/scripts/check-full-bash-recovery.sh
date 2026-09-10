#!/usr/bin/env bash
set -euo pipefail
[[ $# == 4 ]] || exit 2
root=$(cygpath -u "$1") output=$(cygpath -u "$2") sdk=$(cygpath -u "$3") host=$(cygpath -u "$4")
[[ $host == / ]] && host=
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tc=/c/ag-e138920f/tc-cpp-guard-01
[[ -n ${NATIVE_BASH_TEST_UTILITIES:-} && -n ${NATIVE_BASH_TEST_RUNTIME:-} ]]
utilities=$(cygpath -u "$NATIVE_BASH_TEST_UTILITIES")
runtime_dll=$(cygpath -u "$NATIVE_BASH_TEST_RUNTIME")
runtime_sha=${NATIVE_BASH_TEST_RUNTIME_SHA256:-}
[[ $runtime_sha =~ ^[0-9a-f]{64}$ ]]
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export LC_ALL=C.UTF-8 MSYSTEM=CYGWIN MSYS=winsymlinks:sys
export MAKEFLAGS=-j1 MFLAGS=-j1 OMP_NUM_THREADS=1
export WOARM64_NATIVE_ARG_CONVERSION=none TERMINFO="$sdk/usr/share/terminfo"
export MSYS2_ENV_CONV_EXCL=NATIVE_BASH_TEST_HELPERS
export BASH_TEST_EVIDENCE="$output/cases"
unset BASH_ENV ENV
mkdir -p "$HOME" "$TMPDIR" "$output/runtime/usr/bin" "$output/runtime/etc" \
    "$BASH_TEST_EVIDENCE"
actual_runtime=$("$host/usr/bin/sha256sum.exe" "$runtime_dll")
[[ ${actual_runtime%% *} == "$runtime_sha" ]]
"$host/usr/bin/cp.exe" "$runtime_dll" "$output/runtime/usr/bin/msys-2.0.dll"
printf 'none / cygdrive binary,posix=0,noacl,user 0 0\n' > "$output/runtime/etc/fstab"
for config in passwd group nsswitch.conf; do
    [[ -f "$host/etc/$config" ]] &&
        "$host/usr/bin/cp.exe" "$host/etc/$config" "$output/runtime/etc/"
done
if [[ ! -f "$output/runtime/etc/passwd" ]]; then
    printf 'root:x:0:0:root:/root:/usr/bin/bash\n' > "$output/runtime/etc/passwd"
fi
for dll in "$utilities"/usr/bin/msys-*.dll; do
    [[ -e $dll ]] || continue
    dll_windows=$("$host/usr/bin/cygpath.exe" -w "$dll")
    identity=$("$tc/bin/objdump.exe" -f "$dll_windows")
    [[ $identity == *"file format pei-aarch64-little"* ]]
    target="$output/runtime/usr/bin/${dll##*/}"
    if [[ -e $target ]]; then
        existing=$("$host/usr/bin/sha256sum.exe" "$target")
        incoming=$("$host/usr/bin/sha256sum.exe" "$dll")
        [[ ${existing%% *} == "${incoming%% *}" ]]
    else
        "$host/usr/bin/cp.exe" "$dll" "$target"
    fi
done
for source_tool in "$utilities"/usr/bin/*.exe; do
    case ${source_tool##*/} in
        bash.exe|sh.exe) continue ;;
    esac
    source_tool_windows=$("$host/usr/bin/cygpath.exe" -w "$source_tool")
    identity=$("$tc/bin/objdump.exe" -f "$source_tool_windows")
    [[ $identity == *"file format pei-aarch64-little"* ]]
    target="$output/runtime/usr/bin/${source_tool##*/}"
    if [[ -e $target ]]; then
        existing=$("$host/usr/bin/sha256sum.exe" "$target")
        incoming=$("$host/usr/bin/sha256sum.exe" "$source_tool")
        [[ ${existing%% *} == "${incoming%% *}" ]]
    else
        "$host/usr/bin/cp.exe" "$source_tool" "$target"
    fi
done
for helper in printenv recho xcase zecho; do
    source_helper="$root/source/tests/$helper.exe"
    source_helper_windows=$("$host/usr/bin/cygpath.exe" -w "$source_helper")
    identity=$("$tc/bin/objdump.exe" -f "$source_helper_windows")
    [[ $identity == *"file format pei-aarch64-little"* ]]
    "$host/usr/bin/cp.exe" "$source_helper" "$output/runtime/usr/bin/"
done
export PATH="$output/runtime/usr/bin:$sdk/usr/bin:$tc/bin"
export NATIVE_BASH_TEST_HELPERS="$output/runtime/usr/bin"
run_all="$root/source/tests/run-all"
run_all_sha=$("$host/usr/bin/sha256sum.exe" "$run_all")
case ${run_all_sha%% *} in
    0a1446a7dee1c5b75a0e8bb3902d626924e77dd1fcec46644a62b5c889a9a94b)
        "$host/usr/bin/patch.exe" --batch --forward --fuzz=0 --no-backup-if-mismatch \
            -p1 -d "$root/source" -i "$here/bash-5.3-record-all-tests.patch"
        ;;
    a05e9044d9314ed8c602e0f9044a8abd1a4fce9ef9763f2148c924084a548d63 | \
    c1ec9ce5e2a64ed9e63c6c541aa3271028a98783c51ad387c5e8009fbe942db1 | \
    e9790d75c88d24c7a14d4314cb4bab4381c75c4ffbdfa680fc299aef1a519c30 | \
    8f30aa853743adfc1718b2e551a6bf59b0305f2eb8de390ce71e37b42322549f | \
    5e22d073b9cb4c83246dea5d927f052daff1ebc03475a431ac2f85dc27692a0b | \
    e19e0050ca1ebe8bdb292b8b1c2505b516d15d8937f1f0f020164fe9ff7703fb)
        ;;
    *)
        echo "Bash run-all differs from sealed recording harness states" >&2
        exit 3
        ;;
esac
run_all_sha=$("$host/usr/bin/sha256sum.exe" "$run_all")
case ${run_all_sha%% *} in
    a05e9044d9314ed8c602e0f9044a8abd1a4fce9ef9763f2148c924084a548d63)
        "$host/usr/bin/patch.exe" --batch --forward --fuzz=0 --no-backup-if-mismatch \
            -p1 -d "$root/source" -i "$here/bash-5.3-native-test-helpers.patch"
        ;;
    c1ec9ce5e2a64ed9e63c6c541aa3271028a98783c51ad387c5e8009fbe942db1 | \
    e9790d75c88d24c7a14d4314cb4bab4381c75c4ffbdfa680fc299aef1a519c30 | \
    8f30aa853743adfc1718b2e551a6bf59b0305f2eb8de390ce71e37b42322549f | \
    5e22d073b9cb4c83246dea5d927f052daff1ebc03475a431ac2f85dc27692a0b | \
    e19e0050ca1ebe8bdb292b8b1c2505b516d15d8937f1f0f020164fe9ff7703fb)
        ;;
    *)
        echo "Bash run-all differs from sealed native-helper harness states" >&2
        exit 3
        ;;
esac
if ! grep -q 'BASH_TEST_CASE_TIMEOUT' "$run_all"; then
    "$host/usr/bin/patch.exe" --batch --forward --fuzz=0 --no-backup-if-mismatch \
        -p1 -d "$root/source" -i "$here/bash-5.3-bound-case-timeouts.patch"
fi
if grep -q 'timeout --foreground --signal=TERM' "$run_all"; then
    [[ $(grep -c 'timeout --foreground --signal=TERM' "$run_all") == 1 ]]
    sed -i 's/timeout --foreground --signal=TERM/timeout --signal=TERM/' "$run_all"
fi
if ! grep -q 'BASH_TEST_TIMEOUT_MODE' "$run_all"; then
    "$host/usr/bin/patch.exe" --batch --forward --fuzz=0 --no-backup-if-mismatch \
        -p1 -d "$root/source" -i "$here/bash-5.3-job-control-timeout.patch"
fi
grep -q 'BASH_TEST_CASE_TIMEOUT' "$run_all"
grep -q 'run-jobs) BASH_TEST_TIMEOUT_MODE=--foreground' "$run_all"
cd "$root/source/tests"
BUILD_DIR="$root/source" THIS_SH="$output/runtime/usr/bin/bash.exe" \
    "$output/runtime/usr/bin/sh.exe" run-all
