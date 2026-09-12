#!/usr/bin/env bash
set -euo pipefail
[[ $# == 6 ]] || { echo "usage: $0 OUTPUT TOOLCHAIN NATIVE_ROOT BOOTSTRAP PATCH JOBS" >&2; exit 2; }
export PATH=/usr/bin
output=$(cygpath -au -U "$1") toolchain=$(cygpath -au -U "$2") native_root=$(cygpath -au -U "$3")
bootstrap_bin=$(cygpath -au -U "$4\\usr\\bin") patch_file=$(cygpath -au -U "$5") jobs=$6
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo "Explicit job allocation required" >&2; exit 2; }
[[ $bootstrap_bin == "${output%/*}/"* ]] || { echo "Private bootstrap copy required" >&2; exit 3; }
export PERL_MSYS_BUILD_PATH=".:$native_root/usr/bin:$toolchain/bin:$bootstrap_bin"
export PERL_MSYS_LIBC="$toolchain/aarch64-pc-cygwin/lib/libmsys-2.0.a"
export PATH="$PERL_MSYS_BUILD_PATH"
export LC_ALL=C MSYSTEM=MSYS MSYS=winsymlinks:nativestrict
unset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS GCC_EXEC_PREFIX COMPILER_PATH LIBRARY_PATH
export TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
type -a gcc make sh sed awk grep env
mkdir -p "$TMPDIR" "$output/stage"
script_path=${BASH_SOURCE[0]//\\//}
source "${script_path%/*}/perl-native-arch-guard.sh"
require_native_perl_arch "$native_root"
mkdir "$output/symlink-prerequisite"
(
    cd "$output/symlink-prerequisite"
    printf 'native Perl link prerequisite\n' > target
    ln -s target link
    test -L link
)
cd "$output/source"
patch --batch --fuzz=0 -p1 -i "$patch_file"
[[ $(gcc -dumpmachine) == aarch64-pc-cygwin ]] || { echo "Wrong C compiler target" >&2; exit 3; }
"$bootstrap_bin/sh.exe" ./Configure -des -Dusethreads -Dosname=msys \
    -Doptimize="-O2 -g" -Dprefix=/usr -Dvendorprefix=/usr \
    -Dprivlib=/usr/share/perl5/core_perl -Darchlib=/usr/lib/perl5/core_perl \
    -Dsitelib=/usr/share/perl5/site_perl -Dsitearch=/usr/lib/perl5/site_perl \
    -Dvendorlib=/usr/share/perl5/vendor_perl -Dvendorarch=/usr/lib/perl5/vendor_perl \
    -Dscriptdir=/usr/bin/core_perl -Dsitescript=/usr/bin/site_perl \
    -Dvendorscript=/usr/bin/vendor_perl -Dinc_version_list=none \
    -Dman1ext=1perl -Dman3ext=3perl -Darchname=aarch64-msys-threads \
    -Dmyarchname=aarch64-msys -Dlibperl=msys-perl5_38.dll \
    -Dusrinc="$toolchain/aarch64-pc-cygwin/include" \
    -Dcc=gcc -Dld=gcc -Accflags="-O2 -g -fwrapv"
make -j"$jobs"
./perl.exe -Ilib -MConfig -e 'die "wrong Perl platform\n" unless $^O eq "msys" && $Config{ptrsize} == 8 && $Config{usethreads} eq "define"; print "$^O $Config{archname}\n"'
PERL_BUILD_PACKAGING=Yep TEST_JOBS="$jobs" make test_harness
make -j1 DESTDIR="$output/stage" install
mkdir -p "$output/stage/usr/share/licenses/perl"
cp Artistic Copying "$output/stage/usr/share/licenses/perl/"
