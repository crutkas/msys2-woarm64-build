#!/usr/bin/env bash
set -euo pipefail

[[ $# == 4 || $# == 5 ]] || {
    echo "usage: $0 SOURCE_ROOT BASE_INCLUDE CROSS_GCC PKGBUILD [EVIDENCE_ROOT]" >&2
    exit 2
}

source_root=$(cd "$1" && pwd -P)
base_include=$(cd "$2" && pwd -P)
cross_gcc=$3
pkgbuild=$4
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
repository_root=$(cd "$script_dir/../.." && pwd -P)
stage_script=$script_dir/pthread-headers-hack-before.sh
headers=(pthread_signal.h pthread_unistd.h pthread_time.h pthread_compat.h)
fixture='#include <pthread_time.h>
int main(void) { struct timespec value = {0}; return (int)value.tv_sec; }
'
if [[ $# == 5 ]]; then
    work=$5
    [[ ! -e "$work" ]] || {
        echo "Use a fresh evidence root: $work" >&2
        exit 1
    }
    mkdir -p "$work"
else
    work=$(mktemp -d)
    trap 'rm -rf -- "$work"' EXIT
fi

cp -a "$base_include" "$work/missing"
for header in "${headers[@]}"; do
    rm -f "$work/missing/$header"
done
install -m 0644 \
    "$source_root/mingw-w64-libraries/winpthreads/include/pthread_signal.h" \
    "$source_root/mingw-w64-libraries/winpthreads/include/pthread_unistd.h" \
    "$source_root/mingw-w64-libraries/winpthreads/include/pthread_time.h" \
    "$work/missing/"
printf '%s' "$fixture" >"$work/probe.c"
internal_include=$("$cross_gcc" -print-file-name=include)
if "$cross_gcc" -nostdinc -isystem "$internal_include" -I"$work/missing" \
    -std=gnu99 -c "$work/probe.c" -o "$work/missing.o" \
    >"$work/missing.stdout" 2>"$work/missing.stderr"; then
    echo "The incomplete three-header set unexpectedly compiled." >&2
    exit 1
fi
grep -Fq 'pthread_compat.h' "$work/missing.stderr" ||
    { cat "$work/missing.stderr" >&2; exit 1; }

git -c core.autocrlf=false clone --quiet --no-hardlinks "$source_root" "$work/bad-source"
git -C "$work/bad-source" remote set-url origin \
    https://github.com/Windows-on-ARM-Experiments/mingw-woarm64.git
rm "$work/bad-source/mingw-w64-libraries/winpthreads/include/pthread_compat.h"
mkdir "$work/bad-target"
if bash "$stage_script" "$work/bad-source" "$work/bad-target" \
    "$work/bad-receipt.json" "$pkgbuild" >"$work/bad.stdout" 2>"$work/bad.stderr"; then
    echo "The staging script accepted a missing source header." >&2
    exit 1
fi
[[ -z $(find "$work/bad-target" -mindepth 1 -print -quit) &&
    ! -e "$work/bad-receipt.json" ]] ||
    { echo "Missing-header rejection mutated output." >&2; exit 1; }

cp -a "$base_include" "$work/complete"
for header in "${headers[@]}"; do
    rm -f "$work/complete/$header"
done
bash "$stage_script" "$source_root" "$work/complete" \
    "$work/receipt.json" "$pkgbuild"

"$cross_gcc" -nostdinc -isystem "$internal_include" -I"$work/complete" \
    -std=gnu99 -c "$work/probe.c" -o "$work/complete.o"
"$cross_gcc" -nostdinc -isystem "$internal_include" \
    -I"$work/complete" \
    -I"$source_root/mingw-w64-crt" \
    -I"$source_root/mingw-w64-crt/include" \
    -std=gnu99 -fno-builtin -D_CRTBLD -D_WIN32_WINNT=0x0f00 \
    -D__MSVCRT_VERSION__=0x600 -D__USE_MINGW_ANSI_STDIO=0 \
    -c "$source_root/mingw-w64-crt/misc/gettimeofday.c" \
    -o "$work/gettimeofday.o"

for header in "${headers[@]}"; do
    cmp \
        "$source_root/mingw-w64-libraries/winpthreads/include/$header" \
        "$work/complete/$header"
done

grep -Fq '"sourceCommit": "92e63a665c6f217a41401feb69b4662928d370ba"' \
    "$work/receipt.json"

mkdir -p "$work/mock-bin" "$work/mingw-w64-cross-mingwarm64-crt"
mkdir "$work/pipeline-target"
cp "$pkgbuild" "$work/mingw-w64-cross-mingwarm64-crt/PKGBUILD"
cat >"$work/mock-bin/makepkg" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$MOCK_MAKEPKG_LOG"
if [[ " $* " == *" --nobuild "* ]]; then
    mkdir -p "$PWD/src"
    cp -a "$MOCK_SOURCE" "$PWD/src/mingw-w64"
fi
EOF
chmod +x "$work/mock-bin/makepkg"
(
    cd "$work/mingw-w64-cross-mingwarm64-crt"
    PATH="$work/mock-bin:$PATH" \
    FLAVOR=NATIVE_WITH_NATIVE \
    CLEAN_BUILD=1 \
    INSTALL_PACKAGE=0 \
    NO_EXTRACT=0 \
    MOCK_MAKEPKG_LOG="$work/makepkg.log" \
    MOCK_SOURCE="$source_root" \
    WOARM64_CRT_TARGET_INCLUDE="$work/pipeline-target" \
    WOARM64_CRT_HEADER_RECEIPT="$work/pipeline-receipt.json" \
        bash "$script_dir/build-package.sh" MSYS2-packages
)
[[ $(wc -l <"$work/makepkg.log") == 2 ]]
sed -n '1p' "$work/makepkg.log" | grep -Fq -- '--nobuild'
sed -n '1p' "$work/makepkg.log" | grep -Fq -- '--cleanbuild'
sed -n '2p' "$work/makepkg.log" | grep -Fq -- '--noextract'
if sed -n '2p' "$work/makepkg.log" | grep -Fq -- '--cleanbuild'; then
    echo "The second makepkg pass would delete its prepared source." >&2
    exit 1
fi
for header in "${headers[@]}"; do
    cmp \
        "$source_root/mingw-w64-libraries/winpthreads/include/$header" \
        "$work/pipeline-target/$header"
done
bash "$script_dir/pthread-headers-hack-after.sh"
for header in "${headers[@]}"; do
    [[ -f "$work/pipeline-target/$header" ]]
done
if grep -Fq 'dependencies: mingw-w64-cross-mingw64-winpthreads' \
    "$repository_root/.github/workflows/mingw-cross-toolchain.yml"; then
    echo "The CRT job still installs the incompatible x64 winpthreads package." >&2
    exit 1
fi

rm -rf \
    "$work/bad-source" \
    "$work/complete" \
    "$work/missing" \
    "$work/mingw-w64-cross-mingwarm64-crt" \
    "$work/mock-bin" \
    "$work/pipeline-target"

printf 'missing-three-header-control=failed-as-expected\n'
printf 'missing-source-header-control=failed-as-expected\n'
printf 'pthread-time-compile=passed\n'
printf 'gettimeofday-compile=passed\n'
printf 'two-phase-package-contract=passed\n'
printf 'downstream-header-retention=passed\n'
cat "$work/receipt.json"
