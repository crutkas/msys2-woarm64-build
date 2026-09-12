#!/bin/bash

source "$(dirname -- "${BASH_SOURCE[0]}")/../../config.sh"
SCRIPTS_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ "$FLAVOR" == NATIVE_WITH_NATIVE ]]; then
  CC=aarch64-w64-mingw32-gcc CXX=aarch64-w64-mingw32-g++ \
    bash "$SCRIPTS_DIR/assert-native-toolchain.sh"
fi

# Sanity check of the GCC binary and its version.
aarch64-w64-mingw32-gcc --version

# Create a simple "Hello, World!" program binary.
echo '#include <stdio.h>
int main() {
  printf("Hello, World!\n");
  return 0;
}
' > hello-world.c
aarch64-w64-mingw32-gcc -o hello-world.exe hello-world.c
powershell.exe -NoProfile -NonInteractive -File \
  "$(cygpath -w "$SCRIPTS_DIR/assert-arm64-pe.ps1")" -Path "$(cygpath -w "$PWD/hello-world.exe")"
