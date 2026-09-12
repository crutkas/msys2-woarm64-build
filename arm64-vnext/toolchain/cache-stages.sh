#!/usr/bin/env bash
# Sourced by bootstrap-cygwin.sh, under its lock and immutable recipe snapshot.
build_cache_runtime() {
  local epoch=$ROOT/epochs/cache-$(date -u +%Y%m%dT%H%M%S)-$$
  mkdir -p "$epoch"
  printf 'CACHE_EPOCH=%s\n' "$epoch"
  printf '%s\n' "$LOG" > "$epoch/build-log.txt"
  printf '%s\n' "$RECIPE" > "$epoch/recipe.txt"
  check_source gcc 5688a17320e775944bbe795010ebe7e89fc7a628
  cp "$ROOT/identities/gcc-patch.sha256" "$epoch/"
  git -C "$ROOT/sources/gcc" diff --binary HEAD > "$epoch/gcc-source.patch"
  sha256sum "$ROOT/sources/gcc/libgcc/config/aarch64/sync-cache.c" \
    > "$epoch/cache-source.sha256"

  local target tree prefix build out installed version program
  for target in aarch64-w64-mingw32 aarch64-pc-cygwin; do
    if [[ $target == aarch64-w64-mingw32 ]]; then
      tree=mingw-gcc-msabi
      prefix=$ROOT/mingw-cross
    else
      tree=gcc-msabi
      prefix=$ROOT/prefix
    fi
    build=$ROOT/build/$tree/$target/libgcc
    out=$epoch/$target
    [[ -f $build/Makefile && -s $build/libgcc.a && -s $build/sync-cache.o ]] ||
      fail "Build the original target libgcc stage first: $build"
    [[ $("$prefix/bin/$target-gcc" -dumpmachine) == "$target" ]] ||
      fail "Wrong target compiler"
    version=$("$prefix/bin/$target-gcc" -dumpversion)
    installed=$prefix/lib/gcc/$target/$version/libgcc.a
    [[ -s $installed ]] || fail "Missing installed baseline archive"
    mkdir -p "$out/baseline"
    cp -a "$build/libgcc.a" "$build/sync-cache.o" "$out/baseline/"
    cp -a "$installed" "$out/baseline/installed-libgcc.a"
    cp "$build/Makefile" "$build/config.log" "$build/config.status" "$out/baseline/"
    sha256sum "$out/baseline/"* > "$out/baseline.sha256"
    sha256sum "$installed" > "$out/installed-before.sha256"
    for program in xgcc cc1 cc1plus; do
      sha256sum "$ROOT/build/$tree/gcc/$program"
    done > "$out/build-compiler.sha256"
    sha256sum "$prefix/bin/$target-as" >> "$out/build-compiler.sha256"
    printf '' | "$prefix/bin/$target-gcc" -dM -E -x c - > "$out/target-macros.txt"
    grep -Eq '^#define (_WIN32|__CYGWIN__) ' "$out/target-macros.txt" ||
      fail "Windows cache guard is not active for $target"
    make -C "$build" -j"$JOBS" libgcc.a
    cp -a "$build/libgcc.a" "$build/sync-cache.o" "$out/"
    "$prefix/bin/$target-objdump" -dr "$out/sync-cache.o" > "$out/cache-disassembly.txt"
    grep -q '__imp_FlushInstructionCache' "$out/cache-disassembly.txt" ||
      fail "Missing Windows cache API reference"
    if grep -Eq 'ctr_el0|[[:space:]]dc[[:space:]]+cvau|[[:space:]]ic[[:space:]]+ivau' \
        "$out/cache-disassembly.txt"; then
      fail "Unix cache-maintenance instructions remain in the Windows object"
    fi
    sha256sum "$out/libgcc.a" "$out/sync-cache.o" > "$out/output.sha256"
    sha256sum -c "$out/installed-before.sha256"
    printf 'CACHE_TARGET=%s LIBRARY=%s VERSION=%s\n' "$target" "$out/libgcc.a" "$version"
  done
  printf 'CACHE_EPOCH_READY=%s (no installed prefix changed)\n' "$epoch"
}

stage_cache_cross_prefixes() {
  local epoch=${CACHE_EPOCH:?Set CACHE_EPOCH to the completed cache-runtime epoch}
  local target baseline destination version relative selected status program
  [[ -d $epoch ]] || fail "Missing cache epoch"
  for target in aarch64-pc-cygwin aarch64-w64-mingw32; do
    if [[ $target == aarch64-pc-cygwin ]]; then
      baseline=$ROOT/prefix
      destination=$epoch/cygwin-cross
    else
      baseline=$ROOT/mingw-cross
      destination=$epoch/mingw-cross
    fi
    [[ ! -e $destination ]] || fail "Preserving existing prefix: $destination"
    sha256sum -c "$epoch/$target/output.sha256"
    version=$("$baseline/bin/$target-gcc" -dumpversion)
    relative=lib/gcc/$target/$version/libgcc.a
    cp -a "$baseline" "$destination"
    cp "$epoch/$target/libgcc.a" "$destination/$relative"
    status=0
    LC_ALL=C diff -qr "$baseline" "$destination" > "$epoch/$target/prefix.diff" || status=$?
    [[ $status == 1 && $(wc -l < "$epoch/$target/prefix.diff") == 1 ]] ||
      fail "Unexpected cross-prefix difference"
    grep -Fx "Files $baseline/$relative and $destination/$relative differ" \
      "$epoch/$target/prefix.diff"
    selected=$("$destination/bin/$target-gcc" -print-libgcc-file-name)
    [[ $(realpath "$selected") == "$destination/$relative" ]] ||
      fail "Relocated cross compiler selected the wrong libgcc"
    [[ $(realpath "$("$destination/bin/$target-gcc" -print-sysroot)") == "$destination/$target" ]] ||
      fail "Relocated cross compiler selected the wrong sysroot"
    for program in cc1 as ld; do
      selected=$("$destination/bin/$target-gcc" "-print-prog-name=$program")
      selected=$(realpath "$selected")
      [[ -x $selected && $selected == "$destination/"* ]] ||
        fail "Compiler support tool escaped its epoch: $program"
      sha256sum "$selected"
    done > "$epoch/$target/relocated-support.sha256"
    printf 'CACHE_CROSS_PREFIX=%s TARGET=%s\n' "$destination" "$target"
  done
}

build_cache_cross_probe() {
  local epoch=${CACHE_EPOCH:?Set CACHE_EPOCH to the completed cache-runtime epoch}
  local library=$epoch/aarch64-pc-cygwin/libgcc.a
  local out=$ROOT/probes/cache-cross-$(date -u +%Y%m%dT%H%M%S)-$$
  local prefix=$epoch/cygwin-cross
  local cc=$prefix/bin/msys2-gcc name version selected
  [[ -d $epoch && -s $library ]] || fail "Missing Cygwin cache epoch: $epoch"
  sha256sum -c "$epoch/aarch64-pc-cygwin/output.sha256"
  selected=$("$cc" -print-libgcc-file-name)
  version=$("$cc" -dumpversion)
  [[ $(realpath "$selected") == "$prefix/lib/gcc/aarch64-pc-cygwin/$version/libgcc.a" ]] ||
    fail "MSYS compiler did not select its installed cache epoch archive"
  cmp "$selected" "$library"
  mkdir -p "$out"
  cp "$library" "$out/libgcc.a"
  for name in windows-clear-cache windows-cache-contract; do
    cp "$RECIPE/probes/$name.c" "$out/"
    "$cc" -O2 -Wall -Wextra "$out/$name.c" \
      "-Wl,-Map,$out/$name.map" -o "$out/$name.exe"
  done
  cp "$prefix/bin/msys-2.0.dll" "$out/"
  {
    printf 'host=Linux ARM64\ntarget=aarch64-pc-cygwin\nprofile=MSYS\n'
    "$cc" -v
    sha256sum "$cc" "$prefix/bin/aarch64-pc-cygwin-gcc" \
      "$prefix/libexec/gcc/aarch64-pc-cygwin/$version/cc1" \
      "$prefix/aarch64-pc-cygwin/bin/as" "$prefix/aarch64-pc-cygwin/bin/ld"
  } > "$out/compiler-identity.txt" 2>&1
  sha256sum "$out/"*.c "$out/"*.a "$out/"*.exe "$out/"*.dll > "$out/inputs-outputs.sha256"

  # The Linux branch must preprocess identically, not merely still compile.
  git -C "$ROOT/sources/gcc" show HEAD:libgcc/config/aarch64/sync-cache.c \
    > "$out/linux-original.c"
  gcc -E -P "$out/linux-original.c" -o "$out/linux-original.i"
  gcc -E -P "$ROOT/sources/gcc/libgcc/config/aarch64/sync-cache.c" -o "$out/linux-fixed.i"
  cmp "$out/linux-original.i" "$out/linux-fixed.i"
  gcc -O2 -S "$ROOT/sources/gcc/libgcc/config/aarch64/sync-cache.c" -o "$out/linux-fixed.s"
  grep -q ctr_el0 "$out/linux-fixed.s"
  printf 'CACHE_CROSS_PROBE=%s (execute on Windows; Linux branch unchanged)\n' "$out"
}
