#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || { echo "usage: behavior.sh NEW_WORK_ROOT HTTPS_REPOSITORY_OR_DASH" >&2; exit 2; }
work=$1 remote=$2
[[ ! -e $work ]] || { echo "A fresh independent workspace is required" >&2; exit 2; }
mkdir -p "$work/home"
cd "$work"
work=$(pwd -P)
export HOME="$work/home" XDG_CONFIG_HOME="$work/home/.config"
export PATH=/mingwarm64/bin:/usr/bin
for name in ${!GIT_@}; do unset "$name"; done
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL="$HOME/config" GIT_TERMINAL_PROMPT=0
export GIT_AUTHOR_NAME='Native MVP fixture' GIT_COMMITTER_NAME='Native MVP fixture'
export GIT_AUTHOR_EMAIL=fixture@example.invalid GIT_COMMITTER_EMAIL=fixture@example.invalid
export GIT_AUTHOR_DATE=2020-01-01T00:00:00Z GIT_COMMITTER_DATE=2020-01-01T00:00:00Z
export LC_ALL=C
: > "$GIT_CONFIG_GLOBAL"
: > "$work/cases.tsv"
case_pass() { printf '%s\tPASS\t%s\n' "$1" "$2" >> "$work/cases.tsv"; }
[[ $(uname -m) == aarch64 || $(uname -m) == arm64 ]]
case_pass native-uname "$(uname -m)"
winroot=$(cd / && pwd -W)
[[ $winroot == [A-Za-z]:/* ]]
unset GIT_CONFIG_NOSYSTEM
export GIT_CONFIG_SYSTEM="$winroot/mingwarm64/etc/gitconfig"
case_pass relocated-runtime-root "$winroot"
printf 'b\na\nb\n' | sort | uniq > pipeline.txt
printf 'a\nb\n' > expected.txt
cmp pipeline.txt expected.txt
case_pass pipeline-sort-uniq exact-bytes
subshell=$(printf 'subshell-%s' ok)
[[ $subshell == subshell-ok ]]
if [[ ${MVP_EXPECTED_EXIT_HELPER-} ]]; then
    "$MVP_EXPECTED_EXIT_HELPER" --exit msys-child-seven-v1 7 &
else
    (exit 7) &
fi
child=$!
rc=0
wait "$child" || rc=$?
[[ $rc == 7 ]]
case_pass fork-wait 'semantic-exit-7'
trap 'printf "USR1 handled\n" > signal.txt' USR1
kill -USR1 "$$"
[[ $(cat signal.txt) == 'USR1 handled' ]]
trap - USR1
case_pass signal-usr1 native-bash-trap
mkdir 'directory space'
printf 'filesystem payload\n' > 'directory space/file.txt'
cp 'directory space/file.txt' copy.txt
cmp 'directory space/file.txt' copy.txt
mv copy.txt moved.txt
[[ -f moved.txt && ! -e copy.txt ]]
rm moved.txt
[[ ! -e moved.txt ]]
case_pass filesystem copy-move-remove-spaces
dd if=/dev/urandom of=random64.bin bs=64 count=1 status=none
[[ $(wc -c < random64.bin) == 64 ]]
dd if=/dev/urandom of=random4096.bin bs=4096 count=1 iflag=fullblock,nonblock status=none
[[ $(wc -c < random4096.bin) == 4096 ]]
case_pass random-device '64-and-4096-bytes'
rc=0
if [[ ${MVP_EXPECTED_EXIT_HELPER-} ]]; then
    "$MVP_EXPECTED_EXIT_HELPER" --spawn msys-env-eacces-v1 126 /usr/bin/env . >env.stdout 2>env.stderr
else
    env . >env.stdout 2>env.stderr || rc=$?
    [[ $rc == 126 ]]
fi
grep -q 'Permission denied' env.stderr
case_pass execvp-permission 'semantic-exit-126'
for repo in child source; do
    git init --initial-branch=main "$repo"
    printf '%s payload\n' "$repo" > "$repo/payload.txt"
    git -C "$repo" add payload.txt
    git -C "$repo" commit -m initial
done
case_pass git-init-commit two-real-repositories
printf '#!/bin/sh\nprintf "hook-ok\\n" > .git/hook-observed\n' > source/.git/hooks/pre-commit
[[ -x source/.git/hooks/pre-commit ]]
printf 'positive\n' >> source/payload.txt
git -C source commit -am hook-positive
[[ $(cat source/.git/hook-observed) == hook-ok ]]
before=$(git -C source rev-parse HEAD)
printf '#!/bin/sh\nprintf "negative-hook-executed\\n" > .git/negative-hook-observed\nexit 73\n' > source/.git/hooks/pre-commit
cp source/.git/hooks/pre-commit negative-hook-source.sh
printf 'negative\n' >> source/payload.txt
rc=0
if [[ ${MVP_NEGATIVE_HOOK_PHASE-} ]]; then
    hook_argv=("$MVP_EXPECTED_EXIT_HELPER" --spawn msys-git-hook-negative-v1 1 /usr/bin/bash
               "$MVP_NEGATIVE_HOOK_PHASE" /mingwarm64/bin/git.exe "$work/source")
    printf '%s\0' "${hook_argv[@]}" > negative-hook-argv.bin
    WOARM64_EXIT_CONTRACT_SOURCE_SHA256="${MVP_NEGATIVE_HOOK_SOURCE_SHA256:?Missing bound phase source}" \
        "${hook_argv[@]}"
else
    git -C source commit -am must-not-commit || rc=$?
    [[ $rc != 0 ]]
fi
[[ $(cat source/.git/negative-hook-observed) == negative-hook-executed ]]
[[ $(git -C source rev-parse HEAD) == "$before" ]]
printf '%s\n%s\n%s\n' "$before" "$(git -C source rev-parse HEAD)" \
    "$(cat source/.git/negative-hook-observed)" > negative-hook-proof.txt
printf '#!/bin/sh\nexit 0\n' > source/.git/hooks/pre-commit
git -C source commit -am after-negative
case_pass git-hooks positive-and-rejected-commit
git -C source -c protocol.file.allow=always submodule add "$work/child" 'sub module'
git -C source commit -m submodule
git -c protocol.file.allow=always clone --no-local --recurse-submodules "$work/source" "$work/clone"
[[ $(git -C clone rev-parse HEAD) == "$(git -C source rev-parse HEAD)" ]]
[[ $(git -C 'clone/sub module' rev-parse HEAD) == "$(git -C child rev-parse HEAD)" ]]
[[ -z $(git -C clone status --porcelain) ]]
git -C clone fsck --strict
case_pass git-recursive-clone exact-head-clean-fsck
git -C clone log -1 --format=%H > git-head.txt
if [[ $remote != - ]]; then
    git -c credential.helper= -c http.sslVerify=true clone --depth=1 --no-checkout "$remote" https-clone
    git -C https-clone -c credential.helper= -c http.sslVerify=true fetch --depth=1 origin
    git -C https-clone fsck --strict
    git -C https-clone rev-parse HEAD > https-head.txt
    [[ $(cat https-head.txt) =~ ^[0-9a-f]{40,64}$ ]]
    case_pass https-clone-fetch "$remote"
fi
printf 'NATIVE_MVP_BEHAVIOR_COMPLETE\n'
