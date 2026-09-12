#!/usr/bin/env bash
# Run with the new private d70 native MSYS shell, never an x64 Git shell.
set -euo pipefail
root=$1
stage=$2
jobs=${3:-2}
[[ $jobs =~ ^[12]$ ]] || { echo "Current allocation is at most two jobs" >&2; exit 2; }
cd "$root"
root=$(pwd)
export PATH="$root/bootstrap/usr/bin:$root/sdk/bin:/c/Windows/System32"
export CONFIG_SHELL="$root/bootstrap/usr/bin/bash.exe"
export SHELL="$CONFIG_SHELL"
export LC_ALL=C
# The genuine MSYS2 GCC recipe uses this policy: libtool's historical
# file-magic predicate accepts only x86 and rejects MSYS compatibility archives.
export lt_cv_deplibs_check_method=pass_all
export TMPDIR="$root/tmp" TMP="$root/tmp" TEMP="$root/tmp"
unset MSYS2_ARG_CONV_EXCL MSYS2_ENV_CONV_EXCL CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH
export CC="$root/sdk/bin/gcc.exe" CXX="$root/sdk/bin/g++.exe"
export AR="$root/sdk/bin/ar.exe" RANLIB="$root/sdk/bin/ranlib.exe" NM="$root/sdk/bin/nm.exe"
export AS="$root/sdk/aarch64-pc-cygwin/bin/as.exe" LD="$root/sdk/aarch64-pc-cygwin/bin/ld.exe"
target=aarch64-pc-cygwin
[[ $("$CC" -dumpmachine) == "$target" ]] || { echo "Wrong target" >&2; exit 1; }
printf 'STAGE=%s PID=%s TARGET=%s JOBS=%s\n' "$stage" "$$" "$target" "$jobs"
case "$stage" in
  probe-bootstrap)
    mkdir -p build/bootstrap-probe
    cd build/bootstrap-probe
    printf 'int main(void) { return sizeof(long) == 8 ? 0 : 1; }\n' > probe.c
    printf 'all: probe.exe\nprobe.exe: probe.c\n\t$(CC) -O2 -Wall -Werror $< -o $@\n' > Makefile
    make -j"$jobs"
    ./probe.exe
    make -q
    printf 'native-make-d70-build-probe-ok\n'
    ;;
  configure-libgcc)
    mkdir -p "build/$target/libgcc" build/gcc/include
    cd "build/$target/libgcc"
    "$CONFIG_SHELL" "$root/source/libgcc/configure" \
      --srcdir=../../../source/libgcc \
      --build="$target" --host="$target" --target="$target" \
      --prefix=/usr --libdir=/usr/lib --with-target-subdir="$target" \
      --disable-multilib --enable-shared --enable-static --enable-threads=posix \
      --with-gnu-as --with-gnu-ld
    grep -q '^thread_header = gthr-posix.h$' Makefile
    grep -q '^enable_shared = yes$' Makefile
    for generated in libgcc_tm.h libgcc_tm.stamp; do
      if [[ -e $generated ]]; then
        mv "$generated" "$root/logs/$generated.before-relative-source-$(date +%s)"
      fi
    done
    ;;
  libgcc)
    mkdir -p build/gcc/include
    cd "build/$target/libgcc"
    make -j"$jobs"
    make -j1 bindir=/usr/bin DESTDIR="$root/dev" install
    ;;
  install-libgcc)
    cd "build/$target/libgcc"
    make -j1 bindir=/usr/bin DESTDIR="$root/dev" install-shared
    ;;
  libgcc-unwind)
    [[ $# == 4 && -f $4/receipts/inputs.json ]] ||
      { echo "Missing explicitly prepared libgcc successor" >&2; exit 2; }
    cd "$4"
    successor=$(pwd)
    cd "build/$target/libgcc"
    make -j"$jobs"
    make -j1 bindir=/usr/bin DESTDIR="$successor/dev" install
    ;;
  configure-libstdcxx)
    mkdir -p "build/$target/libstdc++-v3-raw-cxx"
    cd "build/$target/libstdc++-v3-raw-cxx"
    # Match the top-level GCC RAW_CXX_FOR_TARGET boundary. Installed C++
    # compatibility wrappers must not shadow C headers in configure probes.
    export CXX="$CXX -nostdinc++"
    export CPPFLAGS="-I$root/build/$target/libgcc"
    export CFLAGS="-O2 -g -pthread" CXXFLAGS="-O2 -g -pthread"
    "$CONFIG_SHELL" "$root/source/libstdc++-v3/configure" \
      --srcdir=../../../source/libstdc++-v3 \
      --build="$target" --host="$target" --target="$target" --prefix=/usr \
      --with-target-subdir="$target" --disable-multilib --enable-shared --enable-static \
      --enable-libstdcxx-threads --disable-symvers --disable-libstdcxx-pch \
      --enable-version-specific-runtime-libs --with-gnu-as --with-gnu-ld
    grep -q '^#define _GLIBCXX_HAS_GTHREADS 1$' config.h
    ;;
  libstdcxx)
    cd "build/$target/libstdc++-v3-raw-cxx"
    make -j"$jobs"
    make -j1 DESTDIR="$root/dev-raw-cxx" install
    ;;
  configure-libgomp|configure-libatomic|configure-libquadmath|configure-libvtv)
    name=${stage#configure-}
    mkdir -p "build/$target/$name"
    cd "build/$target/$name"
    export CFLAGS="-O2 -g -pthread" CXXFLAGS="-O2 -g -pthread"
    "$CONFIG_SHELL" "$root/source/$name/configure" \
      --srcdir="../../../source/$name" \
      --build="$target" --host="$target" --target="$target" --prefix=/usr \
      --with-target-subdir="$target" --disable-multilib --enable-shared --enable-static \
      --disable-symvers --enable-threads=posix --with-gnu-as --with-gnu-ld
    if [[ -f $name.la ]]; then
      mv "$name.la" "$root/logs/$name.la.before-config-refresh-$(date +%s)"
    fi
    ;;
  libgomp|libatomic|libquadmath|libvtv)
    cd "build/$target/$stage"
    make -j"$jobs"
    make -j1 DESTDIR="$root/dev" install
    ;;
  *) echo "Unknown focused library stage: $stage" >&2; exit 2 ;;
esac
