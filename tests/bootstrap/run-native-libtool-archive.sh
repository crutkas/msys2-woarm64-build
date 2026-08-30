#!/bin/bash

set -euo pipefail
export PATH="/usr/bin:/bin:/mingwarm64/bin${PATH:+:$PATH}"

repo_root=$(realpath "$(dirname "${BASH_SOURCE[0]}")/../..")
source "$repo_root/.github/scripts/lib/path-boundary.sh"
source "$repo_root/.github/scripts/lib/native-recipe-root.sh"
source "$repo_root/tests/bootstrap/lib/native-fixtures.sh"

native_ar=/mingwarm64/bin/ar.exe
if [[ ! -x "$native_ar" ]]; then
  echo "Native ARM64 ar is required for the libtool archive regression" >&2
  exit 1
fi
if ! file "$native_ar" | grep -F 'ARM64' >/dev/null; then
  echo "The libtool archive regression requires an ARM64 ar.exe" >&2
  exit 1
fi
legacy_native_ar=${LEGACY_NATIVE_AR:-$native_ar}
if [[ ! -x "$legacy_native_ar" ]]; then
  echo "LEGACY_NATIVE_AR is not executable: $legacy_native_ar" >&2
  exit 1
fi
if ! file "$legacy_native_ar" | grep -F 'ARM64' >/dev/null; then
  echo "LEGACY_NATIVE_AR must be an ARM64 ar.exe" >&2
  exit 1
fi

temporary_root=$(mktemp -d)
test_process=$BASHPID
cleanup_test_root() {
  if [[ $BASHPID -eq $test_process ]]; then
    rm -rf "$temporary_root"
  fi
}
trap cleanup_test_root EXIT
recipe_root="$temporary_root/mingw-w64-gettext"
while :; do
  recipe_root_native=$(to_native_path "$recipe_root")
  if (( ${#recipe_root_native} + WOARM64_NATIVE_RECIPE_PATH_RESERVE_DEFAULT > 259 )); then
    break
  fi
  recipe_root="${recipe_root}x"
done
control_root="$recipe_root/control"
archive_root="$recipe_root/src/build-MINGWARM64-static/gettext-tools/gnulib-lib/.libs"
extract_root="$recipe_root/src/build-MINGWARM64-static/gettext-tools/src/.libs"
member=libgettextlib_la-scratch_buffer_grow_preserve.o

mkdir -p "$control_root" "$archive_root"
printf 'native libtool archive path fixture\n' > "$control_root/$member"
(
  cd "$control_root"
  "$native_ar" rcs "$archive_root/libgettextlib.a" "$member"
)
grep -Fx "$member" <("$native_ar" t "$archive_root/libgettextlib.a") >/dev/null
rm -f "$control_root/$member"
(
  cd "$control_root"
  "$native_ar" x "$archive_root/libgettextlib.a" "$member"
)
[[ -f "$control_root/$member" ]]

deep_component=libgettextsrc
while :; do
  failing_root="$extract_root/$deep_component.lax/libgettextlib.a"
  failing_output_native=$(to_native_path "$failing_root/$member")
  if (( ${#failing_output_native} > 259 )); then
    break
  fi
  deep_component="${deep_component}x"
done
mkdir -p "$failing_root"

if [[ "$legacy_native_ar" != "$native_ar" ]]; then
  (
    cd "$failing_root"
    "$native_ar" x "$archive_root/libgettextlib.a" "$member"
  )
  [[ -f "$failing_root/$member" ]]
  rm -f "$failing_root/$member"
fi

set +e
(
  cd "$failing_root"
  "$legacy_native_ar" x "$archive_root/libgettextlib.a" "$member"
) >/dev/null 2>&1
old_status=$?
set -e
old_reproduced=1
if [[ $old_status -eq 0 || -e "$failing_root/$member" ]]; then
  if [[ -n "${LEGACY_NATIVE_AR:-}" ]]; then
    echo "The explicit legacy native ar did not reproduce the path boundary" >&2
    exit 1
  fi
  old_reproduced=0
  rm -f "$failing_root/$member"
fi

printf '# path-boundary fixture\n' > "$recipe_root/PKGBUILD"
relative_archive=${archive_root#"$recipe_root/"}
relative_extract=${failing_root#"$recipe_root/"}
export legacy_native_ar member relative_archive relative_extract
native_recipe_root_needs_alias "$recipe_root"
if native_recipe_root_needs_alias /c; then
  echo "A short native recipe path unexpectedly requires an alias" >&2
  exit 1
fi
set +e
WOARM64_NATIVE_RECIPE_PATH_RESERVE=0 native_recipe_root_needs_alias "$recipe_root"
invalid_reserve_status=$?
set -e
if [[ $invalid_reserve_status -ne 2 ]]; then
  echo "Invalid native recipe path reserve was not rejected" >&2
  exit 1
fi
export WOARM64_SUBST_DRIVES=Z
if [[ -e /z ]]; then
  echo "Drive Z is required for the isolated libtool archive regression" >&2
  exit 1
fi
(
  cd "$recipe_root"
  with_short_native_recipe_root bash -c '
    set -e
    cd "$relative_extract"
    "$legacy_native_ar" x "/z/$relative_archive/libgettextlib.a" "$member"
    test -f "$member"
    fixed_output_native=$(cygpath -am "$PWD/$member")
    test "${#fixed_output_native}" -le 259
  '
)
if [[ -e /z ]]; then
  echo "Native recipe alias Z was not removed" >&2
  exit 1
fi

set +e
(
  cd "$recipe_root"
  with_short_native_recipe_root bash -c 'exit 37'
) >/dev/null 2>&1
failure_status=$?
set -e
if [[ $failure_status -ne 37 || -e /z ]]; then
  echo "Native recipe alias did not preserve failure status and clean up" >&2
  exit 1
fi

set +e
(
  cd "$recipe_root"
  with_short_native_recipe_root bash -c 'kill -KILL $$'
) >/dev/null 2>&1
crash_status=$?
set -e
if [[ $crash_status -ne 137 || -e /z ]]; then
  echo "Native recipe alias did not clean up after its child crashed" >&2
  exit 1
fi

second_recipe_root="$temporary_root/second/mingw-w64-gettext"
mkdir -p "$second_recipe_root"
printf '# second path-boundary fixture\n' > "$second_recipe_root/PKGBUILD"
first_ready="$temporary_root/first.ready"
first_release="$temporary_root/first.release"
first_capture="$temporary_root/first.capture"
second_capture="$temporary_root/second.capture"
export first_ready first_release first_capture second_capture
(
  cd "$recipe_root"
  WOARM64_SUBST_DRIVES='Y X' with_short_native_recipe_root bash -c '
    cygpath -am . > "$first_capture"
    touch "$first_ready"
    while [[ ! -e "$first_release" ]]; do sleep 0.05; done
  '
) &
first_pid=$!
for _ in {1..200}; do
  [[ -e "$first_ready" ]] && break
  sleep 0.05
done
if [[ ! -e "$first_ready" ]]; then
  echo "First parallel native recipe alias did not start" >&2
  exit 1
fi
(
  cd "$second_recipe_root"
  WOARM64_SUBST_DRIVES='Y X' with_short_native_recipe_root \
    bash -c 'cygpath -am . > "$second_capture"'
)
grep -Fx 'Y:/' "$first_capture" >/dev/null
grep -Fx 'X:/' "$second_capture" >/dev/null
touch "$first_release"
wait "$first_pid"
if [[ -e /x || -e /y ]]; then
  echo "Parallel native recipe aliases were not removed" >&2
  exit 1
fi

signal_runner="$temporary_root/signal-runner"
cat > "$signal_runner" <<'EOF'
#!/bin/bash
set -e
source "$HELPER_PATH"
cd "$RECIPE_ROOT"
WOARM64_SUBST_DRIVES=Z with_short_native_recipe_root \
  bash -c '
    trap "exit 0" HUP INT TERM
    echo "$$" > "$signal_child"
    echo "$MSYS2_WOARM64_RECIPE_HELPER_PID" > "$signal_helper"
    touch "$signal_ready"
    kill -s "$SIGNAL_TO_SEND" "$MSYS2_WOARM64_RECIPE_HELPER_PID"
    while :; do sleep 1; done
  '
EOF
chmod +x "$signal_runner"
export HELPER_PATH="$repo_root/.github/scripts/lib/native-recipe-root.sh"
export RECIPE_ROOT="$recipe_root"

for signal_spec in 'HUP 129' 'TERM 143'; do
  read -r signal expected_status <<< "$signal_spec"
  signal_ready="$temporary_root/$signal.ready"
  signal_child="$temporary_root/$signal.child"
  signal_helper="$temporary_root/$signal.helper"
  export signal_ready signal_child signal_helper SIGNAL_TO_SEND="$signal"
  set +e
  /usr/bin/bash "$signal_runner" >/dev/null 2>&1
  signal_status=$?
  set -e
  if [[ $signal_status -ne 0 && $signal_status -ne $expected_status ]] || [[ -e /z ]]; then
    echo "Native recipe alias did not clean up after $signal: status $signal_status" >&2
    exit 1
  fi
  if kill -0 "$(< "$signal_child")" 2>/dev/null; then
    echo "Native recipe alias did not forward $signal to its child" >&2
    exit 1
  fi
done

fake_bin="$temporary_root/fake-bin"
driver_capture="$temporary_root/driver.capture"
mkdir -p "$fake_bin"
cat > "$fake_bin/ccache" <<'EOF'
#!/bin/bash
exit 0
EOF
cat > "$fake_bin/makepkg-mingw" <<'EOF'
#!/bin/bash
printf 'cwd=%s\n' "$(cygpath -am .)" > "$DRIVER_CAPTURE"
printf 'arg=%s\n' "$@" >> "$DRIVER_CAPTURE"
EOF
chmod +x "$fake_bin/ccache" "$fake_bin/makepkg-mingw"

# The driver now gates on the pinned tool closure and on a launcher whose cache
# identity covers that closure. Give it synthetic ARM64 fixtures so this test
# keeps exercising the alias plumbing rather than the host toolchain.
driver_tool_bin="$temporary_root/driver-bin"
driver_launcher_dir="$temporary_root/driver-libexec"
driver_fake_compiler="$temporary_root/driver-gcc"
driver_compiler_calls="$temporary_root/driver-gcc.calls"
make_native_tool_fixtures "$driver_tool_bin" aa64
mkdir -p "$driver_launcher_dir"
cp -f "$repo_root/.github/scripts/lib/native-compiler-launcher.c" \
  "$driver_launcher_dir/native-compiler-launcher.c"
make_fake_launcher_compiler "$driver_fake_compiler" "$driver_compiler_calls"

driver_environment=(
  PATH="$driver_tool_bin:$fake_bin:$PATH"
  DRIVER_CAPTURE="$driver_capture"
  FLAVOR=NATIVE_WITH_NATIVE
  CLEAN_BUILD=1
  INSTALL_PACKAGE=1
  WOARM64_SUBST_DRIVES=Z
  WOARM64_NATIVE_BIN="$driver_tool_bin"
  WOARM64_TOOL_VERSION_PROBE=0
  WOARM64_LAUNCHER_INSTALL_DIR="$driver_launcher_dir"
  WOARM64_NATIVE_LAUNCHER_COMPILER="$driver_fake_compiler"
  WOARM64_FAKE_COMPILER_COUNTER="$driver_compiler_calls"
)

(
  cd "$recipe_root"
  env "${driver_environment[@]}" "$repo_root/.github/scripts/build-package.sh" MINGW
)
grep -Fx 'cwd=Z:/' "$driver_capture" >/dev/null
grep -Fx 'arg=--cleanbuild' "$driver_capture" >/dev/null
grep -Fx 'arg=--install' "$driver_capture" >/dev/null
if [[ -e /z ]]; then
  echo "Native package driver did not remove its recipe alias" >&2
  exit 1
fi
if [[ ! -x "$driver_launcher_dir/woarm64-gcc.exe" ]]; then
  echo "Native package driver did not provision its compiler launchers" >&2
  exit 1
fi

# Alias residue in staged output has to fail the driver: the drive letter is
# whichever candidate was free, so the recorded path is irreproducible.
mkdir -p "$recipe_root/pkg/mingwarm64/lib"
printf "libdir='Z:/src/build/.libs'\n" > "$recipe_root/pkg/mingwarm64/lib/leak.la"
set +e
(
  cd "$recipe_root"
  env "${driver_environment[@]}" "$repo_root/.github/scripts/build-package.sh" MINGW
) >/dev/null 2>&1
residue_status=$?
set -e
if [[ $residue_status -eq 0 ]]; then
  echo "Native package driver accepted staged output containing alias residue" >&2
  exit 1
fi
rm -rf "$recipe_root/pkg"
if [[ -e /z ]]; then
  echo "Native package driver did not remove its recipe alias after residue detection" >&2
  exit 1
fi

printf 'old_output_length=%s old_exit=%s old_reproduced=%s fixed=present\n' \
  "${#failing_output_native}" "$old_status" "$old_reproduced"
echo "native libtool archive regression passed"
