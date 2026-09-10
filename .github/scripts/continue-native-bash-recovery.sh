#!/usr/bin/env bash
set -euo pipefail

[[ $# == 4 ]] || exit 2
root=$(cygpath -u "$1")
tc=$(cygpath -u "$2")
sdk=$(cygpath -u "$3")
jobs=$4
[[ $jobs =~ ^[1-6]$ ]] || exit 2
[[ -f "$root/source/config.status" && -f "$root/stage/usr/bin/bash.exe" ]]

export PATH="$tc/bin:$sdk/usr/bin:/usr/bin" LC_ALL=C MSYSTEM=CYGWIN
unset CC CXX CPP CPPFLAGS CFLAGS CXXFLAGS LDFLAGS CONFIG_SITE
unset LIBRARY_PATH COMPILER_PATH GCC_EXEC_PREFIX
export CC=gcc CXX=g++ CC_FOR_BUILD=gcc AR=ar RANLIB=ranlib LD=ld AS=as NM=nm
export CFLAGS="-O2 -g -fstack-protector-strong"
export CXXFLAGS="$CFLAGS" CFLAGS_FOR_BUILD="$CFLAGS"
export CPPFLAGS="-DWORDEXP_OPTION -DLIBINTL_STATIC -DLIBICONV_STATIC -DNCURSES_STATIC -I$(cygpath -m "$sdk/usr/include") -I$(cygpath -m "$sdk/usr/include/ncursesw")"
export LDFLAGS="-Wl,--no-insert-timestamp -L$(cygpath -m "$sdk/usr/lib")"
export CONFIG_SITE=/dev/null CCACHE_DISABLE=1 MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 WOARM64_NATIVE_ARG_CONVERSION=none
export HOME="$root/home" TMPDIR="$root/temp" TMP="$root/temp" TEMP="$root/temp"
export XDG_CACHE_HOME="$root/cache" TERMINFO="$sdk/usr/share/terminfo"
[[ -n ${WOARM64_NATIVE_EXIT_DIR:-} && -d $WOARM64_NATIVE_EXIT_DIR ]]
grep -A2 '^cygwin\*)' "$root/source/support/shobj-conf" |
    grep -Fq "SHOBJ_LD='\${CC}'"

cat > "$root/dlopen-provider.c" <<'EOF'
__declspec(dllexport) int native_dlopen_probe(void)
{
    return 42;
}
EOF
cat > "$root/dlopen-probe.c" <<'EOF'
#include <dlfcn.h>
int main(void)
{
    void *handle = dlopen("./dlopen-provider.dll", RTLD_NOW);
    if (!handle)
        return 1;
    int (*probe)(void) = (int (*)(void)) dlsym(handle, "native_dlopen_probe");
    if (!probe || probe() != 42)
        return 2;
    return dlclose(handle) != 0;
}
EOF
gcc $CPPFLAGS $CFLAGS -shared $LDFLAGS \
    -o "$root/dlopen-provider.dll" "$root/dlopen-provider.c"
gcc $CPPFLAGS $CFLAGS -static $LDFLAGS \
    -o "$root/dlopen-probe.exe" "$root/dlopen-probe.c"
(cd "$root" && ./dlopen-probe.exe)

export ac_cv_func_dlopen=yes ac_cv_func_dlclose=yes ac_cv_func_dlsym=yes
cd "$root/source"
./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
    --prefix=/usr --sysconfdir=/etc --localstatedir=/var \
    --enable-static-link --enable-readline "--with-installed-readline=$sdk/usr" \
    --enable-nls --enable-multibyte --enable-job-control --without-bash-malloc --with-curses \
    "--with-libintl-prefix=$sdk/usr" "--with-libiconv-prefix=$sdk/usr" \
    bash_cv_dev_stdin=present bash_cv_dev_fd=standard bash_cv_termcap_lib=libncurses
grep -qx '#define WEXITSTATUS_OFFSET 8' config.h
for feature in HAVE_DLOPEN HAVE_DLCLOSE HAVE_DLSYM; do
    sed -i "s@/\\* #undef $feature \\*/@#define $feature 1@" config.h
done
for makefile in examples/loadables/Makefile examples/loadables/Makefile.inc; do
    sed -i "s@^SHOBJ_LIBS =.*@SHOBJ_LIBS = $PWD/libbash.dll.a -lintl -liconv@" "$makefile"
done
grep -qx '#define HAVE_DLOPEN 1' config.h
grep -qx 'SHOBJ_STATUS = supported' examples/loadables/Makefile

make_args=(HISTORY_LDFLAGS= READLINE_LDFLAGS=
           'LOCAL_LDFLAGS=-Wl,--export-all,--out-implib,libbash.dll.a'
           'LDFLAGS_FOR_BUILD=$(CFLAGS_FOR_BUILD)'
           "SHOBJ_LIBS=$PWD/libbash.dll.a -lintl -liconv")
make -j"$jobs" "${make_args[@]}"
make -j1 "${make_args[@]}" DESTDIR="$root/stage" install
cp "$root/stage/usr/bin/bash.exe" "$root/stage/usr/bin/sh.exe"
cp libbash.dll.a "$root/stage/usr/lib/"
