#!/bin/bash

if [[ -n "${MSYS2_WOARM64_NATIVE_TOOLCHAIN_SH:-}" ]]; then
  return 0
fi
readonly MSYS2_WOARM64_NATIVE_TOOLCHAIN_SH=1

# The native tool closure the NATIVE_WITH_NATIVE flavor pins explicitly. Every
# entry is resolved to an absolute path in the makepkg drop-in, and every entry
# is identity-checked before a package build starts. This lane must never reach
# a build tool through a PATH search.
WOARM64_NATIVE_TOOLS=(ar as dlltool ld nm objcopy objdump ranlib strip windres)

# PE IMAGE_FILE_MACHINE values. Only pure ARM64 is admissible here: ARM64EC and
# ARM64X images carry x86-64 ABI code behind an ARM64-looking name, so a `file`
# style substring match on "ARM64" would accept them.
WOARM64_PE_MACHINE_ARM64=0xaa64
WOARM64_PE_MACHINE_ARM64EC=0xa641
WOARM64_PE_MACHINE_ARM64X=0xa64e

native_tool_bindir() {
  printf '%s\n' "${WOARM64_NATIVE_BIN:-/mingwarm64/bin}"
}

native_tool_path() {
  if [[ $# -ne 1 || -z "$1" ]]; then
    echo "native_tool_path requires one tool name" >&2
    return 2
  fi

  printf '%s/%s.exe\n' "$(native_tool_bindir)" "$1"
}

native_launcher_compiler_path() {
  printf '%s\n' "${WOARM64_NATIVE_LAUNCHER_COMPILER:-$(native_tool_bindir)/gcc.exe}"
}

# Reads IMAGE_FILE_HEADER.Machine straight out of the PE image instead of
# trusting a human-readable tool description. Every offset is bounds-checked
# against the real file size, so a truncated or hostile image cannot make the
# machine word be read from an unchecked location.
native_pe_machine() {
  local image=$1
  local -a header=()
  local lfanew
  local size

  if [[ $# -ne 1 || -z "$image" ]]; then
    echo "native_pe_machine requires one image path" >&2
    return 2
  fi
  if [[ ! -f "$image" ]]; then
    echo "Not a regular file: $image" >&2
    return 2
  fi
  if ! size=$(stat -c %s -- "$image") || [[ ! "$size" =~ ^[0-9]+$ ]]; then
    echo "Unable to size the image: $image" >&2
    return 1
  fi
  if (( size < 64 )); then
    echo "Truncated image, smaller than a DOS header: $image" >&2
    return 1
  fi

  read -r -a header <<< "$(od -An -tx1 -j 0 -N 2 -- "$image")"
  if [[ ${#header[@]} -ne 2 || "${header[0]}" != "4d" || "${header[1]}" != "5a" ]]; then
    echo "Missing MZ signature: $image" >&2
    return 1
  fi

  read -r -a header <<< "$(od -An -tx1 -j 60 -N 4 -- "$image")"
  if [[ ${#header[@]} -ne 4 ]]; then
    echo "Truncated DOS header: $image" >&2
    return 1
  fi
  lfanew=$((16#${header[3]}${header[2]}${header[1]}${header[0]}))
  # The PE signature and the two machine bytes must both be inside the file.
  if (( lfanew < 4 || lfanew > size - 6 )); then
    echo "PE header offset $lfanew is outside $image" >&2
    return 1
  fi

  read -r -a header <<< "$(od -An -tx1 -j "$lfanew" -N 6 -- "$image")"
  if [[ ${#header[@]} -ne 6 ]]; then
    echo "Truncated PE header: $image" >&2
    return 1
  fi
  if [[ "${header[0]}${header[1]}${header[2]}${header[3]}" != "50450000" ]]; then
    echo "Missing PE signature: $image" >&2
    return 1
  fi

  printf '0x%04x\n' "$((16#${header[5]}${header[4]}))"
}

assert_native_arm64_pe() {
  local image=$1
  local label=${2:-$1}
  local machine

  if ! machine=$(native_pe_machine "$image"); then
    echo "Not a readable PE image: $label" >&2
    return 1
  fi

  case "$machine" in
    "$WOARM64_PE_MACHINE_ARM64")
      return 0
      ;;
    "$WOARM64_PE_MACHINE_ARM64EC")
      echo "Rejected ARM64EC image ($machine) where pure ARM64 is required: $label" >&2
      return 1
      ;;
    "$WOARM64_PE_MACHINE_ARM64X")
      echo "Rejected ARM64X image ($machine) where pure ARM64 is required: $label" >&2
      return 1
      ;;
  esac

  echo "Rejected PE machine $machine where $WOARM64_PE_MACHINE_ARM64 is required: $label" >&2
  return 1
}

native_tool_version() {
  local image=$1
  local output

  if [[ "${WOARM64_TOOL_VERSION_PROBE:-1}" != "1" ]]; then
    printf 'version-probe-disabled\n'
    return 0
  fi

  output=$("$image" --version 2>/dev/null) || output=
  output=${output%%$'\n'*}
  output=${output//$'\r'/}
  if [[ -z "$output" ]]; then
    return 1
  fi

  printf '%s\n' "$output"
}

# Rejects an AMD64 or otherwise foreign tool that would win a bare-name lookup.
# makepkg internals and configure scripts still call `strip`, `objdump` and
# friends by bare name, so pinning the drop-in variables is not sufficient on
# its own. Only the first effective resolution matters: a later /usr/bin entry
# of the same name is harmless once the pinned tool already wins.
assert_native_tool_unshadowed() {
  local tool=$1
  local pinned=$2
  local resolved

  resolved=$(type -P -- "$tool" 2>/dev/null) || resolved=
  if [[ -z "$resolved" ]]; then
    echo "Pinned native tool $tool does not resolve on PATH; a bare-name build step would fail" >&2
    return 1
  fi
  if [[ ! "$resolved" -ef "$pinned" ]]; then
    echo "PATH resolves $tool to $resolved before the pinned $pinned" >&2
    return 1
  fi
}

# Both compiler drivers are gated as well as the binutils closure: a launcher
# built by a foreign g++ is just as unusable as one built by a foreign gcc.
native_compiler_drivers() {
  printf '%s\n' "$(native_launcher_compiler_path)"
  printf '%s\n' "${WOARM64_NATIVE_CXX:-$(native_tool_bindir)/g++.exe}"
}

# Fails closed on the first problem but keeps going so one run reports the whole
# broken closure instead of one tool at a time.
verify_native_tool_closure() {
  local manifest=${WOARM64_TOOL_MANIFEST:-}
  local tool path digest version driver
  local status=0
  local -a records=()

  while IFS= read -r driver; do
    if [[ ! -f "$driver" ]]; then
      echo "Native compiler driver is missing: $driver" >&2
      status=1
      continue
    fi
    if ! assert_native_arm64_pe "$driver" "$driver"; then
      status=1
      continue
    fi
    if ! digest=$(sha256sum -- "$driver" | cut -d' ' -f1) || [[ -z "$digest" ]]; then
      echo "Unable to digest the native compiler driver: $driver" >&2
      status=1
      continue
    fi
    if ! version=$(native_tool_version "$driver"); then
      echo "Native compiler driver did not report a version: $driver" >&2
      status=1
      continue
    fi
    records+=("${driver##*/} $digest $version")
  done < <(native_compiler_drivers)

  for tool in "${WOARM64_NATIVE_TOOLS[@]}"; do
    path=$(native_tool_path "$tool")

    if [[ ! -f "$path" ]]; then
      echo "Pinned native tool is missing: $path" >&2
      status=1
      continue
    fi
    if ! assert_native_arm64_pe "$path" "$tool"; then
      status=1
      continue
    fi
    if ! digest=$(sha256sum -- "$path" | cut -d' ' -f1) || [[ -z "$digest" ]]; then
      echo "Unable to digest the pinned native tool: $path" >&2
      status=1
      continue
    fi
    if ! version=$(native_tool_version "$path"); then
      echo "Pinned native tool did not report a version: $path" >&2
      status=1
      continue
    fi
    if ! assert_native_tool_unshadowed "$tool" "$path"; then
      status=1
      continue
    fi

    records+=("$tool $digest $version")
  done

  if [[ $status -ne 0 ]]; then
    echo "Native ARM64 tool closure verification failed" >&2
    return 1
  fi

  printf '::group::Native ARM64 tool closure\n'
  printf '%s\n' "${records[@]}"
  printf '::endgroup::\n'
  if [[ -n "$manifest" ]]; then
    printf '%s\n' "${records[@]}" > "$manifest"
  fi
}

# Composite identity of everything that can change the bytes of a locally built
# private tool: both native compiler drivers plus the full binutils closure they
# call through. Binding the launcher cache to this is what stops a launcher
# emitted by a revoked assembler or linker from surviving a toolchain swap.
native_toolchain_identity_digest() {
  local tool entry name path digest driver
  local -a inputs=()
  local material=
  local result

  while IFS= read -r driver; do
    inputs+=("driver:$driver")
  done < <(native_compiler_drivers)
  for tool in "${WOARM64_NATIVE_TOOLS[@]}"; do
    inputs+=("$tool:$(native_tool_path "$tool")")
  done

  # Built without a pipeline so a missing or unreadable input fails the whole
  # digest instead of silently hashing a truncated record set.
  for entry in "${inputs[@]}"; do
    name=${entry%%:*}
    path=${entry#*:}
    if [[ ! -f "$path" ]]; then
      echo "Toolchain identity input is missing: $path" >&2
      return 1
    fi
    if ! digest=$(sha256sum -- "$path" | cut -d' ' -f1) || [[ -z "$digest" ]]; then
      echo "Unable to digest the toolchain identity input: $path" >&2
      return 1
    fi
    material+="$name/${path##*/}=$digest"$'\n'
  done

  if ! result=$(printf '%s' "$material" | sha256sum | cut -d' ' -f1) || [[ -z "$result" ]]; then
    return 1
  fi
  printf '%s\n' "$result"
}
