#!/bin/bash

if [[ $# != 1 || $1 != /* || ! -d $1 ]]; then
    printf 'Expected one existing absolute invocation output directory.\n' >&2
    return 2
fi

invocation_root=$(cd -- "$1" && pwd -P)
# libmakepkg preserves these exported values across system/user configuration.
# Bind every destination before makepkg can derive or clean srcdir/pkgdir.
export BUILDDIR="$invocation_root/build"
export SRCDEST="$invocation_root/sources"
export SRCPKGDEST="$invocation_root/source-packages"
export LOGDEST="$invocation_root/logs"
export PKGDEST="$invocation_root/packages"
mkdir -p -- "$BUILDDIR" "$SRCDEST" "$SRCPKGDEST" "$LOGDEST" "$PKGDEST"
unset invocation_root
