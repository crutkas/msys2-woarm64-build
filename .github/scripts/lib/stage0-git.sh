#!/bin/bash

configure_stage0_git() {
  local git_executable
  local exec_path

  git_executable=$(command -v git) || {
    echo "Stage-0 Git executable is unavailable" >&2
    return 1
  }
  if [[ ! -x "$git_executable" ]]; then
    echo "Stage-0 Git executable is not executable: $git_executable" >&2
    return 1
  fi

  exec_path=$(env -u GIT_EXEC_PATH "$git_executable" --exec-path)
  if [[ ! -x "$exec_path/git-remote-https.exe" ]]; then
    echo "Stage-0 Git HTTPS helper is missing from $exec_path" >&2
    return 1
  fi

  unset GIT_CONFIG GIT_CONFIG_PARAMETERS
  # Source archives must preserve blob bytes regardless of host checkout policy.
  export GIT_CONFIG_COUNT=1
  export GIT_CONFIG_KEY_0=core.autocrlf
  export GIT_CONFIG_VALUE_0=false
  export GIT_CONFIG_GLOBAL=/dev/null
  export GIT_CONFIG_NOSYSTEM=1
  export GIT_CONFIG_SYSTEM=/dev/null
  export GIT_EXEC_PATH="$exec_path"
}
