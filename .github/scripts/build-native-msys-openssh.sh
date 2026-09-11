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
require_sha256 "$toolchain/bin/msys2-gcc" c47a900c28554240ed021bb3d02fa0b542055ec21645a349026c42db0e0f1682
require_sha256 "$toolchain/bin/msys-2.0.dll" 907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c
require_sha256 "$toolchain/aarch64-pc-cygwin/lib/libmsys-2.0.a" 6f19eb725d275d6e9f3564783cf5a18c9f13849b6c8033ca92291ecd3f5a735c
require_sha256 "$toolchain/aarch64-pc-cygwin/lib/crt0.o" 29b356f7105386a37bc8b16169e8beac1b0cbc2c1640946df02f85bbae5d3737
require_sha256 "$openssl/bin/msys-crypto-3.dll" 122625f405ea1d409a1fcd6a1cd9f18f1f5ef6c8069f8ce143582528786ea0c7
require_sha256 "$zlib/bin/msys-z.dll" edb3e9e04c03df58e2f45a416e73c966e4580fedc8b1a60b7630d3cf7815e9d4
require_sha256 "$libxcrypt/bin/msys-crypt-2.dll" ce687271a36f2281ee65991b6cb18efbc3eb3bb45b4f9169a31d3d7d23d45dbe

mkdir -p "$output_root"/{src,build,stage,logs}
cp -a "$source_dir"/. "$output_root/src"/
patch --batch --forward --fuzz=0 -d "$output_root/src" -p1 -i "$patch_file"

export PATH="$toolchain/bin:$PATH"
export CC="$toolchain/bin/msys2-gcc"
export AR="$toolchain/bin/aarch64-pc-cygwin-ar"
export RANLIB="$toolchain/bin/aarch64-pc-cygwin-ranlib"
export STRIP="$toolchain/bin/aarch64-pc-cygwin-strip"
export CPPFLAGS="-I$openssl/include -I$zlib/include -I$libxcrypt/include"
export LDFLAGS="-L$openssl/lib -L$zlib/lib -L$libxcrypt/lib"
export LIBS=-lcrypt
export MSYS_TEXTREADMODE_OBJECT="$toolchain/aarch64-pc-cygwin/lib/textreadmode.o"
export MSYSTEM=CYGWIN
export TEST_SSH_UTF8=no
export ac_cv_func_setproctitle=no
export ac_cv_func_arc4random_stir=no
export MAKEFLAGS="-j$jobs"

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
