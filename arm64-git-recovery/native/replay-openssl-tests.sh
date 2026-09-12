#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 5 ]] || { echo "usage: $0 WINDOWS_BUILD WINDOWS_TOOLCHAIN WINDOWS_OUTPUT JOBS TEST..." >&2; exit 2; }
export PATH=/usr/bin
build=$(cygpath -u "$1") toolchain=$(cygpath -u "$2") output=$(cygpath -u "$3") jobs=$4
shift 4
[[ $jobs =~ ^[1-8]$ && ! -e $output ]] || { echo "Need explicit allocation and new output" >&2; exit 2; }
mkdir -p "$output/results" "$output/home" "$output/temp"
export PATH="$toolchain/bin:$build:/usr/bin"
export OPENSSL_NATIVE_TEST_ROOT="$build"
unset EXE_SHELL
export OPENSSL_NATIVE_TEST_TRANSPORT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/openssl-test-transport.sh"
case "${OPENSSL_NATIVE_TEST_PROFILE:-mingw}" in
    mingw) export PERLIO=crlf ;;
    msys) export PERLIO=unix ;;
    *) echo "Unknown native test runtime profile" >&2; exit 2 ;;
esac
export HARNESS_JOBS="$jobs" HARNESS_TIMER=1 LC_ALL=C
export RESULT_D="$output/results" HARNESS_TAP_COPY="$output/suite.tap"
cd "$build"
exec make run_tests "RESULT_D=$RESULT_D" "TESTS=$*"
