#!/bin/bash

source `dirname ${BASH_SOURCE[0]}`/../../config.sh

pacman -S --noconfirm mingw-w64-cross-mingw64-winpthreads

for HEADER in \
  pthread_compat.h \
  pthread_signal.h \
  pthread_unistd.h \
  pthread_time.h
do
  install -m 644 \
    "/opt/x86_64-w64-mingw32/include/$HEADER" \
    "/opt/aarch64-w64-mingw32/include/$HEADER"
done
