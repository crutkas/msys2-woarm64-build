#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 && ${MSYS-} == winsymlinks:sys ]] || exit 2
cd "$1"
[[ -f regular.c && -f target.h && -f header-control.c && ! -e linked-source.c && ! -e linked-header.h ]] || exit 3
ln -s regular.c linked-source.c
ln -s target.h linked-header.h
[[ -L linked-source.c && -L linked-header.h ]]
[[ $(readlink linked-source.c) == regular.c && $(readlink linked-header.h) == target.h ]]
cmp regular.c linked-source.c
cmp target.h linked-header.h
printf 'CURRENT_MSYS_SOURCE_AND_HEADER_SYMLINKS=PASS\n'
