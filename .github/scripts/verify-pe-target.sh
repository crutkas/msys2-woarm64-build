#!/bin/bash

source `dirname ${BASH_SOURCE[0]}`/../../config.sh

BINARY=${1:?Usage: verify-pe-target.sh BINARY [REPORT]}
REPORT=${2:-hello-world-architecture.json}
TARGET_TRIPLET=${TARGET_TRIPLET:-aarch64-w64-mingw32}
COMPILER=${CC:-${TARGET_TRIPLET}-gcc}
OBJDUMP=${OBJDUMP:-${TARGET_TRIPLET}-objdump}

ACTUAL_TARGET=$("$COMPILER" -dumpmachine)
if [[ "$ACTUAL_TARGET" != "$TARGET_TRIPLET" ]]; then
  echo "Compiler target mismatch: expected $TARGET_TRIPLET, got $ACTUAL_TARGET" >&2
  exit 1
fi

DOS_MAGIC=$(od -An -tx1 -N2 "$BINARY" | tr -d '[:space:]')
if [[ "$DOS_MAGIC" != "4d5a" ]]; then
  echo "$BINARY is not a PE image: missing MZ header" >&2
  exit 1
fi

PE_OFFSET_BYTES=($(od -An -tx1 -j60 -N4 "$BINARY"))
if [[ ${#PE_OFFSET_BYTES[@]} -ne 4 ]]; then
  echo "Unable to read the PE header offset from $BINARY" >&2
  exit 1
fi

PE_OFFSET=$((0x${PE_OFFSET_BYTES[0]} |
  (0x${PE_OFFSET_BYTES[1]} << 8) |
  (0x${PE_OFFSET_BYTES[2]} << 16) |
  (0x${PE_OFFSET_BYTES[3]} << 24)))
PE_SIGNATURE=$(od -An -tx1 -j"$PE_OFFSET" -N4 "$BINARY" | tr -d '[:space:]')
if [[ "$PE_SIGNATURE" != "50450000" ]]; then
  echo "$BINARY is not a PE image: invalid PE signature" >&2
  exit 1
fi

MACHINE_BYTES=$(od -An -tx1 -j"$((PE_OFFSET + 4))" -N2 "$BINARY" | tr -d '[:space:]')
if [[ "$MACHINE_BYTES" != "64aa" ]]; then
  echo "$BINARY has PE machine bytes $MACHINE_BYTES; expected 64aa (ARM64)" >&2
  exit 1
fi

OBJDUMP_OUTPUT=$("$OBJDUMP" -f "$BINARY")
echo "$OBJDUMP_OUTPUT"
if ! grep -q "file format pei-aarch64-little" <<< "$OBJDUMP_OUTPUT"; then
  echo "$OBJDUMP did not identify $BINARY as pei-aarch64-little" >&2
  exit 1
fi

cat > "$REPORT" <<EOF
{
  "schema_version": 1,
  "verified": true,
  "file": "$(basename "$BINARY")",
  "format": "PE",
  "machine": "IMAGE_FILE_MACHINE_ARM64",
  "machine_hex": "0xaa64",
  "compiler": "$COMPILER",
  "compiler_target": "$ACTUAL_TARGET",
  "objdump_format": "pei-aarch64-little"
}
EOF
