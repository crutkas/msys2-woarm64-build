#!/bin/bash
set -euo pipefail

: "${LESS_BUILD_ROOT:?Owned output root is required}"
root=$(/usr/bin/cygpath -u "$LESS_BUILD_ROOT")
compiler="$root/compiler/bin"
sdk=$(/usr/bin/cygpath -am "$root/sdk02/usr")
export PATH="$root/runtime/usr/bin:$compiler:/usr/bin:/c/Windows/System32"
export MSYS2_ARG_CONV_EXCL='*'
export CC="$compiler/aarch64-pc-cygwin-gcc.exe"
export AR="$compiler/aarch64-pc-cygwin-ar.exe"
export RANLIB="$compiler/aarch64-pc-cygwin-ranlib.exe"
export CFLAGS="-O2 -g -pipe -fstack-protector-strong -D_FORTIFY_SOURCE=2"
export CPPFLAGS="-I$sdk/include -I$sdk/include/ncursesw"
export LDFLAGS="-L$sdk/lib -Wl,--no-insert-timestamp -Wl,-t"
export LIBS="-lncursesw -lpcre2-8"
export MAKEFLAGS=-j1
export LC_ALL=C.UTF-8
export TERM=xterm-256color
export TERMINFO="$root/sdk02/usr/share/terminfo"

cd "$root/check-source/less-704"
make LESSTEST=1
make -C lesstest
# All fork/exec participants must use one native MSYS installation. Upstream
# lt_screen receives an empty environment, so PATH cannot supply its DLLs.
test_bin="$root/check-runtime/usr/bin"
mkdir -p "$test_bin"
for library in msys-2.0.dll msys-ncursesw6.dll msys-pcre2-8-0.dll; do
  install -m755 "$root/runtime/usr/bin/$library" "$test_bin/$library"
done
install -m755 less.exe "$test_bin/less.exe"
install -m755 lesstest/lesstest.exe "$test_bin/lesstest.exe"
install -m755 lesstest/lt_screen.exe "$test_bin/lt_screen.exe"
# The bootstrap and target runtimes can use different drive mount prefixes.
# Pass the actual fixtures through their common proc-cygdrive namespace.
target=$(/usr/bin/cygpath -U -u "$(/usr/bin/cygpath -am "$PWD")")
target_bin=$(/usr/bin/cygpath -U -u "$(/usr/bin/cygpath -am "$test_bin")")
/usr/bin/perl "$PWD/lesstest/runtest" \
  -d "$target/lesstest" \
  -l "$target_bin/less.exe" \
  -t "$target_bin/lesstest.exe" \
  -s "$target_bin/lt_screen.exe" \
  -r "$target/lesstest/.runtest-native" \
  "$target/lesstest/lt"
