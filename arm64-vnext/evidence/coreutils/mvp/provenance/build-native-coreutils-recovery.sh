#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 || $# == 6 || $# == 7 ]] || exit 2
inputs=$(cygpath -u "$1")
tc=$(cygpath -u "$2")
sdk=$(cygpath -u "$3")
output=$(cygpath -u "$4")
jobs=$5
gmp_provider=${6:-}
runtime_dll=${7:-}
recipe_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
[[ $(sha256sum "$recipe_dir/coreutils-cygwin-dir-fchmod-fallback.patch") == \
    96b27a2de7685c696579d2951cdcdaba11bbe1c6cc1ddf6b7678d35bd214c28c* ]]
[[ $jobs =~ ^[1-6]$ ]] || exit 2

declare -A expected=(
    [gmp-6.3.0.tar.xz]=a3c2b80201b89e68616f4ad30bc66aee4927c3ce50e33929ca819d5c43538898
    [0001-gcc15.patch]=7c4e2eaaf4da1bd69904077a351d585ff022b1d2e742ec25f15886f0063a2cfe
    [coreutils-8.32.tar.xz]=4458d8de7849df44ccab15e16b1548b285224dbba5f08fac070c1c0e0bcc4cfa
    [001-coreutils-8.30.patch]=467bde24da0ccea48260f58d3c94a84de4e027ab598a926003642f791da47ca2
    [002-coreutils-8.32-enable-stdbuf.patch]=e3be62b9aceb3231f09f05bc3bd8b18f6aaa495f5063781cdd261d560a7e80d0
    [003-coreutils-8.32-fix-test-cases.patch]=ad9e0582373500c0668e38483401169f48d6a2f8ad8d28ef8e7b06e4a3e08a74
    [004-msystem-osname-cygwin.patch]=3922afd54b2323772f5cbd0638d0887ef858199bbaf4076a1db318173021c3dc
)
for name in "${!expected[@]}"; do
    actual=$(sha256sum "$inputs/$name")
    [[ ${actual%% *} == "${expected[$name]}" ]]
done

export PATH="$tc/bin:$sdk/usr/bin:/usr/bin"
export LC_ALL=C MSYSTEM=CYGWIN
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export XDG_CACHE_HOME="$output/cache" CCACHE_DISABLE=1
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LD=ld AS=as NM=nm
export CFLAGS="-O2 -g -fstack-protector-strong -Wno-attributes"
export CXXFLAGS="$CFLAGS"
export MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export WOARM64_NATIVE_ARG_CONVERSION=none
mkdir -p "$output/source" "$output/build" "$output/stage" "$output/home" "$output/temp" "$output/cache"
exec > >(tee "$output/build.log") 2>&1

if [[ -n $runtime_dll ]]; then
    runtime_dll=$(cygpath -u "$runtime_dll")
    [[ $(sha256sum "$runtime_dll") == \
        baa144d1848ea17e8dee944279f4dc707f45581bc5a5e912b451a87cbe7abd15* ]]
    install -Dm755 "$runtime_dll" "$output/stage/runtime/usr/bin/msys-2.0.dll"
    export PATH="$output/stage/runtime/usr/bin:$PATH"
fi

if [[ -n $gmp_provider ]]; then
    gmp_provider=$(cygpath -u "$gmp_provider")
    for required in usr/bin/msys-gmp-10.dll usr/include/gmp.h usr/lib/libgmp.dll.a; do
        [[ -f "$gmp_provider/$required" ]]
    done
    cp -a "$gmp_provider/." "$output/stage/gmp/"
    diff -qr "$gmp_provider" "$output/stage/gmp"
else
    tar -xf "$inputs/gmp-6.3.0.tar.xz" -C "$output/source"
    cd "$output/source/gmp-6.3.0"
    patch -p1 -i "$inputs/0001-gcc15.patch"
    [[ $(grep -Fc 'void g(){}' configure) == 2 ]]
    sed -i 's/void g(){}/void g(int,t1 const*,t1,t2,t1 const*,int){}/g' configure
    ! grep -Fq 'void g(){}' configure
    ./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
        --prefix=/usr --enable-cxx --disable-assembly --enable-shared --disable-static
    grep -Fx 'path= generic' config.log
    [[ $(grep -Fc 's/^lib/cyg/' libtool) == 1 ]]
    sed -i 's|s/\^lib/cyg/|s/^lib/msys-/|' libtool
    make -j"$jobs"
    make -j1 DESTDIR="$output/stage/gmp" install
    export PATH="$output/stage/gmp/usr/bin:$PWD/.libs:$PATH"
    make -j1 check
    for direct_test in \
        tests/mpn/.libs/t-divrem_1.exe \
        tests/mpz/.libs/t-tdiv.exe \
        tests/mpf/.libs/t-div.exe \
        tests/misc/.libs/t-printf.exe; do
        "$direct_test"
    done
fi

export PATH="$output/stage/gmp/usr/bin:$PATH"
export CPPFLAGS="-I$output/stage/gmp/usr/include -I$sdk/usr/include"
export LDFLAGS="-Wl,--no-insert-timestamp -L$output/stage/gmp/usr/lib -L$sdk/usr/lib"
tar -xf "$inputs/coreutils-8.32.tar.xz" -C "$output/source"
cd "$output/source/coreutils-8.32"
for patch_name in 001-coreutils-8.30.patch 002-coreutils-8.32-enable-stdbuf.patch \
    003-coreutils-8.32-fix-test-cases.patch 004-msystem-osname-cygwin.patch; do
    patch -p1 -i "$inputs/$patch_name"
done
patch -p1 -i "$recipe_dir/coreutils-cygwin-dir-fchmod-fallback.patch"
[[ $(grep -Fc 'if test "$stdbuf_supported" = "yes" && test -z "$EXEEXT"; then' configure) == 1 ]]
[[ $(grep -Fc "*' stdbuf '*) pkglibexec_PROGRAMS='src/libstdbuf.so';;" configure) == 1 ]]
sed -i 's/if test "$stdbuf_supported" = "yes" && test -z "$EXEEXT"; then/if test "$stdbuf_supported" = "yes"; then/' configure
sed -i "s|\\*' stdbuf '\\*) pkglibexec_PROGRAMS='src/libstdbuf.so';;|*' stdbuf '*) pkglibexec_PROGRAMS='src/libstdbuf.so\$(EXEEXT)';;|" configure
[[ $(grep -hF '    dd ibs=$n_ count=1 if=$dev_rand_ 2>/dev/null \' \
    tests/init.sh gnulib-tests/init.sh | wc -l) == 2 ]]
sed -i 's|^    dd ibs=$n_ count=1 if=$dev_rand_ 2>/dev/null \\$|    "${COREUTILS_TEST_BOOTSTRAP_DD:-dd}" ibs=$n_ count=1 if=$dev_rand_ 2>/dev/null \\|' \
    tests/init.sh gnulib-tests/init.sh
find . -type f -exec touch -d '2000-01-01 00:00:00 UTC' {} +
touch -d '2000-01-02 00:00:00 UTC' \
    m4/cu-progs.m4 src/cu-progs.mk src/single-binary.mk
touch -d '2000-01-03 00:00:00 UTC' aclocal.m4
find . \( -name configure -o -name Makefile.in \) \
    -exec touch -d '2000-01-04 00:00:00 UTC' {} +
mkdir "$output/build/coreutils"
cd "$output/build/coreutils"
export gl_cv_have_weak=no
"$output/source/coreutils-8.32/configure" \
    --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
    --prefix=/usr --libexecdir=/usr/lib --sysconfdir=/etc --localstatedir=/var \
    --program-transform-name=s/kill/gkill/ \
    --without-libintl-prefix --without-libiconv-prefix \
    --enable-install-program=arch,hostname --enable-no-install-program=uptime \
    gl_cv_func_strtod_works=yes gl_cv_func_strtold_works=yes
if [[ -f libtool ]]; then
    [[ $(grep -Fc 's/^lib/cyg/' libtool) == 1 ]]
    sed -i 's|s/\^lib/cyg/|s/^lib/msys-/|' libtool
fi
make -j"$jobs"
make -j1 DESTDIR="$output/stage/coreutils" install
if [[ -f "$output/stage/coreutils/usr/lib/coreutils/libstdbuf.so.exe" ]]; then
    mv "$output/stage/coreutils/usr/lib/coreutils/libstdbuf.so.exe" \
        "$output/stage/coreutils/usr/lib/coreutils/libstdbuf.dll"
fi
install -Dm644 "$output/source/coreutils-8.32/src/dircolors.hin" \
    "$output/stage/coreutils/etc/DIR_COLORS"
export COREUTILS_TEST_BOOTSTRAP_DD=/usr/bin/dd
make -j1 check
