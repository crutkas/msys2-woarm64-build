#!/bin/bash

[[ -n ${LIBMAKEPKG_WOARM64_COMPRESS_SH:-} ]] && return
LIBMAKEPKG_WOARM64_COMPRESS_SH=1
source "$MAKEPKG_LIBRARY/util/woarm64-compress-original"
source "$MAKEPKG_LIBRARY/util/woarm64-compress-policy"

# Keep pacman's extension handling and configured compression options.
_woarm64_compression_original=$(declare -f get_compression_command)
eval "${_woarm64_compression_original/get_compression_command/woarm64_original_get_compression_command}"
unset _woarm64_compression_original

get_compression_command() {
    woarm64_original_get_compression_command "$@" || return $?
    # Returning false means "unknown format" to pacman, which would emit plain
    # tar. Invalid resource policy must instead fail the archive pipeline.
    bound_woarm64_compression_command "$@" || exit 2
}
