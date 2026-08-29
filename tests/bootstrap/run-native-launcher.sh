#!/bin/bash

set -euo pipefail
export PATH="/usr/bin:/bin${PATH:+:$PATH}"

repo_root=$(realpath "$(dirname "${BASH_SOURCE[0]}")/../..")
source "$repo_root/.github/scripts/lib/native-tooling.sh"

if [[ ! -x /mingwarm64/bin/gcc.exe ]]; then
  echo "Native ARM64 GCC is required for launcher tests" >&2
  exit 1
fi

temporary_root=$(mktemp -d)
trap 'rm -rf "$temporary_root"' EXIT
capture="$temporary_root/compiler arguments"
fake_compiler="$temporary_root/fake compiler"
injection_marker="$temporary_root/injected"
launcher_stdout="$temporary_root/launcher.stdout"
launcher_stderr="$temporary_root/launcher.stderr"

assert_capture() {
  local expected=$1
  if ! grep -Fx "$expected" "$capture" >/dev/null; then
    echo "Launcher capture is missing: $expected" >&2
    cat "$capture" >&2
    exit 1
  fi
}

cat > "$fake_compiler" <<'EOF'
#!/bin/bash
{
  printf 'name=%s\n' "$WOARM64_NATIVE_COMPILER_NAME"
  printf 'tmp=%s\n' "$TMP"
  printf 'arg=%s\n' "$@"
} > "$WOARM64_LAUNCHER_CAPTURE"
printf 'fake compiler stdout\n'
printf 'fake compiler stderr\n' >&2
exit "${WOARM64_FAKE_COMPILER_STATUS:-0}"
EOF
chmod 0755 "$fake_compiler"

ensure_native_compiler_launchers
launcher=/usr/local/libexec/msys2-woarm64/woarm64-gcc.exe
[[ -x "$launcher" ]]

export MSYS2_ARG_CONV_EXCL='*'
export WOARM64_NATIVE_COMPILER="$fake_compiler"
export WOARM64_LAUNCHER_CAPTURE="$capture"
export WOARM64_NATIVE_COMPILER_NAME=woarm64-g++
injection_argument="-DVALUE=literal;touch $injection_marker"
quoted_argument='-DQUOTED="value with space"\'

"$launcher" \
  -I'//server/share/path with spaces/$cache' \
  "$injection_argument" \
  "$quoted_argument" \
  '' \
  -o "$temporary_root/output with spaces/\$value.o" \
  >"$launcher_stdout" 2>"$launcher_stderr"

grep -Fx 'fake compiler stdout' "$launcher_stdout" >/dev/null
grep -Fx 'fake compiler stderr' "$launcher_stderr" >/dev/null
assert_capture 'name=woarm64-gcc'
assert_capture 'arg=-I//server/share/path with spaces/$cache'
assert_capture "arg=$injection_argument"
assert_capture "arg=$quoted_argument"
assert_capture 'arg='
assert_capture "arg=$(to_native_path "$temporary_root/output with spaces/\$value.o")"
grep -E '^tmp=[A-Za-z]:/' "$capture" >/dev/null
[[ ! -e "$injection_marker" ]]

export WOARM64_FAKE_COMPILER_STATUS=37
set +e
"$launcher" --version >/dev/null 2>&1
launcher_status=$?
set -e
if [[ $launcher_status -ne 37 ]]; then
  echo "Launcher did not preserve compiler exit code 37: $launcher_status" >&2
  exit 1
fi

echo "native compiler launcher tests passed"
