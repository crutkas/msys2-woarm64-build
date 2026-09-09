#!/usr/bin/env bash
set -euo pipefail

[[ $# == 2 ]] || exit 2
stage=${1//\\//}
output=${2//\\//}
case "$stage" in
    [A-Za-z]:/*) stage="/proc/cygdrive/${stage:0:1}${stage:2}" ;;
esac
case "$output" in
    [A-Za-z]:/*) output="/proc/cygdrive/${output:0:1}${output:2}" ;;
esac
stage=${stage/\/proc\/cygdrive\/C/\/proc\/cygdrive\/c}
output=${output/\/proc\/cygdrive\/C/\/proc\/cygdrive\/c}

export PATH="$stage/usr/bin"
export LC_ALL=C
unset BASH_ENV ENV

rm -rf "$output"
mkdir -p "$output/tree/sub"
printf 'alpha\nbeta\n' > "$output/input"
printf 'payload\n' > "$output/tree/sub/item"

[[ $(awk 'END { print NR }' "$output/input") == 2 ]]
[[ $(grep -c '^beta$' "$output/input") == 1 ]]
[[ $(sed -n '2p' "$output/input") == beta ]]
[[ $(find "$output/tree" -type f -name item -print) == "$output/tree/sub/item" ]]
[[ $(printf 'one\ntwo\n' | xargs echo) == 'one two' ]]
cp "$output/input" "$output/copy"
cmp "$output/input" "$output/copy"
diff -u "$output/input" "$output/copy"
[[ $(pcregrep -c '^alpha$' "$output/input") == 1 ]]
[[ $(printf 'A' | hexdump -v -e '1/1 "%02x"') == 41 ]]
locale -a | grep -qx C
printf 'A' | od -An -tx1 | grep -Eq '(^|[[:space:]])41([[:space:]]|$)'
tmpfile=$(mktemp "$output/native-utils.XXXXXX")
test -f "$tmpfile"
rm -f "$tmpfile"
mkfifo "$output/native-fifo"
test -p "$output/native-fifo"
rm -f "$output/native-fifo"
mkdir "$output/native-dir"
rmdir "$output/native-dir"
printf 'native tee\n' | tee "$output/tee.out" | grep -qx 'native tee'
grep -qx 'native tee' "$output/tee.out"

printf 'native utility smoke passed\n'
