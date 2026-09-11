#!/usr/bin/env bash
set -euo pipefail

[[ $# == 7 ]] || exit 2
makepkg_library=$1
native_find=$2
startdir=$3
pkgdest=$4
target_bin=$5
host_usr_bin=$6
mingw_arch=$7

[[ $mingw_arch == mingwarm64 ]]
[[ -f $startdir/PKGBUILD && -d $startdir/src ]]
[[ -x $host_usr_bin/makepkg-mingw ]]
[[ $(sha256sum "$makepkg_library/tidy/zipman.sh") == \
    833957cd5e4c90642b3a3fb0b3c5e2278ff09746d4d265c1c443525d848faa4a* ]]
[[ $(sha256sum "$makepkg_library/util/dirsize.sh") == \
    acb6816b6d9eeb28f0f08c5fd469e822d08b0d7d9ab93c4855a432950e09e24f* ]]
[[ $(sha256sum "$native_find") == \
    6fc041358ebe027f8eca51cce88fb3479f4fa75e17c94e865d563864d8a1feb9* ]]
[[ $(sha256sum "$(dirname "$native_find")/msys-2.0.dll") == \
    d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d* ]]

find()
{
    "$native_find" "$@"
}
export -f find
export native_find
export MAKEPKG_LIBRARY="$makepkg_library"
export PATH="$target_bin:$host_usr_bin"
export MINGW_ARCH="$mingw_arch"
export PKGDEST="$pkgdest"

mkdir -p "$pkgdest"
cd "$startdir"
exec "$host_usr_bin/makepkg-mingw" --repackage --nodeps --noconfirm
