#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 7 ]]; then
	echo "usage: $0 SOURCE_DIR SOURCE_MANIFEST TOOLCHAIN OPENSSL ZLIB LIBXCRYPT OUTPUT_ROOT" >&2
	exit 2
fi

source_dir=$1
source_manifest=$2
toolchain=$3
openssl=$4
zlib=$5
libxcrypt=$6
output_root=$7
jobs=${OPENSSH_JOBS:-2}
patch_file=$(cd "$(dirname "$0")/.." && pwd)/patches/openssh-10.5p1-msys-cross-textreadmode.patch
release_cc=$(cd "$(dirname "$0")" && pwd)/msys-openssh-release-gcc

require_sha256 () {
	local path=$1 expected=$2 actual
	actual=$(sha256sum "$path" | cut -d' ' -f1)
	if [[ $actual != "$expected" ]]; then
		echo "hash mismatch for $path: expected $expected, observed $actual" >&2
		exit 1
	fi
}

if [[ $jobs -lt 1 || $jobs -gt 2 ]]; then
	echo "OPENSSH_JOBS must be 1 or 2" >&2
	exit 2
fi
if [[ -e $output_root ]]; then
	echo "output root already exists: $output_root" >&2
	exit 1
fi

require_sha256 "$source_manifest" aaf4155ea067599012b5d31c0c1d394575f6227a5f67e95f47b617aa21f91255
require_sha256 "$toolchain/bin/gcc.exe" 0eb57ff0d26c4d7a8da0a028beedc2df4349209bb14ac8a9553d519d06fe679c
require_sha256 "$toolchain/bin/msys-2.0.dll" 907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c
require_sha256 "$toolchain/aarch64-pc-cygwin/lib/libmsys-2.0.a" 6f19eb725d275d6e9f3564783cf5a18c9f13849b6c8033ca92291ecd3f5a735c
require_sha256 "$toolchain/aarch64-pc-cygwin/lib/crt0.o" 29b356f7105386a37bc8b16169e8beac1b0cbc2c1640946df02f85bbae5d3737
require_sha256 "$openssl/bin/msys-crypto-3.dll" 1f849092ae4f5aa3df1b0a7360c626a7e841c9060e8413220df4e862160c4cb4
require_sha256 "$openssl/bin/msys-ssl-3.dll" 5db603a6df4757055b5e6947cd6051956da311644ae5e9010cdaaf786693b374
require_sha256 "$zlib/bin/msys-z.dll" edb3e9e04c03df58e2f45a416e73c966e4580fedc8b1a60b7630d3cf7815e9d4
require_sha256 "$libxcrypt/bin/msys-crypt-2.dll" ce687271a36f2281ee65991b6cb18efbc3eb3bb45b4f9169a31d3d7d23d45dbe

mkdir -p "$output_root"/{src,build,stage,logs}
cp -a "$source_dir"/. "$output_root/src"/
patch --batch --forward --fuzz=0 -d "$output_root/src" -p1 -i "$patch_file"

export PATH="$toolchain/bin:$PATH"
export OPENSSH_RELEASE_GCC_REAL="$toolchain/bin/gcc.exe"
export OPENSSH_RELEASE_RUNTIME_LIB="$toolchain/aarch64-pc-cygwin/lib"
export OPENSSH_RELEASE_BUILD_SOURCE="$output_root/src"
export OPENSSH_RELEASE_BUILD_ROOT="$output_root/build"
export CC="$release_cc"
export AR="$toolchain/bin/aarch64-pc-cygwin-ar"
export RANLIB="$toolchain/bin/aarch64-pc-cygwin-ranlib"
export STRIP="$toolchain/bin/aarch64-pc-cygwin-strip"
export OBJDUMP="$toolchain/bin/aarch64-pc-cygwin-objdump"
export STRINGS="$toolchain/bin/aarch64-pc-cygwin-strings"
export CPPFLAGS="-I$openssl/include -I$zlib/include -I$libxcrypt/include"
export LDFLAGS="-B$OPENSSH_RELEASE_RUNTIME_LIB/ -L$openssl/lib -L$zlib/lib -L$libxcrypt/lib"
export LIBS=-lcrypt
export MSYS_TEXTREADMODE_OBJECT="$toolchain/aarch64-pc-cygwin/lib/textreadmode.o"
export MSYS2_ARG_CONV_EXCL='-DSSHDIR=;-D_PATH_'
export MSYSTEM=CYGWIN
export TEST_SSH_UTF8=no
export ac_cv_func_setproctitle=no
export ac_cv_func_arc4random_stir=no
export MAKEFLAGS="-j$jobs"

selected_crt=$(cygpath -am "$("$CC" -print-file-name=crt0.o)")
selected_runtime=$(cygpath -am "$("$CC" -print-file-name=libmsys-2.0.a)")
if [[ $selected_crt != "$(cygpath -am "$toolchain/aarch64-pc-cygwin/lib/crt0.o")" ||
	$selected_runtime != "$(cygpath -am "$toolchain/aarch64-pc-cygwin/lib/libmsys-2.0.a")" ]]; then
	echo "compiler did not select the sealed runtime startup/import files" >&2
	exit 1
fi

cd "$output_root/build"
"$output_root/src/configure" \
	--build=x86_64-pc-linux-gnu \
	--host=aarch64-pc-cygwin \
	--prefix=/usr \
	--sbindir=/usr/bin \
	--libexecdir=/usr/lib/ssh \
	--sysconfdir=/etc/ssh \
	--localstatedir=/var \
	--with-ssl-dir="$openssl" \
	--with-zlib="$zlib" \
	--disable-security-key \
	--without-hardening \
	--without-stackprotect \
	--disable-strip \
	--with-sandbox=no \
	2>&1 | tee "$output_root/logs/configure.log"
make "-j$jobs" 2>&1 | tee "$output_root/logs/build.log"
make DESTDIR="$output_root/stage" install-nokeys 2>&1 | tee "$output_root/logs/install.log"

mapfile -d '' release_images < <(find "$output_root/stage" -type f \( -iname '*.exe' -o -iname '*.dll' \) -print0)
if [[ ${#release_images[@]} -eq 0 ]]; then
	echo "install produced no native PE images" >&2
	exit 1
fi
for image in "${release_images[@]}"; do
	"$STRIP" --strip-debug --preserve-dates "$image"
	if ! "$OBJDUMP" -f "$image" | grep -q 'architecture: aarch64'; then
		echo "installed image is not ARM64: $image" >&2
		exit 1
	fi
	if "$STRINGS" -a "$image" | grep -E -q '\.copilot|session-state|C:/Users|C:\\Users|/mnt/c/Users|/root/arm64-vnext|/c/ap13-dcb|C:/ap13-dcb'; then
		echo "installed image contains a forbidden producer-private marker: $image" >&2
		exit 1
	fi
done
(
	cd "$output_root/stage"
	find . -type f -print0 | sort -z | xargs -0 sha256sum
) > "$output_root/release-files.sha256"
