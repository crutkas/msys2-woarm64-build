#!/usr/bin/env bash
set -euo pipefail
[[ $# == 6 ]] || { echo "usage: $0 SOURCE RECIPE_ROOT NATIVE_TOOLCHAIN DEPENDENCIES OUTPUT JOBS" >&2; exit 2; }
source_root=$(cygpath -u "$1") recipe_root=$(cygpath -u "$2") toolchain=$(cygpath -u "$3")
dependencies=$(cygpath -u "$4") output=$(cygpath -u "$5") jobs=$6
[[ $jobs =~ ^[1-8]$ && ! -e $output ]] || { echo "Explicit jobs and new output required" >&2; exit 2; }
for header in zlib.h expat.h pcre2.h curl/curl.h openssl/ssl.h iconv.h libintl.h; do
    [[ -s "$dependencies/include/$header" ]] || { echo "Missing Git build dependency: $header" >&2; exit 3; }
done
[[ -s "$dependencies/bin/libcurl-4.dll" ]] || { echo "Git lazy loading requires the actual libcurl-4.dll" >&2; exit 3; }
export PATH="$toolchain/bin:$dependencies/bin:/usr/bin"
export MSYSTEM=CLANGARM64 MINGW_CHOST=aarch64-w64-mingw32 MINGW_PREFIX=/clangarm64
unset CC CXX CPP CFLAGS CXXFLAGS CPPFLAGS LDFLAGS GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export CC=gcc CXX=g++ AR=ar RANLIB=ranlib LC_ALL=C
[[ $(gcc -dumpmachine) == aarch64-w64-mingw32 ]] || { echo "Wrong compiler target" >&2; exit 3; }
mkdir -p "$output"
cp -a "$source_root" "$output/git"
cp -a "$recipe_root/mingw-w64-git/." "$output/"
mkdir -p "$output/temp" "$output/stage" "$output/home"
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export HOME="$output/home" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
export PKG_CONFIG_PATH="$dependencies/lib/pkgconfig"
cd "$output/git"
exec > >(tee "$output/build.log") 2>&1
dep_native=$(cygpath -m "$dependencies")
cat > config.mak <<EOF
CC = gcc
AR = ar
RC = windres -O coff
prefix = /clangarm64
NO_RUST = YesPlease
NO_INSTALL_HARDLINKS = YesPlease
USE_LIBPCRE2 = YesPlease
DEFAULT_EDITOR = nano
PERL_PATH = /usr/bin/perl
SHELL_PATH = /bin/sh
TCLTK_PATH = /usr/bin/wish
ZLIB_PATH = $dep_native
EXPATDIR = $dep_native
LIBPCREDIR = $dep_native
ICONVDIR = $dep_native
CURLDIR = $dep_native
OPENSSLDIR = $dep_native
BASIC_CFLAGS += -I$dep_native/include
BASIC_LDFLAGS += -L$dep_native/lib -L$dep_native/lib-arm64
EOF
cp ../git-bash.adoc Documentation/
make -j"$jobs" -f ../mingw-w64-git.mak uname_S=MINGW \
    git-wrapper.exe git-bash.exe git-cmd.exe compat-bash.exe \
    cmd/git.exe cmd/gitk.exe cmd/git-gui.exe cmd/git-receive-pack.exe cmd/git-upload-pack.exe \
    cmd/tig.exe edit-git-bash.exe
make -j"$jobs" uname_S=MINGW all
make -j1 -f ../mingw-w64-git.mak uname_S=MINGW print-builtins | tr ' ' '\n' > "$output/builtins.txt"
make -j1 uname_S=MINGW DESTDIR="$output/stage" install
make -C contrib/credential/wincred CC=gcc LDLIBS=-ladvapi32
make -C contrib/credential/wincred gitexecdir=/clangarm64/libexec/git-core DESTDIR="$output/stage" install
make -C contrib/subtree prefix=/clangarm64 DESTDIR="$output/stage" install
mkdir -p "$output/stage/cmd" "$output/stage/bin" "$output/stage/clangarm64/share/git"
cp git-bash.exe git-cmd.exe "$output/stage/"
cp cmd/*.exe "$output/stage/cmd/"
cp ../start-ssh-agent.cmd ../start-ssh-pageant.cmd "$output/stage/cmd/"
cp cmd/git.exe "$output/stage/cmd/scalar.exe"
cp compat-bash.exe "$output/stage/bin/bash.exe"
cp compat-bash.exe "$output/stage/bin/sh.exe"
cp cmd/git.exe "$output/stage/bin/git.exe"
cp compat-bash.exe git-wrapper.exe edit-git-bash.exe ../git-for-windows.ico "$output/stage/clangarm64/share/git/"
cp "$output/builtins.txt" "$output/stage/clangarm64/share/git/builtins.txt"
mkdir -p "$output/stage/clangarm64/share/licenses/git"
cp COPYING "$output/stage/clangarm64/share/licenses/git/COPYING"
printf '%s\n' 'status=native-Git-built-not-accepted' \
    'orchestration=windows-x64-emulated-msys' \
    'Native POSIX runtime, Tcl/Tk, helpers, dependencies and behavior gates remain mandatory.' > "$output/BUILD-STATUS.txt"
