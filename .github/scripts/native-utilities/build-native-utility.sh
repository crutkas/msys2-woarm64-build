#!/bin/bash
set -euo pipefail

: "${NATIVE_UTILITY_ROOT:?A new owned output root is required}"
package=${1:?Specify which or dos2unix}
case "$package" in
  which|dos2unix) ;;
  *) printf 'Unsupported package: %s\n' "$package" >&2; exit 2 ;;
esac
root=$(/usr/bin/cygpath -u "$NATIVE_UTILITY_ROOT")
compiler="$root/compiler/bin"
sdk=$(/usr/bin/cygpath -am "$root/sdk/usr")
export PATH="$compiler:/usr/bin:/usr/bin/core_perl:/usr/bin/vendor_perl:/c/Windows/System32"
export MSYS2_ARG_CONV_EXCL='*'
export CHOST=aarch64-pc-cygwin
export CC="$compiler/aarch64-pc-cygwin-gcc.exe"
export AR="$compiler/aarch64-pc-cygwin-ar.exe"
export RANLIB="$compiler/aarch64-pc-cygwin-ranlib.exe"
export STRIP="$compiler/aarch64-pc-cygwin-strip.exe"
export CFLAGS="-O2 -g -pipe -fstack-protector-strong -D_FORTIFY_SOURCE=2"
export CPPFLAGS="-I$sdk/include"
export LDFLAGS="-L$sdk/lib -Wl,--no-insert-timestamp -Wl,-t"
export MAKEFLAGS=-j1 LC_ALL=C.UTF-8 SOURCE_DATE_EPOCH=1788825600
export srcdir="$root/$package/src" pkgdir="$root/$package/stage"

source "$root/$package/recipe/PKGBUILD"
[[ $pkgname == "$package" && ${arch[*]} == aarch64 ]]
if [[ $pkgname == dos2unix ]]; then
  # Its MSYS branch assigns CC=gcc and replaces LDFLAGS. Preserve that branch's
  # feature defaults while passing the actual qualified target and SDK wiring.
  make() {
    command make CC="$CC" CPP="$CC -E" LDFLAGS_USER="$LDFLAGS" "$@"
  }
fi
"$CC" -dumpmachine
prepare
build
if [[ $pkgname == dos2unix ]]; then
  for library in msys-2.0.dll msys-intl-8.dll msys-iconv-2.dll; do
    install -m755 "$root/sdk/usr/bin/$library" "$srcdir/dos2unix-$pkgver/$library"
  done
fi
package
if [[ $pkgname == which ]]; then
  install -Dm644 "$srcdir/which-$pkgver/COPYING" "$pkgdir/usr/share/licenses/which/COPYING"
fi
printf 'NATIVE_%s_ORIGINAL_RECIPE_BUILD_INSTALL_COMPLETE\n' "$pkgname"
