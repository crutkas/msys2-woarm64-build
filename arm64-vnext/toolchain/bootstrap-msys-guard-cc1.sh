#!/usr/bin/env bash
# Isolated, seeded frontend build. No installation into an admitted SDK.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 4 ]]; then
  printf 'Usage: %s NEW_ROOT JOBS [--cxx] [--resume]\n' "$0" >&2
  exit 2
fi
root=$1
jobs=$2
shift 2
resume=
frontend=cc1.exe
for option in "$@"; do
  case "$option" in
    --resume) resume=--resume ;;
    --cxx) frontend=cc1plus.exe ;;
    *) echo "Unknown option: $option" >&2; exit 2 ;;
  esac
done
[[ $root == /root/arm64-vnext-20260905/toolchain/epochs/guard-* &&
   $root != *..* ]] || { echo 'Use a dedicated guard epoch' >&2; exit 2; }
if [[ -n $resume ]]; then
  [[ $resume == --resume && -f $root/identities/seed.before.sha256 ]] ||
    { echo 'Resume only this recipe existing private build' >&2; exit 2; }
else
  [[ ! -e $root ]] || { echo 'Use a new root or explicit --resume' >&2; exit 2; }
fi
[[ $jobs =~ ^[12]$ ]] || { echo 'Current producer allocation is at most two jobs' >&2; exit 2; }
recipe=$(cd "$(dirname "$0")" && pwd)
old=/root/arm64-cmocka-gcc-20260907-02
seed=$old/epochs/native-msys-cmocka-02/build/gcc
source=/root/arm64-vnext-20260905/toolchain/sources/gcc
expected=20f79b9eefd812e555e3989c24833ba73fd2f7e068dc5d5e218b26e73523943b
if [[ $frontend == cc1plus.exe ]]; then
  old=/root/arm64-vnext-20260905/toolchain/epochs/guard-salted-20260908-01
  seed=$old/epochs/native-msys-guard/build/gcc
  expected=b8046275497c4e8f4d056530ef2e956d1b7672a0e5eb15ad56fde5bf44e76b0a
fi
[[ $(sha256sum "$seed/gcc/cc1.exe" | cut -d' ' -f1) == "$expected" ]] ||
  { echo 'C frontend build seed differs from its qualified producer' >&2; exit 1; }
while IFS= read -r -d '' link; do
  [[ $(realpath "$link") == "$seed/"* ]] ||
    { echo "Build seed contains an external link: $link" >&2; exit 1; }
done < <(find "$seed" -type l -print0)
if [[ -z $resume ]]; then
  mkdir -p "$root"/{sources,identities,logs,recipe,epochs/native-msys-guard/build}
  cp -a "$recipe/." "$root/recipe/"
  printf '%s\n' "$frontend" > "$root/identities/frontend-target"
else
  [[ $(cat "$root/identities/frontend-target") == "$frontend" ]] ||
    { echo 'Resume frontend target differs' >&2; exit 1; }
fi
exec > >(tee "$root/logs/driver$(date -u +%Y%m%dT%H%M%S).log") 2>&1
printf 'PID=%s ROOT=%s FRONTEND=%s JOBS=%s START=%s\n' \
  "$$" "$root" "$frontend" "$jobs" "$(date -u --iso-8601=seconds)"
if [[ -z $resume ]]; then
  find "$seed" -type f -print0 | sort -z | xargs -0 sha256sum > "$root/identities/seed.before.sha256"
  git -C "$source" diff --binary HEAD | sha256sum > "$root/identities/original-source.before.sha256"
  git clone --quiet --shared --no-checkout "$source" "$root/sources/gcc"
  git -C "$root/sources/gcc" -c core.autocrlf=false checkout --quiet --detach \
    5688a17320e775944bbe795010ebe7e89fc7a628
  cp -a --reflink=auto "$old/native-deps" "$root/native-deps"
  cp -a --reflink=auto "$seed" "$root/epochs/native-msys-guard/build/gcc"
  mv "$root/epochs/native-msys-guard/build/gcc/configure.command" "$root/identities/seed-configure.command"
  # Cached configure results embed the predecessor's GMP include/lib paths.
  while IFS= read -r -d '' cache; do
    relative=${cache#"$root/epochs/native-msys-guard/build/gcc/"}
    destination=$root/identities/seed-config-cache/$relative
    mkdir -p "$(dirname "$destination")"
    mv "$cache" "$destination"
  done < <(find "$root/epochs/native-msys-guard/build/gcc" -name config.cache -type f -print0)
fi
export TOOLCHAIN_ROOT=$root JOBS=$jobs NATIVE_MSYS_EPOCH=$root/epochs/native-msys-guard
export ACCEPTED_CACHE_EPOCH=/root/arm64-vnext-20260905/toolchain/epochs/cache-20260905T120205-394
export RUNTIME_SYSROOT=/root/arm64-vnext-20260905/runtime/ucontext-20260907-03/prefix/aarch64-pc-cygwin
export RUNTIME_DLL=/root/arm64-vnext-20260905/runtime/ucontext-20260907-03/prefix/bin/msys-2.0.dll
bash "$root/recipe/bootstrap-cygwin.sh" native-msys-configure
export PATH="$ACCEPTED_CACHE_EPOCH/mingw-cross/bin:$ACCEPTED_CACHE_EPOCH/cygwin-cross/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
build=$root/epochs/native-msys-guard/build/gcc
printf 'BUILD_COMMAND=make -C %q -j%s all-gcc TARGET-gcc=%s\n' "$build" "$jobs" "$frontend"
make -C "$build" -j"$jobs" all-gcc "TARGET-gcc=$frontend" 2>&1 | tee "$root/logs/${frontend%.exe}-build.log"
sha256sum "$build/gcc/$frontend" "$build/gcc/aarch64.o" \
  "$root/sources/gcc/gcc/config/aarch64/aarch64.cc" > "$root/identities/output.sha256"
sha256sum --check --quiet "$root/identities/seed.before.sha256"
git -C "$source" diff --binary HEAD | sha256sum > "$root/identities/original-source.after.sha256"
cmp "$root/identities/original-source.before.sha256" "$root/identities/original-source.after.sha256"
printf 'COMPLETE=%s\n' "$(date -u --iso-8601=seconds)"
