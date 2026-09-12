#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || { echo "Exact Git executable and owned fixture repository required" >&2; exit 91; }
git_executable=$1
repository=$2
[[ -x $git_executable && -f $repository/.git/hooks/pre-commit ]] || exit 92
exec "$git_executable" -C "$repository" commit -am must-not-commit
