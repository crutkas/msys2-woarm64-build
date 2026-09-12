#!/usr/bin/env bash
failures=0
total=0
check() {
    local name=$1
    shift
    total=$((total + 1))
    if "$@"; then
        printf '%s\tPASS\n' "$name"
    else
        printf '%s\tFAIL\n' "$name"
        failures=$((failures + 1))
    fi
}
unicode_dir=$'owned space \u03bb \u4e2d'
mkdir "$unicode_dir" || exit 1
printf '%s\n' 'native path content' > "$unicode_dir/input file.txt"
IFS= read -r content < "$unicode_dir/input file.txt"
check unicode-posix-redirection test "$content" = 'native path content'
original=$PWD
cd "$unicode_dir" || exit 1
windows_path=$(pwd -W)
posix_path=$PWD
check windows-path-drive test "${windows_path:1:2}" = ':/'
printf '%s' 'native windows content' > "$windows_path/output file.txt"
content=$(<"$posix_path/output file.txt")
check windows-to-posix-file-identity test "$content" = 'native windows content'
content=$(/usr/bin/cat.exe "$windows_path/input file.txt")
check native-msys-child-windows-unicode-argument test "$content" = 'native path content'
content=$(/usr/bin/cat.exe "$posix_path/input file.txt")
check native-msys-child-posix-unicode-argument test "$content" = 'native path content'
cd "$windows_path" || exit 1
check windows-cd-preserves-posix-pwd test "$PWD" = "$posix_path"
paths=(*.txt)
check unicode-directory-glob-count test "${#paths[@]}" = 2
check spaced-basename-glob test "${paths[0]}" = 'input file.txt'
cd "$original" || exit 1
printf 'TOTAL\t%d\tFAILURES\t%d\n' "$total" "$failures"
exit "$failures"
