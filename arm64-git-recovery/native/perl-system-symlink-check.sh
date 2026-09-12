#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 && ${MSYS-} == winsymlinks:sys ]] || {
    echo "Explicit MSYS system-symlink mode and a fresh probe directory are required" >&2
    exit 2
}
[[ ! -e $1 ]] || { echo "Refusing to reuse a symlink probe directory" >&2; exit 2; }
mkdir -p "$1"
cd "$1"
printf 'first\n' > target
ln -s target link
[[ -L link && -f link && $(readlink link) == target && $(cat link) == first ]]
printf 'changed\n' > target
[[ $(cat link) == changed ]]
cp target copy
[[ ! -L copy && $(cat copy) == changed ]]
ln -s absent dangling
[[ -L dangling && ! -e dangling && $(readlink dangling) == absent ]]
mkdir directory
ln -s directory directory-link
[[ -L directory-link && -d directory-link && $(readlink directory-link) == directory ]]
[[ $(cd directory-link && pwd -P) == "$(pwd -P)/directory" ]]
issymlink='test -L'
: "${issymlink:?A tested symlink predicate is required; refusing to execute a pathname}"
$issymlink link
if $issymlink copy; then
    echo "Regular-file negative control was incorrectly recognized as a symlink" >&2
    exit 3
fi
[[ -x $(type -P test) ]]
"$(type -P test)" -L link
if "$(type -P test)" -L copy; then
    echo "External test misclassified the regular-file negative control" >&2
    exit 3
fi
printf '%s\n' \
    'PERL_SYSTEM_SYMLINKS=PASS' \
    'SYMLINK_POLICY=winsymlinks:sys' \
    'NATIVE_WINDOWS_SYMLINK_QUALIFICATION=false' \
    'CASES=file-link,readlink,target-mutation,copy-negative,dangling,directory,physical-pwd,nonempty-predicate,external-test'
