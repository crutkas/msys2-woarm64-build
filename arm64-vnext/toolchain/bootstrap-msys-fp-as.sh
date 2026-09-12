#!/usr/bin/env bash
set -euo pipefail

main() {
  local stage=${1:?Choose prepare, host-as, cross-as, or native-as}
  local root=/root/arm64-vnext-20260905/toolchain
  local epoch=${MSYS_FP_AS_EPOCH:?Set a new private assembler epoch}
  local jobs=${JOBS:-1}
  local recipe
  recipe=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  [[ $epoch == "$root/epochs/"* && $epoch != *..* && $jobs =~ ^[12]$ ]] ||
    { printf 'Invalid epoch or job count\n' >&2; exit 1; }
  case $stage in prepare|host-as|cross-as|native-as) ;; *) exit 2 ;; esac
  mkdir -p "$epoch"/{logs,build,identities,recipes}
  if [[ ${MSYS_FP_RECIPE_SNAPSHOT:-} != "$recipe" ]]; then
    local snapshot=$epoch/recipes/$(date -u +%Y%m%dT%H%M%S)-$stage-$$
    mkdir "$snapshot"
    cp -a "$recipe/." "$snapshot/"
    exec env MSYS_FP_RECIPE_SNAPSHOT="$snapshot" bash "$snapshot/bootstrap-msys-fp-as.sh" "$stage"
  fi
  exec 9>"$epoch/build.lock"
  flock -n 9 || { printf 'This assembler epoch already has an active stage\n' >&2; exit 1; }
  local log=$epoch/logs/$(date -u +%Y%m%dT%H%M%S)-$stage-$$.log
  exec > >(tee "$log") 2>&1
  trap 'rc=$?; printf "STAGE=%s EXIT=%s\n" "${1:-unknown}" "$rc"' EXIT
  printf 'STAGE=%s EPOCH=%s JOBS=%s LOG=%s\n' "$stage" "$epoch" "$jobs" "$log"
  export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  python3 "$recipe/source-lock.py" verify
  local source=$epoch/source
  local sha=44335833f8f734f978211b082b15aed14efcf958
  if [[ $stage == prepare ]]; then
    [[ ! -e $source ]] || { printf 'Preserving existing source snapshot\n' >&2; exit 1; }
    mkdir "$source"
    git -C "$root/sources/binutils" cat-file -e "$sha:gas/config/obj-coff-seh.h"
    git -C "$root/sources/binutils" archive "$sha" | tar -x -C "$source"
    local patches patch
    patches=$(python3 "$recipe/source-lock.py" patches binutils)
    while IFS= read -r patch; do
      git -C "$source" apply --check "$patch"
      git -C "$source" apply "$patch"
      sha256sum "$patch"
    done <<< "$patches" > "$epoch/identities/binutils-patches.sha256"
    cp "$recipe/source-lock.json" "$epoch/identities/"
    printf '%s\n' "$sha" > "$epoch/identities/binutils-revision.txt"
    (cd "$source"; find . -type f -print0 | sort -z | xargs -0 sha256sum) \
      > "$epoch/identities/source.sha256"
    return
  fi
  [[ $(cat "$epoch/identities/binutils-revision.txt") == "$sha" ]]
  cmp "$recipe/source-lock.json" "$epoch/identities/source-lock.json"
  (cd "$source"; sha256sum --quiet -c "$epoch/identities/source.sha256")
  local target=aarch64-pc-cygwin host prefix build=$epoch/build/$stage
  host=$("$source/config.guess")
  prefix=$epoch/$stage
  mkdir -p "$build"
  cd "$build"
  local -a command
  if [[ $stage == native-as ]]; then
    local cross=$root/epochs/cache-20260905T120205-394/mingw-cross
    local fixed=$epoch/host-tools
    mkdir -p "$fixed"
    install -m 755 "$epoch/host-as/bin/aarch64-w64-mingw32-as" "$fixed/as"
    local cc="$cross/bin/aarch64-w64-mingw32-gcc"
    [[ $(realpath "$("$cc" "-B$fixed/" -print-prog-name=as)") == "$fixed/as" ]] ||
      { printf 'Native host compiler did not select corrected GAS\n' >&2; exit 1; }
    "$cc" "-B$fixed/" -v 2> "$epoch/identities/native-bootstrap-compiler.txt"
    sha256sum "$cc" "$fixed/as" >> "$epoch/identities/native-bootstrap-compiler.txt"
    command=(env CC="$cc -B$fixed/" CXX="$cross/bin/aarch64-w64-mingw32-g++ -B$fixed/"
      CFLAGS="-O2 -std=gnu17 -pthread" CXXFLAGS="-O2 -pthread" LDFLAGS="-static -pthread"
      CC_FOR_BUILD=gcc CXX_FOR_BUILD=g++ CFLAGS_FOR_BUILD=-O2
      "$source/configure" --build="$host" --host=aarch64-w64-mingw32)
    export PATH="$cross/bin:$PATH"
  else
    [[ $stage != host-as ]] || target=aarch64-w64-mingw32
    command=("$source/configure" --build="$host" --host="$host")
  fi
  command+=(--target="$target" --prefix="$prefix" --disable-nls --disable-werror
    --disable-gdb --disable-sim --disable-libdecnumber --disable-readline)
  printf '%q ' "${command[@]}" > configure.command.next
  printf '\n' >> configure.command.next
  if [[ -f configure.command ]]; then
    cmp configure.command configure.command.next ||
      { printf 'Configuration changed; use a new build directory\n' >&2; exit 1; }
  fi
  "${command[@]}"
  mv configure.command.next configure.command
  make -j"$jobs" all-gas
  make -C gas install
  if [[ $stage != native-as ]]; then
    python3 -B "$recipe/test-gas-fp-unwind.py" --assembler "$prefix/bin/$target-as" \
      --output "$epoch/identities/$stage-fp-encoding"
  fi
  printf 'ASSEMBLER_STAGE_READY=%s\n' "$prefix"
}
main "$@"; exit
