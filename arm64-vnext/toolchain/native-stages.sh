#!/usr/bin/env bash
# Windows-hosted tools are built with the separately verified MinGW cross tools.
install_native_licenses() {
  local native=${1:-$ROOT/native} source file
  for source in gcc binutils gmp-6.2.1 mpfr-4.1.0 mpc-1.2.1; do
    mkdir -p "$native/share/licenses/$source"
    for file in "$ROOT/sources/$source"/COPYING*; do
      [[ -f $file ]] || fail "Missing license file: $file"
      install -m 644 "$file" "$native/share/licenses/$source/"
    done
  done
  install -Dm644 "$ROOT/sources/mingw-woarm64/COPYING.MinGW-w64/COPYING.MinGW-w64.txt" \
    "$native/share/licenses/mingw-w64/COPYING.MinGW-w64.txt"
  install -Dm644 "$ROOT/sources/mingw-woarm64/COPYING.MinGW-w64-runtime/COPYING.MinGW-w64-runtime.txt" \
    "$native/share/licenses/mingw-w64/COPYING.MinGW-w64-runtime.txt"
  install -Dm644 "$ROOT/sources/mingw-woarm64/mingw-w64-libraries/winpthreads/COPYING" \
    "$native/share/licenses/winpthreads/COPYING"
  install -Dm644 "$ROOT/sources/gcc/zlib/README" "$native/share/licenses/zlib/README"
}

build_native_stage() {
  local cross=$ROOT/mingw-cross native=$ROOT/native deps=$ROOT/native-deps
  local build version
  build=$("$ROOT/sources/gcc/config.guess")
  version=$("$cross/bin/$TARGET-gcc" -dumpversion)
  [[ $("$cross/bin/$TARGET-gcc" -dumpmachine) == "$TARGET" ]] ||
    fail "Wrong native-tool bootstrap compiler"
  mkdir -p "$native" "$deps"
  case $STAGE in
    native-configure|native-gcc)
      check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
      configure_build "$ROOT/build/native-gcc-refptr" env \
        CC="$cross/bin/$TARGET-gcc" CXX="$cross/bin/$TARGET-g++" \
        CFLAGS="-O2 -std=gnu17 -pthread" CXXFLAGS="-O2 -pthread" LDFLAGS="-static -pthread" \
        CC_FOR_BUILD=gcc CXX_FOR_BUILD=g++ \
        "$ROOT/sources/gcc/configure" \
        --build="$build" --host="$TARGET" --target="$TARGET" --prefix="$native" \
        --with-sysroot="$native/$TARGET" --with-build-sysroot="$cross/$TARGET" \
        --with-native-system-header-dir=/include \
        --with-gmp="$deps" --with-mpfr="$deps" --with-mpc="$deps" --without-isl \
        --enable-languages=c,c++ --with-arch=armv8-a --with-default-msvcrt=ucrt \
        --enable-threads=posix --enable-host-pie \
        --disable-multilib --disable-nls --disable-shared \
        --disable-libssp --disable-libgomp --disable-libatomic --disable-libquadmath \
        --disable-libstdcxx --disable-bootstrap --disable-werror
      if [[ $STAGE == native-gcc ]]; then
        make -j"$JOBS" all-gcc
        make install-gcc
        # Target libraries are identical PE/COFF inputs whether their compiler
        # runs on Linux or Windows; don't replace them with Linux host libraries.
        mkdir -p "$native/$TARGET" "$native/lib/gcc/$TARGET/$version"
        cp -a "$cross/$TARGET/include" "$cross/$TARGET/lib" "$native/$TARGET/"
        mkdir -p "$native/include/c++"
        cp -a "$cross/$TARGET/include/c++/$version" "$native/include/c++/"
        install -m 644 "$cross/lib/gcc/$TARGET/$version/"*.a \
          "$cross/lib/gcc/$TARGET/$version/"*.o \
          "$native/lib/gcc/$TARGET/$version/"
        install -m 644 "$cross/lib/gcc/$TARGET/$version/include/unwind.h" \
          "$cross/lib/gcc/$TARGET/$version/include/gcov.h" \
          "$native/lib/gcc/$TARGET/$version/include/"
        install_native_licenses
      fi
      ;;
    native-binutils)
      check_source binutils 44335833f8f734f978211b082b15aed14efcf958
      configure_build "$ROOT/build/native-binutils-refptr" env \
        CC="$cross/bin/$TARGET-gcc" CXX="$cross/bin/$TARGET-g++" \
        CFLAGS="-O2 -std=gnu17 -pthread" CXXFLAGS="-O2 -pthread" LDFLAGS="-static -pthread" \
        CC_FOR_BUILD=gcc CXX_FOR_BUILD=g++ \
        "$ROOT/sources/binutils/configure" --build="$build" --host="$TARGET" \
        --target="$TARGET" --prefix="$native" --with-sysroot="$native/$TARGET" \
        --disable-nls --disable-werror --disable-gdb --disable-sim \
        --disable-libdecnumber --disable-readline
      make -j"$JOBS"
      make install
      ;;
    native-deps)
      python3 "$RECIPE/source-lock.py" verify --gcc-source "$ROOT/sources/gcc"
      mkdir -p "$ROOT/downloads"
      local archive name checksum
      for archive in gmp-6.2.1.tar.bz2 mpfr-4.1.0.tar.bz2 mpc-1.2.1.tar.gz; do
        name=${archive%.tar.*}
        checksum=$(awk -v name="$archive" '$2 == name {print $1}' \
          "$ROOT/sources/gcc/contrib/prerequisites.sha512")
        [[ $checksum =~ ^[0-9a-f]{128}$ ]] || fail "Missing pinned hash for $archive"
        if [[ ! -f $ROOT/downloads/$archive ]]; then
          curl --fail --location --retry 3 \
            "https://gcc.gnu.org/pub/gcc/infrastructure/$archive" \
            --output "$ROOT/downloads/$archive.partial"
          mv "$ROOT/downloads/$archive.partial" "$ROOT/downloads/$archive"
        fi
        printf '%s  %s\n' "$checksum" "$ROOT/downloads/$archive" | sha512sum -c -
        if [[ ! -d $ROOT/sources/$name ]]; then
          tar -xf "$ROOT/downloads/$archive" -C "$ROOT/sources"
        fi
        local options=(--build="$build" --host="$TARGET" --prefix="$deps"
                       --disable-shared --enable-static)
        case $name in
          gmp-*) options+=(--disable-assembly --enable-cxx) ;;
          mpfr-*) options+=(--with-gmp="$deps") ;;
          mpc-*) options+=(--with-gmp="$deps" --with-mpfr="$deps") ;;
        esac
        configure_build "$ROOT/build/native-refptr-$name" env \
          CC="$cross/bin/$TARGET-gcc" CXX="$cross/bin/$TARGET-g++" \
          CFLAGS="-O2 -std=gnu17 -pthread" CXXFLAGS="-O2 -pthread" LDFLAGS="-static -pthread" \
          CC_FOR_BUILD=gcc CXX_FOR_BUILD=g++ \
          "$ROOT/sources/$name/configure" "${options[@]}"
        make -j"$JOBS"
        make install
      done
      sha512sum "$ROOT/downloads/gmp-6.2.1.tar.bz2" \
        "$ROOT/downloads/mpfr-4.1.0.tar.bz2" "$ROOT/downloads/mpc-1.2.1.tar.gz" |
        tee "$ROOT/identities/native-math-sources.sha512"
      ;;
    *) fail "Unknown native stage: $STAGE" ;;
  esac
}
