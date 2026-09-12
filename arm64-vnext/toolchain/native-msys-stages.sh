#!/usr/bin/env bash
# Canadian build: Linux build tools, Windows/UCRT host, MSYS application target.
build_native_msys_stage() {
  [[ $JOBS -le 4 ]] || fail "Native MSYS lane currently owns at most four jobs"
  local accepted=${ACCEPTED_CACHE_EPOCH:?Set ACCEPTED_CACHE_EPOCH to the frozen cache epoch}
  local epoch=${NATIVE_MSYS_EPOCH:-$ROOT/epochs/native-msys-20260905}
  local host=aarch64-w64-mingw32 target=aarch64-pc-cygwin
  local host_cross=$accepted/mingw-cross target_cross=$accepted/cygwin-cross
  local native=$epoch/prefix deps=$ROOT/native-deps build
  [[ $epoch == "$ROOT/epochs/"* && $epoch != "$ROOT/epochs/" && $epoch != *..* ]] ||
    fail "NATIVE_MSYS_EPOCH must be a dedicated child of ROOT/epochs"
  [[ -x $host_cross/bin/$host-gcc && -x $target_cross/bin/msys2-gcc ]] ||
    fail "Both accepted host and target cross compilers are required"
  build=$("$ROOT/sources/gcc/config.guess")
  export PATH="$host_cross/bin:$target_cross/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  mkdir -p "$epoch/build" "$epoch/identities" "$native"
  [[ ! -e $epoch/READY ]] || fail "This native MSYS epoch is already frozen"
  cp "$RECIPE/source-lock.json" "$epoch/identities/"
  {
    printf 'build=%s\nhost=%s\ntarget=%s\naccepted=%s\n' "$build" "$host" "$target" "$accepted"
    sha256sum "$host_cross/bin/$host-gcc" "$host_cross/bin/$host-g++" \
      "$target_cross/bin/$target-gcc" "$target_cross/bin/$target-g++"
  } > "$epoch/identities/compiler-inputs.txt"
  printf 'NATIVE_MSYS_EPOCH=%s HOST=%s TARGET=%s\n' "$epoch" "$host" "$target"
  case $STAGE in
    native-msys-posix-cross)
      check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
      local helper=$epoch/posix-cross version
      configure_build "$epoch/build/posix-cross-gcc" "$ROOT/sources/gcc/configure" \
        --build="$build" --host="$build" --target="$target" --prefix="$helper" \
        --with-sysroot="$target_cross/$target" --with-native-system-header-dir=/include \
        --with-as="$target_cross/bin/$target-as" --with-ld="$target_cross/bin/$target-ld" \
        --with-headers=yes --with-newlib --enable-languages=c,c++ --enable-threads=posix \
        --disable-multilib --disable-nls --disable-shared \
        --disable-libssp --disable-libgomp --disable-libatomic --disable-libquadmath \
        --disable-libstdcxx --disable-bootstrap --disable-werror
      make -j"$JOBS" all-gcc
      make install-gcc
      "$helper/bin/$target-g++" -v > "$epoch/identities/posix-cross-version.txt" 2>&1
      grep -q '^Thread model: posix$' "$epoch/identities/posix-cross-version.txt" ||
        fail "The target-library bootstrap compiler is not POSIX-threaded"
      version=$("$helper/bin/$target-gcc" -dumpversion)
      python3 "$RECIPE/generate-msys-specs.py" --compiler "$helper/bin/$target-gcc" \
        --output "$helper/lib/gcc/$target/$version/msys2.specs" \
        --manifest "$epoch/identities/posix-cross-specs.json"
      install -m 755 "$RECIPE/msys2-driver.sh" "$helper/bin/msys2-gcc"
      install -m 755 "$RECIPE/msys2-driver.sh" "$helper/bin/msys2-g++"
      ;;
    native-msys-configure|native-msys-gcc)
      check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
      configure_build "$epoch/build/gcc" env \
        CC="$host_cross/bin/$host-gcc" CXX="$host_cross/bin/$host-g++" \
        CFLAGS="-O2 -std=gnu17 -pthread" CXXFLAGS="-O2 -pthread" LDFLAGS="-static -pthread" \
        CC_FOR_BUILD=gcc CXX_FOR_BUILD=g++ \
        CC_FOR_TARGET="$target_cross/bin/msys2-gcc" \
        GCC_FOR_TARGET="$target_cross/bin/msys2-gcc" \
        CXX_FOR_TARGET="$target_cross/bin/msys2-g++" \
        AR_FOR_TARGET="$target_cross/bin/$target-ar" \
        AS_FOR_TARGET="$target_cross/bin/$target-as" \
        LD_FOR_TARGET="$target_cross/bin/$target-ld" \
        RANLIB_FOR_TARGET="$target_cross/bin/$target-ranlib" \
        "$ROOT/sources/gcc/configure" \
        --build="$build" --host="$host" --target="$target" --prefix="$native" \
        --with-sysroot="$native/$target" --with-build-sysroot="$target_cross/$target" \
        --with-native-system-header-dir=/include --with-headers=yes --with-newlib \
        --with-gmp="$deps" --with-mpfr="$deps" --with-mpc="$deps" --without-isl \
        --enable-languages=c,c++ --enable-threads=posix --enable-host-pie \
        --disable-multilib --disable-nls --disable-shared \
        --disable-libssp --disable-libgomp --disable-libatomic --disable-libquadmath \
        --disable-libstdcxx --disable-bootstrap --disable-werror
      if [[ $STAGE == native-msys-configure ]]; then
        make -j"$JOBS" configure-gcc
      else
        make -j"$JOBS" all-gcc
        make install-gcc
      fi
      ;;
    native-msys-binutils)
      check_source binutils 44335833f8f734f978211b082b15aed14efcf958
      configure_build "$epoch/build/binutils" env \
        CC="$host_cross/bin/$host-gcc" CXX="$host_cross/bin/$host-g++" \
        CFLAGS="-O2 -std=gnu17 -pthread" CXXFLAGS="-O2 -pthread" LDFLAGS="-static -pthread" \
        CC_FOR_BUILD=gcc CXX_FOR_BUILD=g++ \
        "$ROOT/sources/binutils/configure" \
        --build="$build" --host="$host" --target="$target" \
        --prefix="$native" --with-sysroot="$native/$target" \
        --disable-nls --disable-werror --disable-gdb --disable-sim \
        --disable-libdecnumber --disable-readline
      make -j"$JOBS"
      make install
      ;;
    native-msys-runtime)
      check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
      local runtime_sysroot=${RUNTIME_SYSROOT:-$target_cross/$target}
      local runtime_dll=${RUNTIME_DLL:-$target_cross/bin/msys-2.0.dll}
      local version helper=$epoch/posix-cross library_build=$epoch/build/gcc/$target/libgcc
      version=$("$target_cross/bin/$target-gcc" -dumpversion)
      [[ -s $runtime_sysroot/include/pthread.h && -s $runtime_sysroot/include/stdio.h &&
         -s $runtime_sysroot/lib/crt0.o && -s $runtime_sysroot/lib/libmsys-2.0.a &&
         -s $runtime_dll ]] || fail "Incomplete runtime receipt/sysroot"
      [[ -f $epoch/build/gcc/gcc/Makefile ]] || fail "Configure native MSYS GCC first"
      if [[ ! -e $epoch/identities/runtime-inputs.sha256 ]]; then
        mkdir -p "$native/$target" "$native/bin"
        # Never copy a cross sysroot's bin directory: it contains Linux tools.
        cp -a "$runtime_sysroot/include" "$runtime_sysroot/lib" "$native/$target/"
        cp "$runtime_dll" "$native/bin/msys-2.0.dll"
        (
          cd "$runtime_sysroot"
          find include lib -type f -print0 | sort -z | xargs -0 sha256sum
        ) > "$epoch/identities/runtime-inputs.sha256"
        sha256sum "$runtime_dll" > "$epoch/identities/runtime-dll.sha256"
        printf '%s\n' "$runtime_sysroot" > "$epoch/identities/runtime-sysroot.txt"
        printf '%s\n' "$runtime_dll" > "$epoch/identities/runtime-dll-path.txt"
      fi
      [[ $(cat "$epoch/identities/runtime-sysroot.txt") == "$runtime_sysroot" ]] ||
        fail "Runtime input changed: preserve this epoch and choose a new one"
      [[ $(cat "$epoch/identities/runtime-dll-path.txt") == "$runtime_dll" ]] ||
        fail "Runtime DLL input changed: preserve this epoch and choose a new one"
      (cd "$runtime_sysroot"; sha256sum --quiet -c "$epoch/identities/runtime-inputs.sha256")
      sha256sum -c "$epoch/identities/runtime-dll.sha256"
      [[ -x $helper/bin/msys2-gcc ]] || fail "Build the matching POSIX cross helper first"
      if [[ -f $library_build/Makefile ]] &&
          grep -q '^thread_header = gthr-single.h$' "$library_build/Makefile"; then
        [[ ! -e $library_build-single-thread ]] || fail "Preserving the earlier single-thread build"
        mv "$library_build" "$library_build-single-thread"
      fi
      make -C "$epoch/build/gcc" -j"$JOBS" \
        "CC_FOR_TARGET=$helper/bin/msys2-gcc -B$target_cross/lib/gcc/$target/$version/" \
        "GCC_FOR_TARGET=$helper/bin/msys2-gcc -B$target_cross/lib/gcc/$target/$version/" \
        "CXX_FOR_TARGET=$helper/bin/msys2-g++ -B$target_cross/lib/gcc/$target/$version/" \
        "SYSROOT_CFLAGS_FOR_TARGET=--sysroot=$native/$target" all-target-libgcc
      grep -q '^thread_header = gthr-posix.h$' "$library_build/Makefile" ||
        fail "Target libgcc did not select POSIX gthreads"
      make -C "$epoch/build/gcc" \
        "CC_FOR_TARGET=$helper/bin/msys2-gcc -B$target_cross/lib/gcc/$target/$version/" \
        "GCC_FOR_TARGET=$helper/bin/msys2-gcc -B$target_cross/lib/gcc/$target/$version/" \
        "CXX_FOR_TARGET=$helper/bin/msys2-g++ -B$target_cross/lib/gcc/$target/$version/" \
        "SYSROOT_CFLAGS_FOR_TARGET=--sysroot=$native/$target" install-target-libgcc
      [[ -s $native/lib/gcc/$target/$version/libgcc.a ]] || fail "Target libgcc installation missing"
      ;;
    native-msys-libstdcxx)
      check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
      local version helper=$epoch/posix-cross
      version=$("$target_cross/bin/$target-gcc" -dumpversion)
      [[ -s $native/lib/gcc/$target/$version/libgcc.a ]] || fail "Build the POSIX target libgcc first"
      [[ -x $helper/bin/msys2-g++ ]] || fail "Build the matching POSIX cross helper first"
      configure_build "$epoch/build/libstdcxx-posix" env \
        CC="$helper/bin/msys2-gcc --sysroot=$native/$target -B$native/lib/gcc/$target/$version/" \
        CXX="$helper/bin/msys2-g++ --sysroot=$native/$target -B$native/lib/gcc/$target/$version/" \
        CPPFLAGS="-I$epoch/build/gcc/$target/libgcc" \
        CFLAGS="-g -O2 -pthread" CXXFLAGS="-g -O2 -pthread" \
        "$ROOT/sources/gcc/libstdc++-v3/configure" \
        --build="$build" --host="$target" --with-target-subdir="$target" \
        --with-cross-host="$build" --prefix="$native" \
        --with-gxx-include-dir="$native/$target/include/c++/$version" \
        --disable-multilib --disable-shared --enable-static --enable-libstdcxx-threads \
        --disable-nls --disable-libstdcxx-pch --disable-symvers
      grep -q '^#define _GLIBCXX_HAS_GTHREADS 1$' config.h ||
        fail "MSYS hosted C++ did not detect POSIX threads"
      make -j"$JOBS"
      make install
      ;;
    native-msys-finalize)
      local program file
      for program in gcc g++ cpp as ld ar ranlib dlltool nm objcopy objdump size strings strip windres; do
        [[ -s $native/bin/$target-$program.exe ]] || fail "Missing native program: $program"
      done
      for file in "$native/bin/$target-"*.exe; do
        program=${file##*/}
        program=${program#"$target-"}
        if [[ -e $native/bin/$program ]]; then
          cmp "$file" "$native/bin/$program" ||
            fail "Preserving unexpected generic tool alias: $program"
        else
          cp "$file" "$native/bin/$program"
        fi
      done
      for program in cc c++; do
        file=$native/bin/gcc.exe
        [[ $program != c++ ]] || file=$native/bin/g++.exe
        if [[ -e $native/bin/$program.exe ]]; then
          cmp "$file" "$native/bin/$program.exe" ||
            fail "Preserving unexpected generic tool alias: $program"
        else
          cp "$file" "$native/bin/$program.exe"
        fi
      done
      source "$RECIPE/native-stages.sh"
      install_native_licenses "$native"
      mkdir -p "$native/share/toolchain"
      cp "$RECIPE/source-lock.json" "$native/share/toolchain/"
      cp -a "$epoch/identities" "$native/share/toolchain/"
      printf 'NATIVE_MSYS_STAGED=%s (Windows default specs and native acceptance still required)\n' "$native"
      ;;
    *) fail "Unknown native MSYS stage: $STAGE" ;;
  esac
}
