#!/bin/bash

validate_woarm64_compression_policy() {
    if [[ -n ${WOARM64_JOBS+x} && ! $WOARM64_JOBS =~ ^([1-9]|1[0-6])$ ]]; then
        printf 'WOARM64_JOBS must be an explicit integer from 1 to 16.\n' >&2
        return 2
    fi
}

bound_woarm64_compression_command() {
    validate_woarm64_compression_policy || return
    [[ -n ${WOARM64_JOBS+x} ]] || return 0
    local _woarm64_kind
    case $1 in
        *.tar.xz) _woarm64_kind=xz ;;
        *.tar.zst) _woarm64_kind=zstd ;;
        *) return 0 ;;
    esac
    local -n _woarm64_command=$2
    local _woarm64_program=${_woarm64_command[0]##*/}
    if [[ $_woarm64_program != "$_woarm64_kind" && $_woarm64_program != "$_woarm64_kind.exe" ]]; then
        printf 'Cannot bound %s compression through an unrecognized command: %s\n' \
            "$_woarm64_kind" "${_woarm64_command[0]}" >&2
        return 2
    fi
    local _woarm64_option _woarm64_value _woarm64_index
    local -a _woarm64_bounded=("${_woarm64_command[0]}")
    if [[ $_woarm64_kind == xz ]]; then
        _woarm64_bounded+=(--threads=1)
    else
        _woarm64_bounded+=(--single-thread)
    fi
    for ((_woarm64_index=1; _woarm64_index<${#_woarm64_command[@]}; _woarm64_index++)); do
        _woarm64_option=${_woarm64_command[_woarm64_index]}
        case $_woarm64_option in
            --)
                _woarm64_bounded+=("${_woarm64_command[@]:_woarm64_index}")
                break
                ;;
            -T|--threads)
                ((_woarm64_index+=1))
                _woarm64_value=${_woarm64_command[_woarm64_index]:-}
                ;;
            -T*) _woarm64_value=${_woarm64_option#-T} ;;
            --threads=*) _woarm64_value=${_woarm64_option#--threads=} ;;
            --single-thread)
                if [[ $_woarm64_kind == zstd ]]; then continue; fi
                _woarm64_bounded+=("$_woarm64_option")
                continue
                ;;
            -*)
                if [[ $_woarm64_option != --* && $_woarm64_option == *T* ]]; then
                    printf 'Use a separate -T argument for bounded compression: %s\n' "$_woarm64_option" >&2
                    return 2
                fi
                _woarm64_bounded+=("$_woarm64_option")
                continue
                ;;
            *)
                _woarm64_bounded+=("$_woarm64_option")
                continue
                ;;
        esac
        if [[ ! $_woarm64_value =~ ^[0-9]+$ ]]; then
            printf 'Invalid configured compressor thread count: %s\n' "$_woarm64_value" >&2
            return 2
        fi
    done
    _woarm64_command=("${_woarm64_bounded[@]}")
    printf 'WOARM64 compression (%s):' "$_woarm64_kind" >&2
    printf ' %q' "${_woarm64_command[@]}" >&2
    printf '\n' >&2
}

install_woarm64_compression_policy() {
    validate_woarm64_compression_policy || return
    [[ -n ${WOARM64_JOBS+x} ]] || return 0
    local library=$1 scripts=$2
    if [[ ! -f "$library/util/compress.sh" || -e "$library/util/woarm64-compress-original" ]]; then
        printf 'Expected a fresh libmakepkg compression library: %s\n' "$library" >&2
        return 2
    fi
    mv -- "$library/util/compress.sh" "$library/util/woarm64-compress-original"
    install -m644 "$scripts/makepkg-compression.sh" "$library/util/compress.sh"
    install -m644 "$scripts/makepkg-compression-policy.sh" "$library/util/woarm64-compress-policy"
}
