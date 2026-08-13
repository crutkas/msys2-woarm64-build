#!/bin/bash

source `dirname ${BASH_SOURCE[0]}`/../../config.sh

pacman -R --noconfirm mingw-w64-cross-mingw64-winpthreads || true

rm -f \
  /opt/aarch64-w64-mingw32/include/pthread_compat.h \
  /opt/aarch64-w64-mingw32/include/pthread_signal.h \
  /opt/aarch64-w64-mingw32/include/pthread_unistd.h \
  /opt/aarch64-w64-mingw32/include/pthread_time.h
