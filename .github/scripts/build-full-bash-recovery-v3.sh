#!/usr/bin/env bash
set -euo pipefail
[[ $# == 5 ]] || exit 2
source_root=$(cygpath -u "$1") tc=$(cygpath -u "$2")
sdk=$(cygpath -u "$3") output=$(cygpath -u "$4") jobs=$5
[[ $jobs =~ ^[1-6]$ ]] || exit 2
native_python=${WOARM64_NATIVE_PYTHON:-$(command -v python.exe)}
[[ -n $native_python ]] || { echo "Verified native Python is required" >&2; exit 2; }
native_python=$(cygpath -u "$native_python")
runtime_sha=${WOARM64_TC_RUNTIME_SHA256:-}
import_sha=${WOARM64_TC_IMPORT_SHA256:-}
crt_sha=${WOARM64_TC_CRT0_SHA256:-}
[[ $runtime_sha =~ ^[0-9a-f]{64}$ &&
   $import_sha =~ ^[0-9a-f]{64}$ &&
   $crt_sha =~ ^[0-9a-f]{64}$ ]] ||
    { echo "Sealed compiler runtime, import-library, and CRT hashes are required" >&2; exit 2; }
export PATH="$tc/bin:$sdk/usr/bin:/usr/bin" LC_ALL=C MSYSTEM=CYGWIN
unset CC CXX CPP CPPFLAGS CFLAGS CXXFLAGS LDFLAGS CONFIG_SITE LIBRARY_PATH COMPILER_PATH GCC_EXEC_PREFIX
export CC=gcc CXX=g++ CC_FOR_BUILD=gcc AR=ar RANLIB=ranlib LD=ld AS=as NM=nm
export CFLAGS="-O2 -g -fstack-protector-strong" CXXFLAGS="-O2 -g -fstack-protector-strong"
export CFLAGS_FOR_BUILD="$CFLAGS"
export CPPFLAGS="-DWORDEXP_OPTION -DLIBINTL_STATIC -DLIBICONV_STATIC -DNCURSES_STATIC -I$(cygpath -m "$sdk/usr/include") -I$(cygpath -m "$sdk/usr/include/ncursesw")"
export LDFLAGS="-Wl,--no-insert-timestamp -L$(cygpath -m "$sdk/usr/lib")"
export CONFIG_SITE=/dev/null CCACHE_DISABLE=1 MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs"
host_locale=$(cygpath -am /usr/share/locale)
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 WOARM64_NATIVE_ARG_CONVERSION=none
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export XDG_CACHE_HOME="$output/cache" TERMINFO="$sdk/usr/share/terminfo"
mkdir -p "$HOME" "$TMPDIR" "$XDG_CACHE_HOME" "$output/source" "$output/stage"
for sealed_input in \
    "$runtime_sha:$tc/bin/msys-2.0.dll" \
    "$import_sha:$tc/aarch64-pc-cygwin/lib/libmsys-2.0.a" \
    "$crt_sha:$tc/aarch64-pc-cygwin/lib/crt0.o"; do
    expected=${sealed_input%%:*}
    input=${sealed_input#*:}
    actual=$(sha256sum "$input")
    [[ ${actual%% *} == "$expected" ]] ||
        { echo "Compiler cohort mismatch: $input" >&2; exit 3; }
done
cp -a "$source_root/." "$output/source/"
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
probe_patcher=$(cygpath -am "$script_dir/patch-bash-wexitstatus-probe.py")
"$native_python" -I "$probe_patcher" "$output/source"
loadable_patcher=$(cygpath -am "$script_dir/patch-bash-cygwin-loadables.py")
"$native_python" -I "$loadable_patcher" "$output/source"
export MSYS2_ARG_CONV_EXCL='-DLOCALEDIR=;-DLOCALE_ALIAS_PATH=;-DLIBDIR='
exec > >(tee "$output/build.log") 2>&1
cat > "$output/dlopen-provider.c" <<'EOF'
__declspec(dllexport) int native_dlopen_probe(void)
{
    return 42;
}
EOF
cat > "$output/dlopen-probe.c" <<'EOF'
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
    -o "$output/dlopen-provider.dll" "$output/dlopen-provider.c"
gcc $CPPFLAGS $CFLAGS -static $LDFLAGS \
    -o "$output/dlopen-probe.exe" "$output/dlopen-probe.c"
(cd "$output" && ./dlopen-probe.exe)
export ac_cv_func_dlopen=yes ac_cv_func_dlclose=yes ac_cv_func_dlsym=yes
cd "$output/source"
./configure --build=aarch64-pc-cygwin --host=aarch64-pc-cygwin \
    --prefix=/usr --sysconfdir=/etc --localstatedir=/var --localedir=/usr/share/locale \
    --enable-static-link --enable-readline "--with-installed-readline=$sdk/usr" \
    --enable-nls --enable-multibyte --enable-job-control --without-bash-malloc --with-curses \
    "--with-libintl-prefix=$sdk/usr" "--with-libiconv-prefix=$sdk/usr" \
    bash_cv_dev_stdin=present bash_cv_dev_fd=standard bash_cv_termcap_lib=libncurses
grep -qx 'prefix = /usr' Makefile
grep -qx 'datarootdir = ${prefix}/share' Makefile
grep -qx 'localedir = /usr/share/locale' Makefile
grep -qx '#define WEXITSTATUS_OFFSET 8' config.h
for feature in HAVE_DLOPEN HAVE_DLCLOSE HAVE_DLSYM; do
    sed -i "s@/\\* #undef $feature \\*/@#define $feature 1@" config.h
done
for makefile in examples/loadables/Makefile examples/loadables/Makefile.inc; do
    sed -i "s@^SHOBJ_LIBS =.*@SHOBJ_LIBS = $PWD/libbash.dll.a -lintl -liconv@" "$makefile"
done
for feature in READLINE JOB_CONTROL ENABLE_NLS; do
    grep -qx "#define $feature 1" config.h
done
if grep -q '^#define NO_MULTIBYTE_SUPPORT' config.h; then
    echo "Full Bash may not disable multibyte support" >&2
    exit 3
fi
printf '2\n' > .build
make_args=(HISTORY_LDFLAGS= READLINE_LDFLAGS=
           'LOCAL_LDFLAGS=-Wl,--export-all,--out-implib,libbash.dll.a'
           'LDFLAGS_FOR_BUILD=$(CFLAGS_FOR_BUILD)'
           "SHOBJ_LIBS=$PWD/libbash.dll.a -lintl -liconv")
make -j"$jobs" "${make_args[@]}"
make -j"$jobs" "${make_args[@]}" printenv.exe recho.exe xcase.exe zecho.exe
cp printenv.exe recho.exe xcase.exe zecho.exe tests/
make -j1 "${make_args[@]}" DESTDIR="$output/stage" install
cp "$output/stage/usr/bin/bash.exe" "$output/stage/usr/bin/sh.exe"
sdk_locale=$(cygpath -m "$sdk/usr/share/locale")
while IFS= read -r executable; do
    for forbidden_locale in "$host_locale" "$sdk_locale"; do
        if grep -aFq "$forbidden_locale" "$executable"; then
            echo "Staged executable retains build-only locale prefix: $executable" >&2
            exit 3
        fi
    done
done < <(find "$output/stage" -type f -name '*.exe' -print)
install -Dm644 COPYING "$output/stage/usr/share/licenses/bash/COPYING"
mkdir -p "$output/stage/usr/include/bash" "$output/stage/usr/lib"
cp libbash.dll.a "$output/stage/usr/lib/"
for header in [^y]*.h builtins/*.h include/*.h lib/glob/*.h lib/tilde/*.h; do
    /usr/bin/install -m644 "$header" "$output/stage/usr/include/bash/"
done
cd "$output/stage/usr/share/man/man1"
printf '.so man1/bash.1\n' > sh.1
printf '.so man1/bash_builtins.1.gz\n' > alias.1
gzip alias.1
for name in bg bind break builtin caller case cd command compgen complete continue declare dirs disown \
    do done elif else enable esac eval exec exit export fc fg fi for function getopts hash help history \
    if in jobs let local logout popd pushd read readonly return select set shift shopt source suspend \
    then time times trap type typeset ulimit umask unalias unset until wait while '['; do
    cp -f alias.1.gz "$name.1.gz"
done
