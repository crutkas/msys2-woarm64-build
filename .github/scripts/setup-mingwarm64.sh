#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/../../config.sh"
source "$(dirname "${BASH_SOURCE[0]}")/lib/path-boundary.sh"

MSYS2_ROOT="$(to_msys_path "${MSYS2_ROOT:-/}")"
MSYS2_ROOT_PREFIX="${MSYS2_ROOT%/}"
SCRIPT_DIR="$(to_msys_path "$(dirname "${BASH_SOURCE[0]}")")"

require_line() {
  local file=$1
  local text=$2

  if [[ ! -f "$file" ]] || ! grep -Fq "$text" "$file"; then
    echo "Unsupported MSYS2 base: $file does not provide '$text'" >&2
    return 1
  fi
}

write_managed_file() {
  local target=$1
  local mode=${2:-0644}
  local temporary

  mkdir -p "$(dirname "$target")"
  temporary=$(mktemp "${target}.tmp.XXXXXX")
  cat > "$temporary"
  chmod "$mode" "$temporary"

  if [[ -f "$target" ]] && cmp -s "$target" "$temporary"; then
    rm -f "$temporary"
    chmod "$mode" "$target"
    echo "Already configured: $target"
  else
    mv -f "$temporary" "$target"
    echo "Configured: $target"
  fi
}

disable_makepkg_option() {
  local target=$1
  local option=$2
  local line
  local changed=0
  local found=0
  local temporary

  temporary=$(mktemp "${target}.tmp.XXXXXX")
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == OPTIONS=\(* ]]; then
      found=$((found + 1))
      if [[ " $line " == *" $option "* ]]; then
        line="${line/ $option / !$option }"
        changed=$((changed + 1))
      elif [[ "$line" == "OPTIONS=($option "* ]]; then
        line="OPTIONS=(!$option ${line#OPTIONS=($option }"
        changed=$((changed + 1))
      elif [[ " $line " != *" !$option "* && "$line" != "OPTIONS=(!$option "* ]]; then
        rm -f "$temporary"
        echo "Cannot find option '$option' in $target" >&2
        return 1
      fi
    fi
    printf '%s\n' "$line" >> "$temporary"
  done < "$target"

  if [[ $found -ne 1 || $changed -gt 1 ]]; then
    rm -f "$temporary"
    echo "Expected one OPTIONS declaration in $target" >&2
    return 1
  fi

  chmod --reference="$target" "$temporary"
  if cmp -s "$target" "$temporary"; then
    rm -f "$temporary"
  else
    mv -f "$temporary" "$target"
  fi
}

makepkg_config="$MSYS2_ROOT_PREFIX/etc/makepkg_mingw.conf"
msystem_config="$MSYS2_ROOT_PREFIX/etc/msystem"
makepkg_mingw="$MSYS2_ROOT_PREFIX/usr/bin/makepkg-mingw"

require_line "$makepkg_config" '/etc/makepkg_mingw.d/${MSYSTEM,,}.conf'
require_line "$msystem_config" '/etc/msystem.d/${MSYSTEM}'
require_line "$makepkg_mingw" 'for _conf in /etc/makepkg_mingw.d/*.conf'

echo "::notice::Mixed bootstrap: Bash and Pacman are stage-0 AMD64-emulated tools; woarm64 and CLANGARM64 packages are copied native inputs until rebuilt."
echo "::group::Configure MINGWARM64 environment"
write_managed_file "$MSYS2_ROOT_PREFIX/usr/local/libexec/msys2-woarm64/path-boundary.sh" 0644 \
  < "$SCRIPT_DIR/lib/path-boundary.sh"
write_managed_file "$MSYS2_ROOT_PREFIX/usr/local/libexec/msys2-woarm64/woarm64-gcc" 0755 \
  < "$SCRIPT_DIR/lib/native-compiler.sh"
write_managed_file "$MSYS2_ROOT_PREFIX/usr/local/libexec/msys2-woarm64/woarm64-g++" 0755 \
  < "$SCRIPT_DIR/lib/native-compiler.sh"
write_managed_file "$MSYS2_ROOT_PREFIX/usr/local/libexec/msys2-woarm64/native-compiler-launcher.c" 0644 \
  < "$SCRIPT_DIR/lib/native-compiler-launcher.c"
write_managed_file "$MSYS2_ROOT_PREFIX/etc/msystem.d/MINGWARM64" <<'EOF'
MSYSTEM_PREFIX='/mingwarm64'
MSYSTEM_CARCH='aarch64'
MSYSTEM_CHOST='aarch64-w64-mingw32'
MINGW_CHOST="${MSYSTEM_CHOST}"
MINGW_PREFIX="${MSYSTEM_PREFIX}"
MINGW_PACKAGE_PREFIX="mingw-w64-${MSYSTEM_CARCH}"
export MSYSTEM_PREFIX MSYSTEM_CARCH MSYSTEM_CHOST MINGW_CHOST MINGW_PREFIX MINGW_PACKAGE_PREFIX
EOF

if [[ "$FLAVOR" == "NATIVE_WITH_NATIVE" ]]; then
  GCC_LAUNCHER_NATIVE="$(to_native_path "$MSYS2_ROOT_PREFIX/usr/local/libexec/msys2-woarm64/woarm64-gcc.exe")"
  GXX_LAUNCHER_NATIVE="$(to_native_path "$MSYS2_ROOT_PREFIX/usr/local/libexec/msys2-woarm64/woarm64-g++.exe")"
  printf -v GCC_LAUNCHER_SHELL '%q' "$GCC_LAUNCHER_NATIVE"
  printf -v GXX_LAUNCHER_SHELL '%q' "$GXX_LAUNCHER_NATIVE"

  # Pin the whole native tool closure to absolute paths. Leaving these unset
  # made every binutils tool a bare-name PATH lookup, which is how an emulated
  # AMD64 strip or objdump can reach an ARM64 package. Identity of the pinned
  # binaries is verified separately, in build-package.sh, because the toolchain
  # is not installed yet when this configuration is written.
  NATIVE_TOOL_BIN="${WOARM64_NATIVE_BIN:-/mingwarm64/bin}"
  NATIVE_TOOL_LINES=
  NATIVE_TOOL_EXPORTS='CC CXX'
  for TOOL_ASSIGNMENT in AR=ar AS=as DLLTOOL=dlltool LD=ld NM=nm \
      OBJCOPY=objcopy OBJDUMP=objdump RANLIB=ranlib RC=windres STRIP=strip \
      WINDRES=windres; do
    TOOL_VARIABLE="${TOOL_ASSIGNMENT%%=*}"
    TOOL_NAME="${TOOL_ASSIGNMENT#*=}"
    printf -v TOOL_SHELL '%q' \
      "$(to_native_path "$NATIVE_TOOL_BIN/$TOOL_NAME.exe")"
    NATIVE_TOOL_LINES+="$TOOL_VARIABLE=$TOOL_SHELL"$'\n'
    NATIVE_TOOL_EXPORTS+=" $TOOL_VARIABLE"
  done
  # makepkg's buildenv only exports CC, CXX, CHOST and MAKEFLAGS, so without an
  # explicit export the pinned binutils never reach configure or make and every
  # AC_CHECK_TOOL falls back to a bare-name PATH probe.
  NATIVE_TOOL_LINES+="export $NATIVE_TOOL_EXPORTS"

  write_managed_file "$MSYS2_ROOT_PREFIX/etc/makepkg_mingw.d/mingwarm64.conf" <<EOF
CARCH="aarch64"
CHOST="aarch64-w64-mingw32"
MINGW_CHOST="aarch64-w64-mingw32"
MINGW_PREFIX="/mingwarm64"
MINGW_PACKAGE_PREFIX="mingw-w64-aarch64"
CC=$GCC_LAUNCHER_SHELL
CXX=$GXX_LAUNCHER_SHELL
$NATIVE_TOOL_LINES
CPPFLAGS=
CFLAGS="-march=armv8-a -mtune=generic -O2 -pipe -Wp,-D_FORTIFY_SOURCE=2 -fstack-protector-strong -Wp,-D__USE_MINGW_ANSI_STDIO=1"
CXXFLAGS="\$CFLAGS -static-libstdc++"
LDFLAGS=""
RUSTFLAGS="-Cforce-frame-pointers=yes"
EOF
  rm -f "$MSYS2_ROOT_PREFIX/etc/profile.d/woarm64-cross.sh"
else
  write_managed_file "$MSYS2_ROOT_PREFIX/etc/makepkg_mingw.d/mingwarm64.conf" <<'EOF'
CARCH="aarch64"
CHOST="aarch64-w64-mingw32"
MINGW_CHOST="aarch64-w64-mingw32"
MINGW_PREFIX="/mingwarm64"
MINGW_PACKAGE_PREFIX="mingw-w64-aarch64"
CC="aarch64-w64-mingw32-gcc"
CXX="aarch64-w64-mingw32-g++"
RC="aarch64-w64-mingw32-windres"
WINDRES="aarch64-w64-mingw32-windres"
RANLIB="aarch64-w64-mingw32-ranlib"
STRIP="aarch64-w64-mingw32-strip"
OBJDUMP="aarch64-w64-mingw32-objdump"
OBJCOPY="aarch64-w64-mingw32-objcopy"
CPPFLAGS=
CFLAGS="-march=armv8-a -mtune=generic -O2 -pipe -Wp,-D_FORTIFY_SOURCE=2 -fstack-protector-strong -Wp,-D__USE_MINGW_ANSI_STDIO=1"
CXXFLAGS="$CFLAGS"
LDFLAGS=""
RUSTFLAGS="-Cforce-frame-pointers=yes"
EOF
  write_managed_file "$MSYS2_ROOT_PREFIX/etc/profile.d/woarm64-cross.sh" <<'EOF'
if [[ "${MSYSTEM:-}" == "MINGWARM64" ]]; then
  PATH="${MINGW_PREFIX}/bin:${MINGW_PREFIX}/${MSYSTEM_CHOST}/bin:/opt/bin:/opt/${MSYSTEM_CHOST}/bin:/opt/lib/gcc/${MSYSTEM_CHOST}/15.0.1:/opt/lib/bfd-plugins:/mingw64/bin:/mingw64/${MSYSTEM_CHOST}/bin:${PATH}"
  export PATH
fi
EOF
fi

if [[ "$DEBUG_BUILD" == "1" ]]; then
  disable_makepkg_option "$makepkg_config" strip
fi
echo "::endgroup::"

if [[ "${SETUP_MINGWARM64_SKIP_DIAGNOSTICS:-0}" != "1" ]]; then
  echo "::group::MINGWARM64 configuration"
  cat "$MSYS2_ROOT_PREFIX/etc/msystem.d/MINGWARM64"
  cat "$MSYS2_ROOT_PREFIX/etc/makepkg_mingw.d/mingwarm64.conf"
  echo "::endgroup::"
fi
