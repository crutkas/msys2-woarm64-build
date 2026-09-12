#!/usr/bin/env bash
set -euo pipefail

# Parse the complete recipe before executing a long stage, so an edit to this
# worktree cannot change the commands a running Bash process reads next.
main() {
# Run under Linux/WSL. Sources, objects, installed tools and logs stay on ext4.
ROOT=${TOOLCHAIN_ROOT:-/root/arm64-vnext-20260905/toolchain}
JOBS=${JOBS:-14}
TARGET=aarch64-pc-cygwin
PREFIX=$ROOT/prefix
SYSROOT=$PREFIX/$TARGET
RECIPE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
STAGE=${1:-}

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ $ROOT == /* && $ROOT != / && $ROOT != /root && $ROOT != /mnt/* ]] ||
  fail "TOOLCHAIN_ROOT must be a dedicated absolute Linux filesystem directory"
[[ $JOBS =~ ^[1-9][0-9]*$ && $JOBS -le 14 ]] ||
  fail "JOBS must be 1..14; coordinate the shared machine budget before raising it"
case $STAGE in
  sources|binutils|ld|ld-install|gcc|gcc-candidate|w32api|w32api-libs|cxx-headers|libgcc|probe|msys-specs|gas|gas-install|mingw-gas|mingw-binutils|mingw-gcc|mingw-gcc-candidate|mingw-headers|mingw-crt|mingw-libraries|native-configure|native-deps|native-binutils|native-gcc|native-gas|native-windres|native-drivers|cache-runtime|cache-cross-prefixes|cache-cross-probe|native-msys-configure|native-msys-gcc|native-msys-binutils|native-msys-runtime|native-msys-libstdcxx|native-msys-finalize|native-msys-posix-cross) ;;
  *) fail "Unknown stage: $STAGE. See README.md for the bootstrap sequence." ;;
esac
if [[ $STAGE == mingw-* || $STAGE == native-* ]]; then
  TARGET=aarch64-w64-mingw32
  PREFIX=$ROOT/mingw-cross
  SYSROOT=$PREFIX/$TARGET
fi

mkdir -p "$ROOT"/{sources,build,logs,identities} "$PREFIX"
if [[ ${TOOLCHAIN_RECIPE_SNAPSHOT:-} != "$RECIPE" ]]; then
  snapshot=$ROOT/recipes/$(date -u +%Y%m%dT%H%M%S)-$STAGE-$$
  mkdir -p "$snapshot"
  cp -a "$RECIPE/." "$snapshot/"
  export TOOLCHAIN_RECIPE_SNAPSHOT=$snapshot
  exec bash "$snapshot/bootstrap-cygwin.sh" "$@"
fi
exec 9>"$ROOT/bootstrap.lock"
flock -n 9 || fail "Another toolchain stage is running in $ROOT"
LOG=$ROOT/logs/$(date -u +%Y%m%dT%H%M%S)-$STAGE-$$.log
exec > >(tee "$LOG") 2>&1
trap 'result=$?; printf "STAGE=%s EXIT=%s LOG=%s\n" "$STAGE" "$result" "$LOG"' EXIT
printf 'STAGE=%s ROOT=%s JOBS=%s PID=%s UTC=%s\n' \
  "$STAGE" "$ROOT" "$JOBS" "$$" "$(date -u --iso-8601=seconds)"
uname -a
free -h
df -h "$ROOT"
sha256sum "$RECIPE/bootstrap-cygwin.sh"
python3 "$RECIPE/source-lock.py" verify
export PATH="$PREFIX/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

fetch_source() {
  local name=$1 url sha blob directory=$ROOT/sources/$1 actual
  url=$(python3 "$RECIPE/source-lock.py" source "$name" repository)
  sha=$(python3 "$RECIPE/source-lock.py" source "$name" revision)
  blob=$(python3 "$RECIPE/source-lock.py" source "$name" blob)
  if [[ ! -d $directory ]]; then
    git init "$directory"
    git -C "$directory" config core.autocrlf false
    git -C "$directory" remote add origin "$url"
  fi
  [[ $(git -C "$directory" remote get-url origin) == "$url" ]] ||
    fail "Unexpected origin in $directory"
  if ! git -C "$directory" cat-file -e "$sha^{commit}" 2>/dev/null; then
    git -C "$directory" fetch --depth=1 origin "$sha"
  fi
  if ! git -C "$directory" rev-parse --verify HEAD >/dev/null 2>&1; then
    git -C "$directory" -c advice.detachedHead=false checkout --detach "$sha"
  fi
  actual=$(git -C "$directory" rev-parse --verify HEAD)
  [[ -n $actual && $actual == "$sha" ]] || fail "Wrong source HEAD: $directory"
  git -C "$directory" cat-file -e "$sha:$blob"
  [[ $(git -C "$directory" cat-file -s "$sha:$blob") -gt 0 ]] ||
    fail "Empty source blob: $blob"
  {
    printf 'name=%s\nurl=%s\ncommit=%s\n' "$name" "$url" "$actual"
    printf 'source_blob=%s\n' "$(git -C "$directory" rev-parse "$sha:$blob")"
    git -C "$directory" status --short
  } | tee "$ROOT/identities/$name.txt"
}

check_source() {
  local name=$1 sha=$2 directory=$ROOT/sources/$1
  [[ $(python3 "$RECIPE/source-lock.py" source "$name" revision) == "$sha" ]] ||
    fail "Source lock and recipe revision disagree: $name"
  [[ -d $directory ]] || fail "Run sources first"
  [[ $(git -C "$directory" rev-parse --verify HEAD) == "$sha" ]] ||
    fail "Unexpected $name source revision"
  if [[ $name == gcc || $name == binutils || $name == mingw-woarm64 ]]; then
    local patch patch_list
    local patches
    patch_list=$(python3 "$RECIPE/source-lock.py" patches "$name")
    [[ -n $patch_list ]] || fail "Missing source patch series: $name"
    mapfile -t patches <<< "$patch_list"
    # Match an exact prefix of the patch series before applying anything.
    # Later patches may legitimately change an earlier patch's context.
    local index=$ROOT/identities/$name-expected.index
    GIT_INDEX_FILE=$index git -C "$directory" read-tree "$sha"
    local applied matched=false
    for ((applied = 0; applied <= ${#patches[@]}; applied++)); do
      if GIT_INDEX_FILE=$index git -C "$directory" diff --quiet &&
         [[ -z $(GIT_INDEX_FILE=$index git -C "$directory" ls-files --others --exclude-standard) ]]; then
        matched=true
        break
      fi
      if ((applied < ${#patches[@]})); then
        GIT_INDEX_FILE=$index git -C "$directory" apply --cached "${patches[applied]}"
      fi
    done
    [[ $matched == true ]] ||
      fail "Unexpected $name source delta; preserving it for inspection"
    for ((; applied < ${#patches[@]}; applied++)); do
      patch=${patches[applied]}
      git -C "$directory" apply --check "$patch"
      git -C "$directory" apply "$patch"
      GIT_INDEX_FILE=$index git -C "$directory" apply --cached "$patch"
    done
    GIT_INDEX_FILE=$index git -C "$directory" diff --exit-code ||
      fail "Unexpected $name source delta; preserving it for inspection"
    [[ -z $(GIT_INDEX_FILE=$index git -C "$directory" ls-files --others --exclude-standard) ]] ||
      fail "Unexpected untracked $name source files"
    sha256sum "${patches[@]}" | tee "$ROOT/identities/$name-patch.sha256"
    return
  fi
  [[ -z $(git -C "$directory" status --porcelain) ]] ||
    fail "Preserving unexpected source changes in $directory; inspect before continuing"
}

configure_build() {
  local directory=$1
  shift
  mkdir -p "$directory"
  cd "$directory"
  printf '%q ' "$@" > configure.command.next
  printf '\n' >> configure.command.next
  if [[ -f configure.command ]]; then
    cmp configure.command configure.command.next ||
      fail "Configuration changed: use a new dedicated build root, not stale objects"
  fi
  # Re-detect tools installed after a failed build; retain all object files.
  "$@"
  mv configure.command.next configure.command
}

case $STAGE in
  native-drivers)
    check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
    driver_epoch=$ROOT/epochs/native-drivers-$(date -u +%Y%m%dT%H%M%S)-$$
    mkdir -p "$driver_epoch"
    cp "$RECIPE/source-lock.json" "$driver_epoch/"
    for flavor in mingw msys; do
      if [[ $flavor == mingw ]]; then
        driver_build=$ROOT/build/native-gcc-refptr
      else
        driver_build=${NATIVE_MSYS_EPOCH:-$ROOT/epochs/native-msys-20260905}/build/gcc
      fi
      [[ -f $driver_build/Makefile ]] || fail "Missing configured $flavor native compiler"
      mkdir -p "$driver_epoch/$flavor/baseline"
      cp "$driver_build/gcc/"{xgcc,xg++,cpp}.exe "$driver_epoch/$flavor/baseline/"
      # Use the top-level Canadian-build environment, but rebuild only drivers:
      # TARGET_EXECUTABLE_SUFFIX is consumed by gcc.cc, not generated code.
      make -C "$driver_build" -j"$JOBS" all-gcc 'TARGET-gcc=xgcc.exe xg++.exe cpp.exe'
      cp "$driver_build/gcc/"{xgcc,xg++,cpp}.exe "$driver_epoch/$flavor/"
      sha256sum "$driver_epoch/$flavor/"*.exe
    done
    printf 'NATIVE_DRIVER_EPOCH=%s (not installed into any accepted prefix)\n' "$driver_epoch"
    ;;
  native-windres)
    check_source binutils 44335833f8f734f978211b082b15aed14efcf958
    make -C "$ROOT/build/native-binutils-refptr/binutils" -j"$JOBS" windres.exe
    sha256sum "$ROOT/build/native-binutils-refptr/binutils/windres.exe"
    ;;
  native-msys-configure|native-msys-gcc|native-msys-binutils|native-msys-runtime|native-msys-libstdcxx|native-msys-finalize|native-msys-posix-cross)
    source "$RECIPE/native-msys-stages.sh"
    build_native_msys_stage
    ;;
  cache-runtime)
    source "$RECIPE/cache-stages.sh"
    build_cache_runtime
    ;;
  cache-cross-probe)
    source "$RECIPE/cache-stages.sh"
    build_cache_cross_probe
    ;;
  cache-cross-prefixes)
    source "$RECIPE/cache-stages.sh"
    stage_cache_cross_prefixes
    ;;
  sources)
    fetch_source binutils
    fetch_source gcc
    fetch_source mingw-w64
    fetch_source mingw-woarm64
    ;;
  binutils)
    check_source binutils 44335833f8f734f978211b082b15aed14efcf958
    configure_build "$ROOT/build/binutils" "$ROOT/sources/binutils/configure" \
      --target="$TARGET" --prefix="$PREFIX" --with-sysroot="$SYSROOT" \
      --disable-nls --disable-werror --disable-gdb --disable-sim \
      --disable-libdecnumber --disable-readline
    make -j"$JOBS"
    make install
    "$PREFIX/bin/$TARGET-ld" -V
    ;;
  gcc|gcc-candidate)
    check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
    [[ -x $PREFIX/bin/$TARGET-as ]] || fail "Build binutils first"
    configure_build "$ROOT/build/gcc-msabi" "$ROOT/sources/gcc/configure" \
      --target="$TARGET" --prefix="$PREFIX" --with-sysroot="$SYSROOT" \
      --enable-languages=c,c++ --without-headers --with-newlib \
      --disable-multilib --disable-nls --disable-shared --disable-threads \
      --disable-libssp --disable-libgomp --disable-libatomic --disable-libquadmath \
      --disable-libstdcxx --disable-bootstrap --disable-werror
    make -j"$JOBS" all-gcc
    if [[ $STAGE == gcc ]]; then
      make install-gcc
      "$PREFIX/bin/$TARGET-gcc" -v
      "$PREFIX/bin/$TARGET-g++" -v
    fi
    ;;
  w32api)
    check_source mingw-w64 819a6ec2ea87c19814b287e21d65e0dc7f05abba
    overlay_identity=$(python3 "$RECIPE/prepare-w32api-overlay.py" --identity-only)
    overlay=$ROOT/build/w32api-source-$overlay_identity
    python3 "$RECIPE/prepare-w32api-overlay.py" \
      --source "$ROOT/sources/mingw-w64" --output "$overlay"
    sha256sum "$overlay/mingw-w64-headers/crt/_cygwin.h" \
      "$overlay/mingw-w64-headers/include/basetsd.h" \
      "$overlay/mingw-w64-headers/include/psdk_inc/intrin-impl.h" |
      tee "$ROOT/identities/w32api-patched-headers.sha256"
    configure_build "$ROOT/build/w32api-headers" \
      "$overlay/mingw-w64-headers/configure" --host="$TARGET" \
      --prefix="$SYSROOT" --includedir="$SYSROOT/include/w32api" \
      --enable-sdk=all --with-default-msvcrt=msvcrt
    make install
    test -s "$SYSROOT/include/w32api/windows.h"
    ;;
  libgcc)
    check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
    [[ -f $ROOT/build/gcc-msabi/Makefile ]] || fail "Build GCC first"
    cd "$ROOT/build/gcc-msabi"
    make -j"$JOBS" all-target-libgcc
    make install-target-libgcc
    "$PREFIX/bin/$TARGET-gcc" -print-libgcc-file-name
    ;;
  w32api-libs)
    check_source mingw-w64 819a6ec2ea87c19814b287e21d65e0dc7f05abba
    crt=$ROOT/sources/mingw-w64/mingw-w64-crt
    mkdir -p "$ROOT/build/w32api-libs" "$SYSROOT/lib"
    cd "$ROOT/build/w32api-libs"
    for library in kernel32 ntdll user32 winmm advapi32 netapi32 userenv shell32 \
                   ole32 oleaut32 ws2_32 wsock32 bcrypt setupapi hid crypt32 secur32; do
      if [[ -f $crt/libarm64/$library.def ]]; then
        cp "$crt/libarm64/$library.def" "$library.def"
      elif [[ -f $crt/lib-common/$library.def.in ]]; then
        "$TARGET-gcc" -E -x c "$crt/lib-common/$library.def.in" \
          -Wp,-w -undef -P -I"$crt/def-include" -DDEF_ARM64 > "$library.def"
      elif [[ -f $crt/lib-common/$library.def ]]; then
        cp "$crt/lib-common/$library.def" "$library.def"
      else
        fail "No official ARM64 definition for $library"
      fi
      test -s "$library.def"
      "$TARGET-dlltool" -m arm64 -k --as="$PREFIX/bin/$TARGET-as" \
        --input-def "$library.def" --output-lib "lib$library.a"
      "$TARGET-nm" --defined-only "lib$library.a" > "$library.symbols"
      test -s "$library.symbols"
      install -m 644 "lib$library.a" "$SYSROOT/lib/"
    done
    sha256sum ./*.def ./*.a | tee "$ROOT/identities/w32api-libs.sha256"
    ;;
  cxx-headers)
    check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
    [[ -x $PREFIX/bin/$TARGET-g++ ]] || fail "Build GCC first"
    version=$("$PREFIX/bin/$TARGET-gcc" -dumpversion)
    configure_build "$ROOT/build/libstdcxx-headers" env \
      CC="$PREFIX/bin/$TARGET-gcc" CXX="$PREFIX/bin/$TARGET-g++" \
      "$ROOT/sources/gcc/libstdc++-v3/configure" \
      --build="$("$ROOT/sources/gcc/config.guess")" --host="$TARGET" \
      --with-target-subdir="$TARGET" \
      --prefix="$PREFIX" --with-gxx-include-dir="$SYSROOT/include/c++/$version" \
      --with-newlib --without-headers --disable-hosted-libstdcxx \
      --disable-multilib --disable-shared --disable-threads --disable-nls \
      --disable-libstdcxx-pch --disable-symvers --disable-libstdcxx-time
    make -C include all
    make -C include install
    make -C libsupc++ install-stdHEADERS install-bitsHEADERS
    test -s "$SYSROOT/include/c++/$version/$TARGET/bits/c++config.h"
    "$PREFIX/bin/$TARGET-g++" -c "$RECIPE/probes/bootstrap-headers.cc" \
      -o "$ROOT/build/libstdcxx-headers/bootstrap-headers.o"
    ;;
  probe)
    [[ -x $PREFIX/bin/$TARGET-g++ ]] || fail "Build GCC first"
    probe_dir=$ROOT/probes/$(date -u +%Y%m%dT%H%M%S)-$$
    mkdir -p "$probe_dir"
    cd "$probe_dir"
    sha256sum "$RECIPE"/probes/* > sources.sha256
    "$TARGET-gcc" -O2 -S "$RECIPE/probes/compiler.c" -o compiler.s
    "$TARGET-as" compiler.s -o compiler.o
    "$TARGET-g++" -O2 -fno-exceptions -fno-rtti -S \
      "$RECIPE/probes/compiler.cc" -o compiler-cxx.s
    "$TARGET-as" compiler-cxx.s -o compiler-cxx.o
    "$TARGET-gcc" -O2 -pg -S "$RECIPE/probes/compiler.c" -o profiling.s
    "$TARGET-dlltool" -m arm64 -d "$RECIPE/probes/kernel32.def" -l libkernel32-probe.a
    "$TARGET-g++" -nostdlib compiler.o compiler-cxx.o libkernel32-probe.a -lgcc \
      -Wl,-e,ProbeEntry,--subsystem,console,--no-insert-timestamp -o compiler-probe.exe
    "$TARGET-g++" -O2 -fno-exceptions -fno-rtti -DPROBE_NEGATIVE_CONTROL \
      -c "$RECIPE/probes/compiler.cc" -o compiler-negative.o
    "$TARGET-g++" -nostdlib compiler.o compiler-negative.o libkernel32-probe.a -lgcc \
      -Wl,-e,ProbeEntry,--subsystem,console,--no-insert-timestamp -o compiler-negative.exe
    "$TARGET-objdump" -p compiler-probe.exe > compiler-probe.imports.txt
    "$TARGET-objdump" -d compiler-probe.exe > compiler-probe.disassembly.txt
    sha256sum compiler-probe.exe compiler-negative.exe compiler.o compiler-cxx.o \
      compiler.s compiler-cxx.s profiling.s | tee SHA256SUMS
    printf 'No-CRT probes: run on Windows, expecting exit 73 (positive), 91 (negative).\n'
    printf 'PROBE_DIRECTORY=%s\n' "$probe_dir"
    ;;
  mingw-binutils)
    check_source binutils 44335833f8f734f978211b082b15aed14efcf958
    configure_build "$ROOT/build/mingw-binutils" "$ROOT/sources/binutils/configure" \
      --target="$TARGET" --prefix="$PREFIX" --with-sysroot="$SYSROOT" \
      --disable-nls --disable-werror --disable-gdb --disable-sim \
      --disable-libdecnumber --disable-readline
    make -j"$JOBS"
    make install
    ;;
  mingw-gcc|mingw-gcc-candidate)
    check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
    [[ -x $PREFIX/bin/$TARGET-as ]] || fail "Build mingw-binutils first"
    configure_build "$ROOT/build/mingw-gcc-msabi" "$ROOT/sources/gcc/configure" \
      --target="$TARGET" --prefix="$PREFIX" --with-sysroot="$SYSROOT" \
      --enable-languages=c,c++ --without-headers --with-arch=armv8-a \
      --with-native-system-header-dir=/include \
      --with-default-msvcrt=ucrt --enable-threads=posix \
      --disable-multilib --disable-nls --disable-shared \
      --disable-libssp --disable-libgomp --disable-libatomic --disable-libquadmath \
      --disable-libstdcxx --disable-bootstrap --disable-werror
    make -j"$JOBS" all-gcc
    if [[ $STAGE == mingw-gcc ]]; then
      make install-gcc
    fi
    ;;
  mingw-headers|mingw-crt|mingw-libraries)
    source "$RECIPE/mingw-stages.sh"
    build_mingw_runtime
    ;;
  msys-specs)
    version=$("$PREFIX/bin/$TARGET-gcc" -dumpversion)
    python3 "$RECIPE/generate-msys-specs.py" \
      --compiler "$PREFIX/bin/$TARGET-gcc" \
      --output "$PREFIX/lib/gcc/$TARGET/$version/msys2.specs" \
      --manifest "$ROOT/identities/msys-specs.json"
    install -m 755 "$RECIPE/msys2-driver.sh" "$PREFIX/bin/msys2-gcc"
    install -m 755 "$RECIPE/msys2-driver.sh" "$PREFIX/bin/msys2-g++"
    "$PREFIX/bin/msys2-gcc" -c "$RECIPE/probes/msys-profile.c" \
      -o "$ROOT/build/msys-profile.o"
    "$PREFIX/bin/msys2-gcc" -### "$RECIPE/probes/msys-profile.c" \
      > "$ROOT/identities/msys-link-dry-run.txt" 2>&1
    sha256sum "$PREFIX/bin/msys2-gcc" "$PREFIX/bin/msys2-g++" \
      "$PREFIX/lib/gcc/$TARGET/$version/msys2.specs"
    ;;
  native-configure|native-deps|native-binutils|native-gcc)
    source "$RECIPE/native-stages.sh"
    build_native_stage
    ;;
  gas|gas-install)
    check_source binutils 44335833f8f734f978211b082b15aed14efcf958
    make -C "$ROOT/build/binutils/gas" -j"$JOBS"
    python3 "$RECIPE/test-gas-unwind.py" \
      --assembler "$ROOT/build/binutils/gas/as-new" \
      --output "$ROOT/probes/gas-$(date -u +%Y%m%dT%H%M%S)-$$"
    if [[ $STAGE == gas-install ]]; then
      make -C "$ROOT/build/binutils/gas" install
      cmp "$PREFIX/bin/$TARGET-as" "$PREFIX/$TARGET/bin/as"
      sha256sum "$PREFIX/bin/$TARGET-as" "$PREFIX/$TARGET/bin/as"
    fi
    ;;
  ld|ld-install)
    check_source binutils 44335833f8f734f978211b082b15aed14efcf958
    make -C "$ROOT/build/binutils" -j"$JOBS" all-ld
    if [[ $STAGE == ld-install ]]; then
      make -C "$ROOT/build/binutils/ld" install
      cmp "$PREFIX/bin/$TARGET-ld" "$PREFIX/$TARGET/bin/ld"
    fi
    sha256sum "$ROOT/build/binutils/ld/ld-new"
    ;;
  mingw-gas|native-gas)
    check_source binutils 44335833f8f734f978211b082b15aed14efcf958
    if [[ $STAGE == mingw-gas ]]; then
      gas_build=$ROOT/build/mingw-binutils/gas
    else
      gas_build=$ROOT/build/native-binutils-refptr/gas
    fi
    make -C "$gas_build" -j"$JOBS"
    make -C "$gas_build" install
    if [[ $STAGE == mingw-gas ]]; then
      cmp "$PREFIX/bin/$TARGET-as" "$PREFIX/$TARGET/bin/as"
      python3 "$RECIPE/test-gas-unwind.py" \
        --assembler "$PREFIX/bin/$TARGET-as" \
        --output "$ROOT/probes/mingw-gas-$(date -u +%Y%m%dT%H%M%S)-$$"
    else
      sha256sum "$ROOT/native/bin/as.exe"
    fi
    ;;
esac
}

main "$@"; exit
