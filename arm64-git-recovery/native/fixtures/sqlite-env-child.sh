#!/usr/bin/env bash
printf 'foreign-MSYS-bash inherited=<%s> new=<%s> CCACHE_DISABLE=<%s> TMPDIR=<%s>\n' \
    "${WOARM64_ENV_INHERITED-absent}" "${WOARM64_ENV_NEW-absent}" \
    "${CCACHE_DISABLE-absent}" "${TMPDIR-absent}"
printf 'foreign-MSYS-bash PATH=<%s> MSYSTEM=<%s> SYSTEMROOT-present=%s WINDIR-present=%s\n' \
    "${PATH-absent}" "${MSYSTEM-absent}" "${SYSTEMROOT+yes}" "${WINDIR+yes}"
