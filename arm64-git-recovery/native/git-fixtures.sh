#!/usr/bin/env bash
# Functional fixture layer only. Test-NativeGit.ps1 supplies the native gates.
set -euo pipefail
[[ $# == 5 ]] || {
    echo "usage: $0 GIT_EXE GIT_EXEC_PATH NEW_FIXTURE_ROOT native-msys|harness-control BUILTINS_FILE_OR_DASH" >&2
    exit 2
}
git_exe=$1 exec_path=$2 work=$3 mode=$4 builtin_list=$5
case "$mode" in native-msys|harness-control) ;; *) echo "Invalid fixture mode" >&2; exit 2 ;; esac
[[ -x $git_exe && -d $exec_path ]] || { echo "Missing Git executable/exec path" >&2; exit 2; }
[[ ! -e $work ]] || { echo "Fixture root must not exist" >&2; exit 2; }
for name in ${!GIT_@}; do unset "$name"; done
unset CDPATH ENV BASH_ENV PERL5LIB PERLLIB PERL5OPT
mkdir -p "$work/home"
work=$(cd "$work" && pwd)
cd "$work"
exec > >(tee "$work/fixture.log") 2>&1
export HOME="$work/home" XDG_CONFIG_HOME="$work/home/.config"
: > "$work/home/empty.gitconfig"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL="$work/home/empty.gitconfig" GIT_TERMINAL_PROMPT=0
export GIT_EXEC_PATH="$exec_path" LC_ALL=C
export GIT_AUTHOR_NAME=Fixture GIT_AUTHOR_EMAIL=fixture@example.invalid
export GIT_COMMITTER_NAME=Fixture GIT_COMMITTER_EMAIL=fixture@example.invalid
export GIT_AUTHOR_DATE="2020-01-01T00:00:00Z" GIT_COMMITTER_DATE="2020-01-01T00:00:00Z"
export PATH="$exec_path:$PATH"
git_run() { "$git_exe" "$@"; }

if [[ $mode == native-msys ]]; then
    win_pwd=$(builtin pwd -W)
    [[ $win_pwd =~ ^[a-zA-Z]:/ ]] || { echo "pwd -W did not return a Windows path" >&2; exit 3; }
fi
if [[ $builtin_list != - ]]; then
    [[ -s $builtin_list ]] || { echo "Missing builtin provenance list" >&2; exit 3; }
    git_run --list-cmds=builtins | tr ' ' '\n' | sed '/^$/d;s/^/git-/;s/$/.exe/' | sort \
        > "$work/actual-builtins.txt"
    sort "$builtin_list" > "$work/packaged-builtins.txt"
    cmp "$work/actual-builtins.txt" "$work/packaged-builtins.txt"
fi

git_run init --initial-branch=main "$work/child"
printf 'child payload\n' > "$work/child/payload.txt"
git_run -C "$work/child" add payload.txt
git_run -C "$work/child" commit -m child
child_head=$(git_run -C "$work/child" rev-parse HEAD)
[[ $child_head =~ ^[0-9a-f]{40,64}$ ]]

git_run init --initial-branch=main "$work/source"
printf 'first payload\n' > "$work/source/a file.txt"
git_run -C "$work/source" add "a file.txt"
git_run -C "$work/source" commit -m initial
cat > "$work/source/.git/hooks/pre-commit" <<'HOOK'
#!/bin/sh
printf 'hook executed\n' > .git/hook-observed
HOOK
chmod +x "$work/source/.git/hooks/pre-commit"
printf 'second payload\n' >> "$work/source/a file.txt"
git_run -C "$work/source" commit -am hook-positive
[[ $(cat "$work/source/.git/hook-observed") == "hook executed" ]]
before=$(git_run -C "$work/source" rev-parse HEAD)
printf '#!/bin/sh\nexit 73\n' > "$work/source/.git/hooks/pre-commit"
printf 'negative control\n' >> "$work/source/a file.txt"
if git_run -C "$work/source" commit -am must-not-commit; then
    echo "Failing hook was ignored" >&2
    exit 4
fi
[[ $(git_run -C "$work/source" rev-parse HEAD) == "$before" ]]
printf '#!/bin/sh\nexit 0\n' > "$work/source/.git/hooks/pre-commit"
git_run -C "$work/source" commit -am after-negative

git_run -C "$work/source" -c protocol.file.allow=always submodule add "$work/child" "sub module"
git_run -C "$work/source" commit -m submodule
source_head=$(git_run -C "$work/source" rev-parse HEAD)
git_run -c protocol.file.allow=always clone --no-local --recurse-submodules "$work/source" "$work/clone"
[[ $(git_run -C "$work/clone" rev-parse HEAD) == "$source_head" ]]
[[ $(git_run -C "$work/clone/sub module" rev-parse HEAD) == "$child_head" ]]
clone_status=$(git_run -C "$work/clone" status --porcelain)
[[ -z $clone_status ]]
git_run -C "$work/clone" fsck --strict
cmp "$work/child/payload.txt" "$work/clone/sub module/payload.txt"

# An isolated helper tests Git's credential protocol, not Windows credential storage.
cat > "$work/credential-fixture.sh" <<'HELPER'
#!/bin/sh
case "$1" in
get)
    while IFS= read -r line && test -n "$line"; do :; done
    printf 'username=fixture-user\npassword=fixture-only-not-a-secret\n\n'
    ;;
*) exit 9 ;;
esac
HELPER
chmod +x "$work/credential-fixture.sh"
printf 'protocol=https\nhost=fixture.invalid\n\n' |
    git_run -c credential.helper= -c "credential.helper=$work/credential-fixture.sh" credential fill \
    > "$work/credential-result.txt"
grep -qx 'username=fixture-user' "$work/credential-result.txt"
grep -qx 'password=fixture-only-not-a-secret' "$work/credential-result.txt"

# Deliberately local transport fixture: proves SSH helper dispatch and upload-pack,
# NOT an SSH connection, encryption, agent behavior, or host-key verification.
cat > "$work/ssh-fixture.sh" <<'SSH'
#!/bin/sh
test "$#" -eq 2 && test "$1" = fixture.invalid || exit 19
printf 'invoked\n' > "$FIXTURE_SSH_MARKER"
exec sh -c "$2"
SSH
chmod +x "$work/ssh-fixture.sh"
export GIT_SSH="$work/ssh-fixture.sh" GIT_SSH_VARIANT=simple
export FIXTURE_SSH_MARKER="$work/ssh-observed"
git_run clone --no-checkout "fixture.invalid:$work/source" "$work/ssh-clone"
[[ $(cat "$FIXTURE_SSH_MARKER") == invoked ]]
[[ $(git_run -C "$work/ssh-clone" rev-parse HEAD) == "$source_head" ]]
git_run -C "$work/ssh-clone" fsck --strict
unset GIT_SSH GIT_SSH_VARIANT FIXTURE_SSH_MARKER

perl -e 'my $p = fork(); defined($p) or die "fork"; if (!$p) {exit 37} waitpid($p,0) == $p or die "wait"; ($? >> 8) == 37 && ($? & 127) == 0 or die "status"; print "perl-fork-ok\n"' \
    > "$work/perl-result.txt"
grep -qx perl-fork-ok "$work/perl-result.txt"
cat > "$work/Makefile" <<'MAKE'
.PHONY: all
all:
	printf 'make-shell-ok\n' > make-result.txt
MAKE
make -C "$work" -j2 -f Makefile
grep -qx make-shell-ok "$work/make-result.txt"
printf 'b\na\nb\n' | sort | uniq > "$work/coreutils-result.txt"
printf 'a\nb\n' > "$work/coreutils-expected.txt"
cmp "$work/coreutils-result.txt" "$work/coreutils-expected.txt"
printf 'mode=%s\nstatus=offline-fixtures-passed\nsource_head=%s\nchild_head=%s\n' \
    "$mode" "$source_head" "$child_head" > "$work/FIXTURE-RESULT.txt"
cat "$work/FIXTURE-RESULT.txt"
