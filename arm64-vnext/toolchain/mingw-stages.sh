#!/usr/bin/env bash
# Sourced by bootstrap-cygwin.sh; reuse its source guards, logging and lock.
build_mingw_runtime() {
  check_source mingw-woarm64 70d63e7c9a477b8b275a9782b289fbf1614b6e9e
  local source=$ROOT/sources/mingw-woarm64
  local build
  build=$("$ROOT/sources/gcc/config.guess")
  if [[ $STAGE != mingw-headers ]]; then
    [[ $("$PREFIX/bin/$TARGET-gcc" -dumpmachine) == "$TARGET" ]] ||
      fail "Wrong MinGW bootstrap compiler"
  fi
  case $STAGE in
    mingw-headers)
      configure_build "$ROOT/build/mingw-headers" \
        "$source/mingw-w64-headers/configure" --host="$TARGET" \
        --prefix="$SYSROOT" --enable-sdk=all --with-default-msvcrt=ucrt
      make install
      # The CRT includes these compatibility headers before winpthreads can
      # link. Use the same pinned source, never an unrelated x64 installation.
      install -m 644 "$source/mingw-w64-libraries/winpthreads/include/"*.h \
        "$SYSROOT/include/"
      ;;
    mingw-crt)
      configure_build "$ROOT/build/mingw-crt-refptr-final" env \
        CC="$PREFIX/bin/$TARGET-gcc" CXX="$PREFIX/bin/$TARGET-g++" \
        "$source/mingw-w64-crt/configure" --build="$build" --host="$TARGET" \
        --prefix="$SYSROOT" --with-default-msvcrt=ucrt \
        --enable-libarm64 --disable-lib32 --disable-lib64 --disable-libarm32
      make -j"$JOBS"
      make install
      ;;
    mingw-libraries)
      check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
      cd "$ROOT/build/mingw-gcc-msabi"
      make -j"$JOBS" all-target-libgcc
      make install-target-libgcc
      configure_build "$ROOT/build/mingw-winpthreads-refptr-final" env \
        CC="$PREFIX/bin/$TARGET-gcc" \
        "$source/mingw-w64-libraries/winpthreads/configure" \
        --build="$build" --host="$TARGET" --prefix="$SYSROOT" \
        --disable-shared --enable-static
      make -j"$JOBS"
      make install
      local version
      version=$("$PREFIX/bin/$TARGET-gcc" -dumpversion)
      configure_build "$ROOT/build/mingw-libstdcxx-refptr-final" env \
        CC="$PREFIX/bin/$TARGET-gcc" CXX="$PREFIX/bin/$TARGET-g++" \
        CPPFLAGS="-I$ROOT/build/mingw-gcc-msabi/$TARGET/libgcc" \
        CFLAGS="-g -O2 -pthread" CXXFLAGS="-g -O2 -pthread" \
        "$ROOT/sources/gcc/libstdc++-v3/configure" \
        --build="$build" --host="$TARGET" --with-target-subdir="$TARGET" \
        --with-cross-host="$build" --prefix="$PREFIX" \
        --with-gxx-include-dir="$SYSROOT/include/c++/$version" \
        --disable-multilib --disable-shared --enable-static --enable-threads=posix \
        --disable-nls --disable-libstdcxx-pch --disable-symvers
      grep -q '^#define _GLIBCXX_HAS_GTHREADS 1$' config.h ||
        fail "POSIX C++ thread support was not detected"
      make -j"$JOBS"
      make install
      ;;
    *) fail "Unknown MinGW runtime stage: $STAGE" ;;
  esac
}
