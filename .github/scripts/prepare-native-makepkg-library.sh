#!/usr/bin/env bash
set -euo pipefail

[[ $# == 2 ]] || exit 2
source_library=$1
output_library=$2
script_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
patch_file="$script_dir/makepkg-6.1-gnu-find-metadata.patch"

[[ -d $source_library ]]
[[ ! -e $output_library ]]
[[ $(sha256sum "$patch_file") == \
    20f2221e3faeb98a00b9cb1d274d613b2c1ce695bfe6dd916daec2cb834d9c52* ]]
[[ $(sha256sum "$source_library/tidy/zipman.sh") == \
    fdcd3c6742acae0213b3dfdb11c38cf3676bdb9a7b14937c252c7c1121990fd1* ]]
[[ $(sha256sum "$source_library/util/dirsize.sh") == \
    12a0a5247a485a0b4c0a80c3dae56fd6d79ed643c46f9a45f6326a445ab7e7e3* ]]

cp -a -- "$source_library" "$output_library"
(
    cd "$output_library"
    patch --fuzz=0 -p1 < "$patch_file"
)

[[ $(sha256sum "$output_library/tidy/zipman.sh") == \
    833957cd5e4c90642b3a3fb0b3c5e2278ff09746d4d265c1c443525d848faa4a* ]]
[[ $(sha256sum "$output_library/util/dirsize.sh") == \
    acb6816b6d9eeb28f0f08c5fd469e822d08b0d7d9ab93c4855a432950e09e24f* ]]
bash -n "$output_library/tidy/zipman.sh" "$output_library/util/dirsize.sh"
