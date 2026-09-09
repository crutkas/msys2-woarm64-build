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

[[ $# == 12 ]] || exit 2
inputs=$(to_posix_path "$1")
tc=$(to_posix_path "$2")
sdk=$(to_posix_path "$3")
gmp=$(to_posix_path "$4")
runtime_dll=$(to_posix_path "$5")
coreutils=$(to_posix_path "$6")
output=$(to_posix_path "$7")
jobs=$8
launch_contract=$(to_posix_path "$9")
host=$(to_posix_path "${10}")
native_prefix=$(to_posix_path "${11}")
runtime_sha256=${12}
sha256="$host/usr/bin/sha256sum.exe"
[[ $jobs =~ ^[1-6]$ ]] || exit 2
[[ $runtime_sha256 =~ ^[0-9a-f]{64}$ ]]
[[ $("$sha256" "$launch_contract") == \
    e3ab7e8f901601e327eb74f52bbd9117d40746a977bfa381d319e080bf91132f* ]]
native_shell="$native_prefix/usr/bin/bash.exe"
host_shell="$host/usr/bin/bash.exe"
[[ $("$sha256" "$native_shell") == \
    0937e8a6c5811b044efeb9cd1f1074bda10a913ebab345bd4a6827305f891a0c* ]]
[[ $("$sha256" "${native_shell%/*}/msys-2.0.dll") == "$runtime_sha256 "* ]]

declare -A expected=(
    [mpfr-4.2.2.tar.xz]=b67ba0383ef7e8a8563734e2e889ef5ec3c3b898a01d00fa0a6869ad81c6ce01
    [gawk-5.4.1.tar.gz]=8b3b0ea83930311a3f30905d3ce898d32c6103c2fe20d6a90b40341171b174de
    [pcre-8.45.tar.bz2]=4dae6fdcd2bb0bb6c37b5f97c33c2be954da743985369cddac3546e3218bffb8
    [pcre-8.33-msys2-fix-ln.patch]=ef9fffef05c53450d196c7997a7de8883e58b8d8a5bbc0abb412d8a22797bb34
    [grep-3.0.tar.xz]=e2c81db5056e3e8c5995f0bb5d0d0e1cad1f6f45c3b2fc77b6e81435aed48ab5
    [sed-4.9.tar.xz]=6e226b732e1cd739464ad6862bd1a1aba42d7982922da7a53519631d24975181
    [sed-4.4-1.src.patch]=12525e7bf4a1b57913d4047a2313f9127f29468193c2b583cfdfa128b4141032
    [sed-4.4-msys-use-text-mode.patch]=a6cf37f31c11f5fbc6d11fb379a3feabdcbe0606b69941d82449d106299ffbf6
    [findutils-4.11.0.tar.xz]=bfd19cb06cc71f3352d567e90284d8cdac02ac89774bbeadf0b533b0c11432fd
    [diffutils-3.12.tar.xz]=7c8b7f9fc8609141fdea9cece85249d308624391ff61dedaf528fcb337727dfd
    [util-linux-2.40.2.tar.xz]=d78b37a66f5922d70edf3bdfb01a6b33d34ed3c3cafd6628203b2a2b67c8e8b3
    [util-linux-2.39.3-cygwin-include.patch]=224505c3624f61f085130b4bc440c6237b19536bcdda57599ea4100f8b704d42
    [locale-d890a845e992.cc]=b71587c387b8e1c26fa1925126e2ebb9620d8cab3f4b703f7fd31850c3066e28
)
for name in "${!expected[@]}"; do
    actual=$("$sha256" "$inputs/$name")
    [[ ${actual%% *} == "${expected[$name]}" ]]
done
[[ $("$sha256" "$runtime_dll") == "$runtime_sha256 "* ]]
for required in usr/bin/msys-gmp-10.dll usr/include/gmp.h usr/lib/libgmp.dll.a; do
    [[ -f "$gmp/$required" ]]
done
for required in usr/bin/cat.exe usr/bin/mkdir.exe usr/bin/tr.exe usr/bin/wc.exe; do
    [[ -f "$coreutils/$required" ]]
done

mkdir -p "$output/source" "$output/build" "$output/stage/usr/bin" \
    "$output/home" "$output/temp" "$output/cache"
exec > >(tee "$output/build.log") 2>&1
"$host/usr/bin/cp.exe" -a "$coreutils/." "$output/stage/"
"$host/usr/bin/install.exe" -Dm755 "$runtime_dll" "$output/stage/usr/bin/msys-2.0.dll"
"$host/usr/bin/cp.exe" -a "$gmp/." "$output/stage/"
for shell_binary in bash.exe sh.exe; do
    "$host/usr/bin/cp.exe" "$native_prefix/usr/bin/$shell_binary" \
        "$output/stage/usr/bin/$shell_binary"
done
for dll in "$sdk"/usr/bin/msys-*.dll; do
    target="$output/stage/usr/bin/${dll##*/}"
    if [[ -e $target ]]; then
        existing=$("$sha256" "$target")
        incoming=$("$sha256" "$dll")
        [[ ${existing%% *} == "${incoming%% *}" ]]
    else
        "$host/usr/bin/cp.exe" "$dll" "$target"
    fi
done

export PATH="$tc/bin:$sdk/usr/bin:$host/usr/bin:$output/stage/usr/bin:$native_prefix/usr/bin"
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export XDG_CACHE_HOME="$output/cache" CCACHE_DISABLE=1
export LC_ALL=C MSYSTEM=CYGWIN
export WOARM64_NATIVE_ARG_CONVERSION=none
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm
export CFLAGS="-O2 -g -fstack-protector-strong -Wno-attributes"
export CXXFLAGS="$CFLAGS"
export CPPFLAGS="-I$output/stage/usr/include -I$sdk/usr/include"
export LDFLAGS="-Wl,--no-insert-timestamp -L$output/stage/usr/lib -L$sdk/usr/lib"
export MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export SHELL="$host_shell" CONFIG_SHELL="$host_shell"
unset MSYS2_ARG_CONV_EXCL

make()
{
    command "$host/usr/bin/make.exe" SHELL="$host_shell" "$@"
}

fix_libtool_names()
{
    while IFS= read -r -d '' libtool; do
        if grep -Fq 's/^lib/cyg/' "$libtool"; then
            sed -i 's|s/\^lib/cyg/|s/^lib/msys-/|' "$libtool"
        fi
    done < <(find . -name libtool -type f -print0)
}

build_in_source()
{
    local package=$1 archive=$2
    shift 2
    if [[ ! -d "$output/source/$package" ]]; then
        tar -xf "$inputs/$archive" -C "$output/source"
    fi
    cd "$output/source/$package"
    printf 'configure-parent=%s package=%s\n' "$host_shell" "$package"
    "$host_shell" --noprofile --norc -c \
        'printf "configure-path=%s\n" "$PATH"; command -v sed expr awk'
    "$@"
}

build_mpfr()
{
    "$host_shell" ./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
        --prefix=/usr --enable-shared --disable-static
    fix_libtool_names
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage" install
}
if [[ ! -f "$output/stage/usr/bin/msys-mpfr-6.dll" \
      || ! -f "$output/stage/usr/include/mpfr.h" \
      || ! -f "$output/stage/usr/lib/libmpfr.dll.a" ]]; then
    build_in_source mpfr-4.2.2 mpfr-4.2.2.tar.xz build_mpfr
fi
for libtool_archive in "$output/stage/usr/lib/libmpfr.la" \
    "$output/stage/usr/lib/libgmpxx.la"; do
    [[ -f $libtool_archive ]] || continue
    sed -i \
        "s| /usr/lib/libgmp.la| $output/stage/usr/lib/libgmp.la|g" \
        "$libtool_archive"
done

build_gawk()
{
    export gl_cv_have_weak=no
    "$host_shell" ./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
        --prefix=/usr --libexecdir=/usr/lib \
        --without-libiconv-prefix --without-libintl-prefix
    fix_libtool_names
    export MSYS2_ARG_CONV_EXCL='-DDEFPATH=;-DDEFLIBPATH=;-DLOCALEDIR='
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage" install
    unset MSYS2_ARG_CONV_EXCL
    [[ -e "$output/stage/usr/bin/gawk.exe" ]]
    cp "$output/stage/usr/bin/gawk.exe" "$output/stage/usr/bin/awk.exe"
}
if [[ ! -f "$output/stage/usr/bin/gawk.exe" ]]; then
    build_in_source gawk-5.4.1 gawk-5.4.1.tar.gz build_gawk
fi

build_pcre()
{
    patch -p1 -i "$inputs/pcre-8.33-msys2-fix-ln.patch"
    "$host_shell" ./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
        --prefix=/usr --enable-newline-is-anycrlf --enable-unicode-properties \
        --enable-utf --disable-cpp --disable-pcre16 --disable-pcre32 \
        --disable-pcregrep-libbz2 --disable-pcregrep-libz \
        --disable-pcretest-libreadline --disable-stack-for-recursion
    fix_libtool_names
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage" install
}
if [[ ! -f "$output/stage/usr/bin/pcregrep.exe" ]]; then
    build_in_source pcre-8.45 pcre-8.45.tar.bz2 build_pcre
fi

build_grep()
{
    export gl_cv_have_weak=no
    "$host_shell" ./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
        --prefix=/usr --without-libiconv-prefix --without-libintl-prefix
    fix_libtool_names
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage" install
}
if [[ ! -f "$output/stage/usr/bin/grep.exe" ]]; then
    build_in_source grep-3.0 grep-3.0.tar.xz build_grep
fi

build_sed()
{
    patch -p1 -i "$inputs/sed-4.4-msys-use-text-mode.patch"
    grep -Fxq 'install-html:;' po/Makefile.in.in
    export gl_cv_have_weak=no
    "$host_shell" ./configure --build=aarch64-pc-cygwin \
        --host=aarch64-pc-cygwin --prefix=/usr
    fix_libtool_names
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage" install
    rm -f "$output/stage/usr/lib/charset.alias"
}
if [[ ! -f "$output/stage/usr/bin/sed.exe" ]]; then
    build_in_source sed-4.9 sed-4.9.tar.xz build_sed
fi

build_findutils()
{
    "$host_shell" ./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
        --prefix=/usr --without-libiconv-prefix --without-libintl-prefix \
        'DEFAULT_ARG_SIZE=(32u*1024)'
    fix_libtool_names
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage" install
}
if [[ ! -f "$output/stage/usr/bin/find.exe" \
      || ! -f "$output/stage/usr/bin/xargs.exe" ]]; then
    build_in_source findutils-4.11.0 findutils-4.11.0.tar.xz build_findutils
fi

build_diffutils()
{
    local stage_shell="$output/stage/usr/bin/bash.exe"
    local cache_file="$output/cache/diffutils-config.cache"
    local stddef_template=lib/stddef.in.h
    local old_stddef_guard='    && !@STDDEF_NOT_IDEMPOTENT@'
    local new_stddef_guard='    && (!@STDDEF_NOT_IDEMPOTENT@ || defined __need_wint_t)'
    # GCC 15's C23 stddef macro is non-idempotent, but Cygwin still requires
    # the special __need_wint_t include path from sys/_types.h.
    if grep -Fqx "$old_stddef_guard" "$stddef_template"; then
        awk -v old="$old_stddef_guard" -v new="$new_stddef_guard" \
            '{ if ($0 == old) { print new; changed = 1 } else print }
             END { if (!changed) exit 3 }' \
            "$stddef_template" > "$stddef_template.tmp"
        mv "$stddef_template.tmp" "$stddef_template"
    fi
    grep -Fqx "$new_stddef_guard" "$stddef_template"
    # The 32 MiB gnulib stack-overflow conftest ICEs this ARM64 GCC build.
    # Selecting "no" enables gnulib's fallback instead of claiming it works.
    printf '%s\n' \
        'sv_cv_sigaltstack=${sv_cv_sigaltstack=no}' > "$cache_file"
    PATH="$output/stage/usr/bin:$tc/bin:$sdk/usr/bin:$host/usr/bin" \
        CONFIG_SHELL="$stage_shell" \
        MSYS2_ARG_CONV_EXCL='--prefix=' \
        "$stage_shell" ./configure \
            --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
            --prefix=/usr --without-libiconv-prefix --without-libintl-prefix \
            --cache-file="$cache_file"
    fix_libtool_names
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage" install
}
if [[ ! -f "$output/stage/usr/bin/diff.exe" \
      || ! -f "$output/stage/usr/bin/cmp.exe" ]]; then
    build_in_source diffutils-3.12 diffutils-3.12.tar.xz build_diffutils
fi

if [[ ! -f "$output/stage/usr/bin/locale.exe" ]]; then
    "$CXX" $CXXFLAGS -D_WIN32_WINNT=0x0a00 -static \
        -Wl,--enable-auto-import -Wl,--no-insert-timestamp \
        -o "$output/stage/usr/bin/locale.exe" \
        "$inputs/locale-d890a845e992.cc" -lnetapi32
fi

build_hexdump()
{
    local source="$output/source/util-linux-2.40.2"
    local build="$output/build/util-linux-2.40.2"
    if [[ ! -d $source ]]; then
        tar -xf "$inputs/util-linux-2.40.2.tar.xz" -C "$output/source"
    fi
    if ! grep -q '^#ifdef ECHOPRT$' "$source/include/ttyutils.h"; then
        (
            cd "$source"
            patch -p2 --forward --batch \
                -i "$inputs/util-linux-2.39.3-cygwin-include.patch"
        )
    fi
    mkdir -p "$build"
    cd "$build"
    "$host_shell" "$source/configure" \
        --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
        --prefix=/usr --bindir=/usr/bin --disable-dependency-tracking \
        --disable-nls \
        --disable-liblastlog2 --disable-makeinstall-chown \
        --disable-makeinstall-setuid --without-libiconv-prefix \
        --without-libintl-prefix
    make -j"$jobs" hexdump.exe
    # Libtool leaves a launcher at the build root; package the real linked binary.
    install -Dm755 .libs/hexdump.exe "$output/stage/usr/bin/hexdump.exe"
}
if [[ ! -f "$output/stage/usr/bin/hexdump.exe" ]]; then
    build_hexdump
fi

cd "$output"
required=(awk basename cat chmod cmp cp cut date diff dirname echo env expr false find grep head
    hexdump id ln locale ls mkdir mkfifo mktemp mv od pcregrep printenv printf pwd readlink rm
    rmdir sed sleep sort tail tee test touch tr true wc xargs)
for tool in "${required[@]}"; do
    executable="$output/stage/usr/bin/$tool.exe"
    [[ -f $executable ]]
    identity=$("$tc/bin/objdump.exe" -f "$executable")
    [[ $identity == *"file format pei-aarch64-little"* ]]
done
