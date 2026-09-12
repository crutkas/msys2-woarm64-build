#!/usr/bin/env bash
set -euo pipefail

if test "$#" -ne 9; then
    echo "usage: $0 OUTPUT PRIOR SOURCE_ROOT COMPILER_ROOT SDK_ROOT FIXTURE SYSTEM32 LIBTOOL_ROOT TEST_TOOLS_ROOT" >&2
    exit 2
fi

output="$(cygpath -u "$1")"
prior="$(cygpath -u "$2")"
sources="$(cygpath -u "$3")"
compiler="$(cygpath -u "$4")"
sdk="$(cygpath -u "$5")"
fixture="$(cygpath -au "$6")"
system32="$(cygpath -u "$7")"
libtool="$(cygpath -u "${8//\\//}")"
test_tools="$(cygpath -u "${9//\\//}")"
bootstrap_bin="$(dirname "$(command -v autoreconf)")"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
pthread_patch="$repo_root/.github/patches/native-msys-pcre2-cygwin-jit-pthread.patch"
test_command_patch="$repo_root/.github/patches/native-msys-pcre2-test-command.patch"
locale_fixture="$sources/pcre2-10.48-testoutput3C"
native_exec="$repo_root/.github/scripts/native-target-exec.sh"
native_relay="$(cygpath -am "$repo_root/.github/scripts/native-target-exec.py")"
msys_argv_relay_source="$repo_root/tests/native-msys-argv-relay.c"
native_python="/c/ap12-ca5f/git-python-readback-01/mingwarm64/bin/python.exe"
native_python_sha256="c55badc4658c6a5e01f21959ae813a66060b786b3297b67991b27a673327652f"
native_echo="$test_tools/usr/bin/echo.exe"
native_echo_sha256="bc7bf74e4a6045dbaca3eab8edb3277c74db128269aa7d9631fa0f2a3917e99e"
native_iconv="$test_tools/usr/bin/msys-iconv-2.dll"
native_iconv_sha256="86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215"
native_intl="$test_tools/usr/bin/msys-intl-8.dll"
native_intl_sha256="eef1befd674c9febcfe769601d8e10a1022b00dabffa383b866847b935eb054d"
test_runtime_sha256="907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"

: "${WOARM64_NATIVE_TEST_ROOT:?native test root is required}"
: "${WOARM64_NATIVE_EXIT_DIR:?native exit receipt directory is required}"

if test -e "$output"; then
    echo "fresh PCRE2 continuation output required: $output" >&2
    exit 3
fi
for required in \
    "$prior/stage/bzip2/bin/msys-bz2-1.dll" \
    "$prior/stage/bzip2/lib/libbz2.dll.a" \
    "$prior/stage/zlib/usr/bin/msys-z.dll" \
    "$prior/stage/zlib/usr/lib/libz.dll.a" \
    "$prior/logs/bzip2-check.log" \
    "$prior/logs/zlib-check.log"; do
    if ! test -f "$required"; then
        echo "completed prerequisite evidence missing: $required" >&2
        exit 4
    fi
done
for required in \
    "$pthread_patch" \
    "$test_command_patch" \
    "$locale_fixture" \
    "$native_exec" \
    "$native_relay" \
    "$msys_argv_relay_source" \
    "$native_python" \
    "$native_echo" \
    "$native_iconv" \
    "$native_intl" \
    "$test_tools/usr/bin/msys-2.0.dll"; do
    if ! test -f "$required"; then
        echo "required PCRE2 continuation input missing: $required" >&2
        exit 5
    fi
done
if test "$(sha256sum "$locale_fixture" | cut -d' ' -f1)" != \
    "f98a13c2ce08ffb97340c3cc57caa85984923fc2ac44a1fc0c7408fc091212a0"; then
    echo "upstream PCRE2 locale fixture changed: $locale_fixture" >&2
    exit 6
fi
if test "$(sha256sum "$native_python" | cut -d' ' -f1)" != "$native_python_sha256"; then
    echo "native relay Python changed: $native_python" >&2
    exit 7
fi
if test "$(sha256sum "$native_echo" | cut -d' ' -f1)" != "$native_echo_sha256"; then
    echo "native script-callout echo fixture changed: $native_echo" >&2
    exit 10
fi
if test "$(sha256sum "$native_iconv" | cut -d' ' -f1)" != "$native_iconv_sha256"; then
    echo "native script-callout iconv dependency changed: $native_iconv" >&2
    exit 12
fi
if test "$(sha256sum "$native_intl" | cut -d' ' -f1)" != "$native_intl_sha256"; then
    echo "native script-callout intl dependency changed: $native_intl" >&2
    exit 13
fi
if test "$(sha256sum "$test_tools/usr/bin/msys-2.0.dll" | cut -d' ' -f1)" != \
    "$test_runtime_sha256"; then
    echo "native script-callout fixture runtime changed" >&2
    exit 11
fi

umask 022
mkdir -p "$output"/{src,stage,runtime/usr/bin,logs,home,temp,native-exits}
if test "$(cygpath -u "$WOARM64_NATIVE_TEST_ROOT")" != "$output"; then
    echo "native test root must match the fresh continuation output" >&2
    exit 8
fi
if ! test -d "$(cygpath -u "$WOARM64_NATIVE_EXIT_DIR")"; then
    echo "native exit receipt directory does not exist" >&2
    exit 9
fi
cp -a "$prior/stage/bzip2" "$output/stage/"
cp -a "$prior/stage/zlib" "$output/stage/"
cp "$prior/logs/bzip2-"*.log "$output/logs/"
cp "$prior/logs/zlib-"*.log "$output/logs/"

runtime_bin="$output/runtime/usr/bin"
export HOME="$output/home"
export TMP="$output/temp"
export TEMP="$output/temp"
export TMPDIR="$output/temp"
export MAKEFLAGS=-j1
export MFLAGS=-j1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export CCACHE_DISABLE=1
export CHOST=aarch64-pc-cygwin
export CC="$compiler/bin/gcc.exe"
export CXX="$compiler/bin/g++.exe"
export AR="$compiler/bin/ar.exe"
export RANLIB="$compiler/bin/ranlib.exe"
export STRIP="$compiler/bin/strip.exe"
export WINDRES="$compiler/bin/windres.exe"
export PATH="$runtime_bin:$compiler/bin:$libtool/bin:$bootstrap_bin:$system32"
export ACLOCAL=aclocal-1.18
export AUTOMAKE=automake-1.18
export LIBTOOLIZE="$libtool/bin/libtoolize"
export _lt_pkgdatadir="$libtool/generator-data"
export CFLAGS="-O2 -g -pipe -fstack-protector-strong -D_FORTIFY_SOURCE=2"
export CPPFLAGS="-I$output/stage/bzip2/include -I$output/stage/zlib/usr/include -I$sdk/usr/include -I$sdk/usr/include/ncursesw"
export LDFLAGS="-L$output/stage/bzip2/lib -L$output/stage/zlib/usr/lib -L$sdk/usr/lib -Wl,--no-insert-timestamp"
export PKG_CONFIG_PATH="$output/stage/zlib/usr/lib/pkgconfig:$sdk/usr/lib/pkgconfig"

cp "$compiler/bin/msys-2.0.dll" "$runtime_bin/"
cp "$sdk/usr/bin/msys-readline8.dll" "$runtime_bin/"
cp "$sdk/usr/bin/msys-history8.dll" "$runtime_bin/"
cp "$sdk/usr/bin/msys-ncursesw6.dll" "$runtime_bin/"
cp "$output/stage/bzip2/bin/msys-bz2-1.dll" "$runtime_bin/"
cp "$output/stage/zlib/usr/bin/msys-z.dll" "$runtime_bin/"
cp "$native_echo" "$runtime_bin/"
cp "$native_iconv" "$runtime_bin/"
cp "$native_intl" "$runtime_bin/"

if test -d "$prior/src/pcre2-10.48" && test -f "$prior/logs/pcre2-build.log"; then
    cp -a "$prior/src/pcre2-10.48" "$output/src/"
else
    tar -xf "$sources/pcre2-10.48.tar.bz2" -C "$output/src"
fi
cd "$output/src/pcre2-10.48"
rm -rf testoutput* test-suite.log ./*.log ./*.trs \
    testtrygrep teststdout testSoutput
cp "$locale_fixture" testdata/testoutput3C
if ! grep -Fq 'command -v "$pcre2grep"' RunGrepTest; then
    patch -p1 --forward --batch <"$test_command_patch" \
        >"$output/logs/pcre2-test-command-patch.log" 2>&1
else
    cp "$prior/logs/pcre2-test-command-patch.log" "$output/logs/"
fi
if grep -Fq "cygwin*) PTHREAD_LIBS=" configure.ac &&
    test -f .libs/msys-pcre2-8-0.dll &&
    test -f .libs/msys-pcre2-16-0.dll &&
    test -f .libs/msys-pcre2-32-0.dll &&
    test -f .libs/msys-pcre2-posix-3.dll; then
    cp "$prior/logs/pcre2-pthread-patch.log" "$output/logs/"
    cp "$prior/logs/pcre2-autoreconf.log" "$output/logs/"
    cp "$prior/logs/pcre2-configure.log" "$output/logs/"
    cp "$prior/logs/pcre2-build.log" "$output/logs/"
else
    patch -p1 --forward --batch <"$pthread_patch" \
        >"$output/logs/pcre2-pthread-patch.log" 2>&1
    autoreconf -fi >"$output/logs/pcre2-autoreconf.log" 2>&1
    ./configure \
        --build="$CHOST" \
        --prefix=/usr \
        --enable-jit \
        --enable-pcre2-8 \
        --enable-pcre2-16 \
        --enable-pcre2-32 \
        --enable-newline-is-anycrlf \
        --enable-unicode \
        --enable-pcre2grep-jit \
        --enable-pcre2grep-libbz2 \
        --enable-pcre2grep-libz \
        --disable-pcre2test-libedit \
        --enable-pcre2test-libreadline \
        ac_cv_header_windows_h=no \
        >"$output/logs/pcre2-configure.log" 2>&1
    make -j1 >"$output/logs/pcre2-build.log" 2>&1
fi

export WOARM64_NATIVE_PYTHON="$native_python"
export WOARM64_NATIVE_PYTHON_SHA256="$native_python_sha256"
export WOARM64_NATIVE_RELAY="$native_relay"
export WOARM64_NATIVE_PYTHON_COMMAND="$native_python"
"$CC" $CFLAGS "$msys_argv_relay_source" \
    -Wl,--no-insert-timestamp \
    -o "$runtime_bin/native-msys-argv-relay.exe" \
    >"$output/logs/argv-relay-compile.log" 2>&1

export WOARM64_MSYS_ARGV_RELAY="$(cygpath -am "$runtime_bin/native-msys-argv-relay.exe")"
woarm64_native_msys_target()
{
    local target=$1 argument index name
    shift
    export WOARM64_MSYS_TARGET="$target"
    export WOARM64_MSYS_ARG_COUNT=$#
    index=0
    for argument in "$@"; do
        printf -v name 'WOARM64_MSYS_ARG_%d' "$index"
        printf -v "$name" 'v1:%s' "$argument"
        export "$name"
        index=$((index + 1))
    done
    export MSYS2_ARG_CONV_EXCL='*' MSYS_NO_PATHCONV=1
    export WOARM64_NATIVE_ARG_COUNT=0
    unset WOARM64_NATIVE_PATH_CONVERSION WOARM64_NATIVE_MSYS_ROOT
    "$WOARM64_NATIVE_PYTHON_COMMAND" -I "$WOARM64_NATIVE_RELAY" \
        "$WOARM64_MSYS_ARGV_RELAY"
}
woarm64_pcre2test()
{
    woarm64_native_msys_target "$WOARM64_PCRE2TEST" "$@"
}
woarm64_pcre2grep()
{
    woarm64_native_msys_target "$WOARM64_PCRE2GREP" "$@"
}
export -f woarm64_native_msys_target woarm64_pcre2test woarm64_pcre2grep
export WOARM64_PCRE2TEST="$(cygpath -am "$output/src/pcre2-10.48/.libs/pcre2test.exe")"
export WOARM64_PCRE2GREP="$(cygpath -am "$output/src/pcre2-10.48/.libs/pcre2grep.exe")"

pcre2test=woarm64_pcre2test \
    pcre2grep=woarm64_pcre2grep \
    make -j1 check >"$output/logs/pcre2-check.log" 2>&1
make DESTDIR="$output/stage/pcre2" install >"$output/logs/pcre2-install.log" 2>&1
cp "$output/stage/pcre2/usr/bin/"msys-pcre2-*-0.dll "$runtime_bin/"
cp "$output/stage/pcre2/usr/bin/msys-pcre2-posix-3.dll" "$runtime_bin/"

"$CC" $CFLAGS \
    -I"$output/stage/pcre2/usr/include" \
    "$fixture" \
    -L"$output/stage/pcre2/usr/lib" -lpcre2-8 \
    -Wl,--no-insert-timestamp \
    -o "$runtime_bin/native-pcre2-jit-api.exe" \
    >"$output/logs/api-compile.log" 2>&1

woarm64_native_msys_target \
    "$(cygpath -am "$runtime_bin/native-pcre2-jit-api.exe")" \
    "$(cygpath -am "$output/native-pcre2-jit-api.json")" \
    >"$output/logs/api-run.log" 2>&1

printf '%s\n' "native MSYS PCRE2 continuation and strict upstream check completed" \
    >"$output/build-complete.txt"
