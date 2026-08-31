#!/bin/bash

set -euo pipefail
export PATH="/usr/bin:/bin${PATH:+:$PATH}"

repo_root=$(realpath "$(dirname "${BASH_SOURCE[0]}")/../..")
source "$repo_root/.github/scripts/lib/path-boundary.sh"
source "$repo_root/.github/scripts/lib/stage0-git.sh"

assert_equal() {
  local expected=$1
  local actual=$2
  local message=$3

  if [[ "$actual" != "$expected" ]]; then
    printf 'Assertion failed: %s\nexpected: <%s>\nactual:   <%s>\n' \
      "$message" "$expected" "$actual" >&2
    exit 1
  fi
}

assert_file_contains() {
  local file=$1
  local text=$2

  if ! grep -Fq "$text" "$file"; then
    echo "Assertion failed: $file does not contain $text" >&2
    exit 1
  fi
}

temporary_root=$(mktemp -d)
trap 'rm -rf "$temporary_root"' EXIT

fixture_root="$temporary_root/root with spaces/\$portable"
mkdir -p "$fixture_root"
cp -R "$repo_root/tests/bootstrap/fixtures/." "$fixture_root/"

set +e
patch_output=$(
  cd "$fixture_root"
  patch --dry-run -p1 -i "$repo_root/patches/makepkg/0001-mingwarm64.patch" 2>&1
)
patch_status=$?
set -e
if [[ $patch_status -eq 0 ]]; then
  echo "Assertion failed: stale patch unexpectedly applied to the portable-base fixture" >&2
  exit 1
fi
assert_file_contains <(printf '%s\n' "$patch_output") 'file etc/makepkg_mingw.conf'
assert_file_contains <(printf '%s\n' "$patch_output") 'file etc/msystem'
assert_file_contains <(printf '%s\n' "$patch_output") 'file usr/bin/makepkg-mingw'
assert_equal '3' \
  "$(grep -c 'Hunk #1 FAILED' <<< "$patch_output")" \
  'stale patch reproduces all three failed hunks'

before_makepkg=$(sha256sum "$fixture_root/etc/makepkg_mingw.conf" | cut -d' ' -f1)
before_msystem=$(sha256sum "$fixture_root/etc/msystem" | cut -d' ' -f1)
before_wrapper=$(sha256sum "$fixture_root/usr/bin/makepkg-mingw" | cut -d' ' -f1)

MSYS2_ROOT="$fixture_root" \
  FLAVOR=NATIVE_WITH_NATIVE \
  SETUP_MINGWARM64_SKIP_DIAGNOSTICS=1 \
  "$repo_root/.github/scripts/setup-mingwarm64.sh"

first_config=$(sha256sum "$fixture_root/etc/makepkg_mingw.d/mingwarm64.conf" | cut -d' ' -f1)
first_msystem=$(sha256sum "$fixture_root/etc/msystem.d/MINGWARM64" | cut -d' ' -f1)
first_compiler=$(sha256sum "$fixture_root/usr/local/libexec/msys2-woarm64/woarm64-gcc" | cut -d' ' -f1)
first_launcher_source=$(sha256sum "$fixture_root/usr/local/libexec/msys2-woarm64/native-compiler-launcher.c" | cut -d' ' -f1)

MSYS2_ROOT="$fixture_root" \
  FLAVOR=NATIVE_WITH_NATIVE \
  SETUP_MINGWARM64_SKIP_DIAGNOSTICS=1 \
  "$repo_root/.github/scripts/setup-mingwarm64.sh"

assert_equal "$first_config" \
  "$(sha256sum "$fixture_root/etc/makepkg_mingw.d/mingwarm64.conf" | cut -d' ' -f1)" \
  'makepkg drop-in is idempotent'
assert_equal "$first_msystem" \
  "$(sha256sum "$fixture_root/etc/msystem.d/MINGWARM64" | cut -d' ' -f1)" \
  'msystem drop-in is idempotent'
assert_equal "$first_compiler" \
  "$(sha256sum "$fixture_root/usr/local/libexec/msys2-woarm64/woarm64-gcc" | cut -d' ' -f1)" \
  'compiler boundary is idempotent'
assert_equal "$first_launcher_source" \
  "$(sha256sum "$fixture_root/usr/local/libexec/msys2-woarm64/native-compiler-launcher.c" | cut -d' ' -f1)" \
  'native compiler launcher source is idempotent'
assert_equal "$before_makepkg" \
  "$(sha256sum "$fixture_root/etc/makepkg_mingw.conf" | cut -d' ' -f1)" \
  'setup does not patch makepkg_mingw.conf'
assert_equal "$before_msystem" \
  "$(sha256sum "$fixture_root/etc/msystem" | cut -d' ' -f1)" \
  'setup does not patch etc/msystem'
assert_equal "$before_wrapper" \
  "$(sha256sum "$fixture_root/usr/bin/makepkg-mingw" | cut -d' ' -f1)" \
  'setup does not patch makepkg-mingw'

fixture_gcc_native=$(to_native_path "$fixture_root/usr/local/libexec/msys2-woarm64/woarm64-gcc.exe")
unset CC CXX
source "$fixture_root/etc/makepkg_mingw.d/mingwarm64.conf"
assert_equal "$fixture_gcc_native" "$CC" \
  'makepkg config preserves the native compiler launcher path'
assert_file_contains "$fixture_root/etc/msystem.d/MINGWARM64" "MSYSTEM_PREFIX='/mingwarm64'"
if [[ ! -x "$fixture_root/usr/local/libexec/msys2-woarm64/woarm64-gcc" ]]; then
  echo "Assertion failed: native compiler boundary is not executable" >&2
  exit 1
fi
if find "$fixture_root" -name '*.rej' -print -quit | grep -q .; then
  echo "Assertion failed: semantic setup left patch reject files" >&2
  exit 1
fi

assert_equal 'C:/Program Files/$cache' \
  "$(to_native_path '/c/Program Files/$cache')" \
  'native conversion preserves spaces and a literal dollar'
assert_equal '/c/Program Files/$cache' \
  "$(to_msys_path 'C:\Program Files\$cache')" \
  'MSYS conversion preserves spaces and a literal dollar'
assert_equal '//server/share/path with spaces/$cache' \
  "$(to_native_path '//server/share/path with spaces/$cache')" \
  'native conversion preserves a UNC path'
assert_equal '//server/share/path with spaces/$cache' \
  "$(to_msys_path '\\server\share\path with spaces\$cache')" \
  'MSYS conversion preserves a UNC path'
leading_dash_expected="$(to_native_path "$PWD/-h")"
assert_equal "$leading_dash_expected" \
  "$(to_native_path '-h')" \
  'native conversion does not parse a leading-dash path as an option'

native_make=${NATIVE_MAKE:-/clangarm64/bin/mingw32-make.exe}
if [[ ! -x "$native_make" ]]; then
  echo "NATIVE_MAKE is not executable: $native_make" >&2
  exit 1
fi

make_root="$temporary_root/native-make-path"
mkdir -p "$make_root"
printf 'VALUE=converted\n' > "$make_root/included.mk"
posix_include=$(to_msys_path "$make_root/included.mk")
native_include=$(to_native_path "$make_root/included.mk")
makefile="$make_root/Makefile"

printf 'include %s\nall:\n\t@echo $(VALUE)\n' "$posix_include" > "$makefile"
if "$native_make" --no-print-directory -f "$(to_native_path "$makefile")" all >/dev/null 2>&1; then
  echo "Assertion failed: native Make unexpectedly accepted an MSYS /c path" >&2
  exit 1
fi

printf 'include %s\nall:\n\t@echo $(VALUE)\n' "$native_include" > "$makefile"
assert_equal 'converted' \
  "$("$native_make" --no-print-directory -f "$(to_native_path "$makefile")" all)" \
  'native Make accepts the centralized Windows path conversion'

compiler_root="$temporary_root/compiler path/\$cache"
mkdir -p "$compiler_root/deep/build" "$compiler_root/deep/source"
printf 'int value;\n' > "$compiler_root/deep/source/input.c"
printf 'object fixture\n' > "$compiler_root/deep/build/local-input.o"
capture="$temporary_root/compiler-arguments.txt"
fake_compiler="$temporary_root/fake-compiler"
cat > "$fake_compiler" <<'EOF'
#!/bin/bash
printf '%s\n' "$@" > "$WOARM64_ARGUMENT_CAPTURE"
EOF
chmod +x "$fake_compiler"
(
  cd "$compiler_root/deep/build"
  WOARM64_NATIVE_COMPILER_NAME=woarm64-gcc \
    WOARM64_NATIVE_COMPILER="$fake_compiler" \
    WOARM64_ARGUMENT_CAPTURE="$capture" \
    "$repo_root/.github/scripts/lib/native-compiler.sh" \
      -I- \
      -I'//server/share/path with spaces/$cache' \
      '-include../source/input.c' \
      '-MFdependency output/$value.d' \
      ../source/input.c \
      local-input.o \
      -o 'output with spaces/$value.o'
)
mapfile -t compiler_arguments < "$capture"
assert_equal '-I-' "${compiler_arguments[0]}" 'compiler boundary preserves GCC include semantics'
assert_equal '-I//server/share/path with spaces/$cache' \
  "${compiler_arguments[1]}" \
  'compiler boundary preserves UNC spaces and a literal dollar'
assert_equal "$(to_native_path "$compiler_root/deep/source/input.c")" \
  "${compiler_arguments[2]#-include}" \
  'compiler boundary normalizes a joined include path'
assert_equal "-MF$(to_native_path "$compiler_root/deep/build/dependency output/\$value.d")" \
  "${compiler_arguments[3]}" \
  'compiler boundary normalizes a joined dependency path'
assert_equal "$(to_native_path "$compiler_root/deep/source/input.c")" \
  "${compiler_arguments[4]}" \
  'compiler boundary normalizes an existing relative source'
assert_equal 'local-input.o' "${compiler_arguments[5]}" \
  'compiler boundary preserves a bare object for libtool filtering'
assert_equal '-o' "${compiler_arguments[6]}" 'compiler boundary preserves output option'
assert_equal "$(to_native_path "$compiler_root/deep/build/output with spaces/\$value.o")" \
  "${compiler_arguments[7]}" \
  'compiler boundary normalizes a non-existent output path'

bare_repository="$temporary_root/bare.git"
/usr/bin/git init --bare -q "$bare_repository"
source_repository="$temporary_root/source repository"
source_export="$temporary_root/source export"
mkdir -p "$source_repository" "$source_export"
/usr/bin/git -C "$source_repository" init -q
printf 'ARM64 tune evidence\nsecond line\n' > "$source_repository/aarch64-tune.md"
printf 'build() {\n  printf "LF only\\n"\n}\n' > "$source_repository/PKGBUILD"
/usr/bin/git -C "$source_repository" \
  -c user.name=bootstrap-test -c user.email=bootstrap@example.invalid \
  add aarch64-tune.md PKGBUILD
/usr/bin/git -C "$source_repository" \
  -c user.name=bootstrap-test -c user.email=bootstrap@example.invalid \
  commit -q -m fixture
export GIT_EXEC_PATH='C:\missing\git-core'
export GIT_CONFIG_PARAMETERS="'safe.bareRepository'='explicit'"
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=safe.bareRepository
export GIT_CONFIG_VALUE_0=explicit
poisoned_git_config="$temporary_root/poisoned.gitconfig"
printf '[core]\n\tautocrlf = true\n[safe]\n\tbareRepository = explicit\n' \
  > "$poisoned_git_config"
export GIT_CONFIG_GLOBAL="$poisoned_git_config"
export GIT_CONFIG_NOSYSTEM=0
export GIT_CONFIG_SYSTEM="$poisoned_git_config"
export GIT_CONFIG="$poisoned_git_config"
configure_stage0_git
assert_equal '/usr/lib/git-core' "$GIT_EXEC_PATH" 'stage-0 Git uses its matching helper tree'
assert_equal '1' "$GIT_CONFIG_COUNT" 'stage-0 Git installs one isolated setting'
assert_equal 'core.autocrlf' "$GIT_CONFIG_KEY_0" 'source exports disable checkout conversion'
assert_equal 'false' "$GIT_CONFIG_VALUE_0" 'source exports preserve Git blob bytes'
assert_equal '/dev/null' "$GIT_CONFIG_GLOBAL" 'host global Git config is disabled'
assert_equal '1' "$GIT_CONFIG_NOSYSTEM" 'host system Git config is disabled'
assert_equal '/dev/null' "$GIT_CONFIG_SYSTEM" 'Git system override is disabled'
if [[ -n "${GIT_CONFIG+x}" ]]; then
  echo "Assertion failed: repository Git config override remains set" >&2
  exit 1
fi
assert_equal 'true' \
  "$(/usr/bin/git -C "$bare_repository" rev-parse --is-bare-repository)" \
  'stage-0 Git can consume makepkg bare repositories'

/usr/bin/git -C "$source_repository" archive --format=tar HEAD |
  /usr/bin/tar -xf - -C "$source_export"
for exported_file in aarch64-tune.md PKGBUILD; do
  blob_hash=$(
    /usr/bin/git -C "$source_repository" cat-file blob "HEAD:$exported_file" |
      sha256sum |
      cut -d' ' -f1
  )
  assert_equal "$blob_hash" \
    "$(sha256sum "$source_export/$exported_file" | cut -d' ' -f1)" \
    "source export preserves the $exported_file Git blob"
done

echo "bootstrap regression tests passed"
