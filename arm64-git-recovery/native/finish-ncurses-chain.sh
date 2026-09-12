#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 || $# == 3 ]] || exit 2
output=$(cygpath -u "$1") jobs=$2
install_mode=${3:-full}
[[ $install_mode == full || $install_mode == remaining ]] || exit 2
[[ $jobs == 1 || $jobs == 2 ]] || exit 2
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tc=/c/ag-e138920f/tc-cpp-guard-01
export PATH="$output/build/lib:$output/build/progs:$tc/bin:/usr/bin"
export HOME="$output/home" TMPDIR="$output/temp" TMP="$output/temp" TEMP="$output/temp"
export LC_ALL=C MSYSTEM=CYGWIN MAKEFLAGS="-j$jobs" MFLAGS="-j$jobs" OMP_NUM_THREADS=1
export WOARM64_NATIVE_ARG_CONVERSION=none CONFIG_SITE=/dev/null
before=c582ad3ab4743c28e15f9ac1453e2d8d08fb30d0c098045b20b6e59a1f0a8505
after=e170ba38aea68370776dba10a36bfdc7fff610d0f7c1ce76146bc90644d2af58
test_source="$output/source/ncurses/tty/hardscroll.c"
current=$(sha256sum "$test_source" | cut -d ' ' -f1)
if [[ $current == "$before" ]]; then
    /usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch \
        -p1 -d "$output/source" -i "$here/patches/ncurses-6.6-debug-test-trace.patch"
elif [[ $current != "$after" ]]; then
    echo "Unexpected standalone scroll-test source before repair" >&2; exit 3
fi
[[ $(sha256sum "$test_source" | cut -d ' ' -f1) == "$after" ]]
sha256sum "$test_source" > "$output/hardscroll-test-after.sha256"
current=$(sha256sum "$output/source/test/Makefile.in" | cut -d ' ' -f1)
if [[ $current == 41d5ef2c8b6187f20b1f29135c3ec0607e898164ea6bc4a53b9ac4f521f798aa ]]; then
    /usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch \
        -p1 -d "$output/source" -i "$here/patches/ncurses-6.6-out-of-tree-header-test.patch"
elif [[ $current != 3b1641e4f24082e65cfb1f2d138bd427c66f7638b8ae22e530feda6d4173a493 &&
        $current != 3afe751d732df98c6e25db15c48c0c5a931c6407e43c51d09ef61dfbae42ddb5 ]]; then
    echo "Unexpected source test header template" >&2; exit 3
fi
cd "$output/build"
if [[ $(sha256sum "$output/source/test/Makefile.in" | cut -d ' ' -f1) != \
      3afe751d732df98c6e25db15c48c0c5a931c6407e43c51d09ef61dfbae42ddb5 ]]; then
    /usr/bin/patch --batch --forward --fuzz=0 --no-backup-if-mismatch \
        -p1 -d "$output/source" -i "$here/patches/ncurses-6.6-header-test-basename.patch"
fi
./config.status --file=test/Makefile
# config.status's separate default command appends these upstream program rules.
# Reproduce that exact test-only generator, without re-appending other Makefiles.
grep -qx 'AWK="gawk"' config.status
grep -qx 'ECHO_LD=""' config.status
gawk -f "$output/source/test/mk-test.awk" INSTALL=no ECHO_LINK="" \
    "$output/source/test/programs" >> test/Makefile
# captoinfo's state lives in the separately requested tic library.
make -j"$jobs" check 'TEST_LDFLAGS=$(TEST_ARGS) -Wl,--no-insert-timestamp -lticw' 'SHELL=/usr/bin/bash -e'
if [[ $install_mode == full ]]; then
    make -j1 DESTDIR="$output/stage" install
else
    for subdir in test misc c++; do
        make -C "$subdir" -j1 DESTDIR="$output/stage" install
    done
fi
cp -a "$output/stage/usr/include/ncursesw" "$output/stage/usr/include/ncurses"
cp "$output/stage/usr/include/ncursesw/"*.h "$output/stage/usr/include/"
for suffix in a dll.a; do
    for alias in ncurses curses; do
        cp "$output/stage/usr/lib/libncursesw.$suffix" "$output/stage/usr/lib/lib$alias.$suffix"
    done
    for library in panel menu; do
        cp "$output/stage/usr/lib/lib${library}w.$suffix" "$output/stage/usr/lib/lib$library.$suffix"
    done
done
for library in form menu ncurses++ ncurses panel tic; do
    cp "$output/stage/usr/lib/pkgconfig/${library}w.pc" "$output/stage/usr/lib/pkgconfig/$library.pc"
done
native_python=$(cygpath -u "$WOARM64_NATIVE_PYTHON")
"$native_python" -B "$here/record-ncurses-package-link.py" "$(cygpath -m "$output")"
install -Dm644 "$output/source/COPYING" "$output/stage/usr/share/licenses/ncurses/LICENSE"
