#!/bin/bash

set -euo pipefail
export PATH="/usr/bin:/bin${PATH:+:$PATH}"

repo_root=$(realpath "$(dirname "${BASH_SOURCE[0]}")/../..")
source "$repo_root/.github/scripts/lib/native-tooling.sh"

if ! verify_native_tool_closure; then
  echo "BLOCKED: admitted native ARM64 tool closure is unavailable" >&2
  exit 77
fi

launcher=/usr/local/libexec/msys2-woarm64/woarm64-gcc.exe
if [[ ! -x "$launcher" ]]; then
  echo "BLOCKED: admitted native compiler launcher is unavailable: $launcher" >&2
  exit 77
fi

temporary_root=$(mktemp -d)
trap 'rm -rf "$temporary_root"' EXIT
capture="$temporary_root/compiler arguments"
fake_compiler="$temporary_root/fake compiler"
injection_marker="$temporary_root/injected"
launcher_stdout="$temporary_root/launcher.stdout"
launcher_stderr="$temporary_root/launcher.stderr"
printf 'object fixture\n' > "$temporary_root/relative-input.o"

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

assert_native_arm64_pe "$launcher" 'installed native compiler launcher'
grep -Fq 'launcher-identity-v4' \
  /usr/local/libexec/msys2-woarm64/native-compiler-launcher.identity

# Production runs under the pinned policy, not with conversion switched off.
export MSYS2_ARG_CONV_EXCL="$WOARM64_MSYS2_ARG_CONV_EXCL"
export WOARM64_NATIVE_COMPILER="$fake_compiler"
export WOARM64_LAUNCHER_CAPTURE="$capture"
export WOARM64_NATIVE_COMPILER_NAME=woarm64-g++
injection_argument="-DVALUE=literal;touch $injection_marker"
quoted_argument='-DQUOTED="value with space"\'

(
  cd "$temporary_root"
  "$launcher" \
    -I'//server/share/path with spaces/$cache' \
    "$injection_argument" \
    "$quoted_argument" \
    '' \
    relative-input.o \
    -o "$temporary_root/output with spaces/\$value.o"
) >"$launcher_stdout" 2>"$launcher_stderr"

grep -Fx 'fake compiler stdout' "$launcher_stdout" >/dev/null
grep -Fx 'fake compiler stderr' "$launcher_stderr" >/dev/null
assert_capture 'name=woarm64-gcc'
assert_capture 'arg=-I//server/share/path with spaces/$cache'
assert_capture "arg=$injection_argument"
assert_capture "arg=$quoted_argument"
assert_capture 'arg='
assert_capture 'arg=relative-input.o'
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
unset WOARM64_FAKE_COMPILER_STATUS

# The payload dialects have to survive the real MSYS2 -> native PE boundary
# identically under the production policy and with the runtime heuristic fully
# enabled. Anything that depends on which of the two is active would be a latent
# gettext link failure.
payload_root="$temporary_root/payload"
mkdir -p "$payload_root/.libs"
printf 'archive\n' > "$payload_root/.libs/libgettextlib.a"
payload_native=$(to_native_path "$payload_root")

collect_payload_arguments() {
  local excl_mode=$1
  shift

  if [[ "$excl_mode" == "policy" ]]; then
    MSYS2_ARG_CONV_EXCL="$WOARM64_MSYS2_ARG_CONV_EXCL" "$launcher" "$@" >/dev/null 2>&1
  else
    env -u MSYS2_ARG_CONV_EXCL "$launcher" "$@" >/dev/null 2>&1
  fi
  grep '^arg=' "$capture"
}

# The full production matrix, not just the payload dialects. The simple classes
# are converted by the MSYS2 runtime under both settings; the payload dialects
# are excluded under the production policy and converted by the boundary. Either
# way the compiler must see the same thing.
payload_arguments=(
  "-I$payload_root/.libs"
  "-L$payload_root/.libs"
  "-DLOCALEDIR=\"$payload_root/.libs\""
  "$payload_root/.libs/libgettextlib.a"
  "bare-object.o"
  "-o" "$payload_root/.libs/out.o"
  "-Wl,--out-implib,$payload_root/.libs/libgettextlib.a"
  "-Wl,--whole-archive"
  "-Wl,--wrap,malloc"
  "-Xlinker" "--out-implib" "-Xlinker" "$payload_root/.libs/libgettextlib.a"
  "-Wp,-MD,$payload_root/.libs/scratch.d"
  "-Wa,-I,$payload_root/.libs"
  "-specs=$payload_root/native.specs"
)

policy_capture=$(collect_payload_arguments policy "${payload_arguments[@]}")
converted_capture=$(collect_payload_arguments converted "${payload_arguments[@]}")

if [[ "$policy_capture" != "$converted_capture" ]]; then
  echo "Argument conversion differs between the production policy and full runtime conversion" >&2
  printf 'policy:\n%s\nconverted:\n%s\n' "$policy_capture" "$converted_capture" >&2
  exit 1
fi

# Simple classes: the runtime is the intended owner, so assert the compiler
# really does receive the native form.
grep -Fx "arg=-I$payload_native/.libs" <<< "$policy_capture" >/dev/null
grep -Fx "arg=-L$payload_native/.libs" <<< "$policy_capture" >/dev/null
grep -Fx "arg=-DLOCALEDIR=\"$payload_native/.libs\"" <<< "$policy_capture" >/dev/null
grep -Fx "arg=$payload_native/.libs/libgettextlib.a" <<< "$policy_capture" >/dev/null
grep -Fx "arg=bare-object.o" <<< "$policy_capture" >/dev/null
grep -Fx "arg=$payload_native/.libs/out.o" <<< "$policy_capture" >/dev/null

# Payload dialects: the boundary is the intended owner.
grep -Fx "arg=-Wl,--out-implib,$payload_native/.libs/libgettextlib.a" \
  <<< "$policy_capture" >/dev/null
grep -Fx "arg=-Wl,--whole-archive" <<< "$policy_capture" >/dev/null
grep -Fx "arg=-Wl,--wrap,malloc" <<< "$policy_capture" >/dev/null
grep -Fx "arg=-Wp,-MD,$payload_native/.libs/scratch.d" <<< "$policy_capture" >/dev/null
grep -Fx "arg=-Wa,-I,$payload_native/.libs" <<< "$policy_capture" >/dev/null
grep -Fx "arg=-specs=$payload_native/native.specs" <<< "$policy_capture" >/dev/null

echo "native compiler launcher tests passed"
