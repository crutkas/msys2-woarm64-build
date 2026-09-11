#!/usr/bin/env bash
set -euo pipefail

[[ $# == 2 ]] || exit 2
makepkg_library=$1
native_find=$2

[[ $(sha256sum "$makepkg_library/tidy/zipman.sh") == \
    833957cd5e4c90642b3a3fb0b3c5e2278ff09746d4d265c1c443525d848faa4a* ]]
[[ $(sha256sum "$makepkg_library/util/dirsize.sh") == \
    acb6816b6d9eeb28f0f08c5fd469e822d08b0d7d9ab93c4855a432950e09e24f* ]]
[[ $(sha256sum "$native_find") == \
    6fc041358ebe027f8eca51cce88fb3479f4fa75e17c94e865d563864d8a1feb9* ]]

find()
{
    "$native_find" "$@"
}
export -f find
export native_find
export MAKEPKG_LIBRARY="$makepkg_library"

fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT

mkdir "$fixture/size" "$fixture/zipman" "$fixture/zipman/man"
printf abc > "$fixture/size/a"
printf 12345 > "$fixture/size/b"
ln "$fixture/size/b" "$fixture/size/b-link"

LIBMAKEPKG_UTIL_DIRSIZE_SH=
set +u
source "$makepkg_library/util/dirsize.sh"
set -u
(
    cd "$fixture/size"
    [[ $(dirsize) == 8 ]]
)

printf 'manual text' > "$fixture/zipman/man/one.1"
ln "$fixture/zipman/man/one.1" "$fixture/zipman/man/alias.1"
LIBMAKEPKG_TIDY_ZIPMAN_SH=
set +u
source "$makepkg_library/tidy/zipman.sh"
set -u
check_option()
{
    return 0
}
msg2()
{
    :
}
MAN_DIRS=(man)
(
    cd "$fixture/zipman"
    set +u
    tidy_zipman
    set -u
    [[ -f man/one.1.gz && -f man/alias.1.gz ]]
    [[ ! -e man/one.1 && ! -e man/alias.1 ]]
    [[ man/one.1.gz -ef man/alias.1.gz ]]
)
