#!/bin/bash

# Shared fixtures for the native boundary regressions.
#
# These build synthetic PE images so the identity gates can be exercised on any
# Windows host, including an AMD64 runner with no ARM64 toolchain installed. A
# real ARM64 binary cannot be executed there, which is exactly why the gates
# read the PE machine word instead of running the tool.

WOARM64_FIXTURE_TOOLS=(ar as dlltool ld nm objcopy objdump ranlib strip windres)

# Minimal but structurally valid image: MZ header, e_lfanew at 0x3c pointing at
# 0x40, the PE signature, and a COFF header whose Machine field carries the
# requested value in little-endian order.
make_pe_image() {
  local path=$1
  local machine=${2:-aa64}
  local low=${machine:2:2}
  local high=${machine:0:2}

  mkdir -p "$(dirname "$path")"
  {
    printf 'MZ'
    head -c 58 /dev/zero
    printf '\x40\x00\x00\x00'
    printf 'PE\x00\x00'
    printf "\\x$low\\x$high"
    head -c 18 /dev/zero
  } > "$path"
  chmod 0755 "$path"
}

# Appends bytes so the file digest changes while the PE header stays valid.
perturb_pe_image() {
  local path=$1
  local marker=${2:-x}

  printf '%s' "$marker" >> "$path"
}

make_native_tool_fixtures() {
  local bindir=$1
  local machine=${2:-aa64}
  local tool

  mkdir -p "$bindir"
  make_pe_image "$bindir/gcc.exe" "$machine"
  perturb_pe_image "$bindir/gcc.exe" 'gcc'
  for tool in "${WOARM64_FIXTURE_TOOLS[@]}"; do
    make_pe_image "$bindir/$tool.exe" "$machine"
    perturb_pe_image "$bindir/$tool.exe" "$tool"
  done
}

# Stands in for the native GCC driver. It parses the last -o value, converts it
# back from the Windows form the boundary produced, and emits a synthetic ARM64
# image so the installed launcher passes its own identity check. Every call is
# recorded so a test can assert whether a rebuild happened.
make_fake_launcher_compiler() {
  local path=$1
  local counter=$2

  mkdir -p "$(dirname "$path")"
  cat > "$path" <<'EOF'
#!/bin/bash
set -e
output=
previous=
for argument in "$@"; do
  if [[ "$previous" == "-o" ]]; then
    output=$argument
  fi
  previous=$argument
done
if [[ -z "$output" ]]; then
  echo "fake launcher compiler received no -o" >&2
  exit 1
fi
printf 'call\n' >> "$WOARM64_FAKE_COMPILER_COUNTER"
if [[ "${WOARM64_FAKE_COMPILER_FAIL:-0}" == "1" ]]; then
  exit 1
fi
output=$(cygpath -u -- "$output")
mkdir -p "$(dirname "$output")"
{
  printf 'MZ'
  head -c 58 /dev/zero
  printf '\x40\x00\x00\x00'
  printf 'PE\x00\x00'
  printf '\x64\xaa'
  head -c 18 /dev/zero
} > "$output"
chmod 0755 "$output"
EOF
  chmod 0755 "$path"
  : > "$counter"
}

fake_compiler_call_count() {
  local counter=$1

  if [[ ! -f "$counter" ]]; then
    printf '0\n'
    return 0
  fi
  printf '%s\n' "$(wc -l < "$counter" | tr -d ' ')"
}

# Records the arguments a compiler boundary produced, one per line.
make_capturing_compiler() {
  local path=$1

  mkdir -p "$(dirname "$path")"
  cat > "$path" <<'EOF'
#!/bin/bash
printf '%s\n' "$@" > "$WOARM64_ARGUMENT_CAPTURE"
# The boundary removes a rewritten response file as soon as the compiler
# returns, so snapshot its contents here while it still exists.
if [[ -n "${WOARM64_RESPONSE_CAPTURE:-}" ]]; then
  : > "$WOARM64_RESPONSE_CAPTURE"
  for argument in "$@"; do
    if [[ "$argument" == @* ]]; then
      cat "$(cygpath -u -- "${argument#@}")" >> "$WOARM64_RESPONSE_CAPTURE" 2>/dev/null || true
    fi
  done
fi
EOF
  chmod 0755 "$path"
}
