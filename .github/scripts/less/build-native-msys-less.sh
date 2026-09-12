#!/bin/bash
set -euo pipefail

: "${LESS_BUILD_ROOT:?Owned output root is required}"
root=$(/usr/bin/cygpath -u "$LESS_BUILD_ROOT")
compiler="$root/compiler/bin"
sdk=$(/usr/bin/cygpath -am "$root/sdk02/usr")

export PATH="$compiler:/usr/bin:/c/Windows/System32"
export MSYS2_ARG_CONV_EXCL='*'
export CC="$compiler/aarch64-pc-cygwin-gcc.exe"
export AR="$compiler/aarch64-pc-cygwin-ar.exe"
export AS="$compiler/aarch64-pc-cygwin-as.exe"
export LD="$compiler/aarch64-pc-cygwin-ld.exe"
export RANLIB="$compiler/aarch64-pc-cygwin-ranlib.exe"
export STRIP="$compiler/aarch64-pc-cygwin-strip.exe"
export OBJDUMP="$compiler/aarch64-pc-cygwin-objdump.exe"
export CFLAGS="-O2 -g -pipe -fstack-protector-strong -D_FORTIFY_SOURCE=2"
export CPPFLAGS="-I$sdk/include -I$sdk/include/ncursesw"
export LDFLAGS="-L$sdk/lib -Wl,--no-insert-timestamp -Wl,-t"
export MAKEFLAGS=-j1
export LC_ALL=C.UTF-8
export CHOST=aarch64-pc-cygwin
export srcdir="$root/src"
export pkgdir="$root/stage"
export SOURCE_DATE_EPOCH=1788825600

source "$root/recipe/PKGBUILD"
[[ $pkgname == less && $pkgver == 704 && $pkgrel == 1 && ${arch[*]} == aarch64 ]]
printf 'Target compiler: %s\n' "$CC"
"$CC" -dumpmachine
printf '%s\n' 'Original pinned recipe prepare()'
prepare
printf '%s\n' 'Original pinned recipe build()'
build
printf '%s\n' 'Original pinned recipe package()'
package
install -Dm644 "$srcdir/less-704/COPYING" "$pkgdir/usr/share/licenses/less/COPYING"
install -Dm644 "$srcdir/less-704/LICENSE" "$pkgdir/usr/share/licenses/less/LICENSE"
printf '%s\n' 'LESS_REGULAR_BUILD_AND_INSTALL_COMPLETE'
