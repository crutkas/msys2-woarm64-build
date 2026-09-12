"""Independent Git behavior cases. Every supplied environment value and fixture is recorded."""

import json
import os
from pathlib import Path

from observe import run, save, sha


def clean_environment(work):
    home, temp = work / "private user home", work / "private temporary files"
    home.mkdir()
    temp.mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA")
           if key in os.environ}
    env.update(PATH=str(Path(env["SystemRoot"]) / "System32"),
               HOME=str(home), USERPROFILE=str(home), TEMP=str(temp), TMP=str(temp),
               GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    save(work / "environment-policy.json", {
        "values": env,
        "reasons": {
            "PATH": "Baseline has only native Windows System32; no artifact PATH repair or bootstrap directories",
            "HOME/USERPROFILE": "Fresh empty private user directory; no real user Git/SSH credentials or configuration",
            "TEMP/TMP": "Fresh verifier-owned temporary files, not preseeded candidate configuration",
            "GIT_CONFIG_GLOBAL": "NUL blocks real user global Git config; shipped system config remains enabled",
            "GIT_TERMINAL_PROMPT": "Disable credential prompts for public HTTPS, not authentication substitution",
            "PROGRAMDATA": "Unmodified OS location, explicitly supplied; no files or ACLs changed there",
        },
        "unset": "Every other inherited environment variable is omitted, including proxies, auth tokens, "
                 "GIT_EXEC_PATH, SSL_CERT_FILE, GIT_SSL_CAINFO and MSYS conversion controls",
        "artifact_files_preseeded": [],
    })
    return env


def launch_case(root, work, env, name, arguments, timeout=120, cwd=None):
    command = [root / "mingwarm64/bin/git.exe", *arguments]
    observation = run(command, cwd=cwd or work, env=env, output=work / name, timeout=timeout)
    return {"name": name, "observation": str(work / name / "observation.json"),
            "parent_raw_exit": observation["parent_raw_exit"], "timed_out": observation["timed_out"],
            "created": observation["created_processes"], "observed": observation["observed_processes"]}


def execute(root, work):
    root, work = Path(root), Path(work)
    work.mkdir()
    env = clean_environment(work)
    rows = []
    launcher = root / "Git-Bash-Native.cmd"
    shell_command = f'""{launcher}" -c "printf independent-launcher-ok; git --version""'
    observed = run([env["COMSPEC"], "/d", "/s", "/c", shell_command], cwd=work, env=env,
                   output=work / "documented-launcher", timeout=60,
                   windows_command_line=f'"{env["COMSPEC"]}" /d /s /c {shell_command}')
    rows.append({"name": "documented-launcher", "parent_raw_exit": observed["parent_raw_exit"],
                 "observation": str(work / "documented-launcher/observation.json")})
    rows.append(launch_case(root, work, env, "native-version", ["--version"]))
    repo = work / "real local repository"
    repo.mkdir()
    fixture = repo / "probe.txt"
    fixture.write_bytes(b"alpha\nneedle-independent-replay\nomega\n")
    save(work / "fixture.json", {
        "path": str(fixture), "sha256": sha(fixture), "purpose": "New user worktree content for real git add/commit/grep",
        "commit_identity": "Per-command -c user.name/user.email; no global account or config change",
    })
    cases = [
        ("git-init", ["init"]),
        ("git-add", ["add", "--", "probe.txt"]),
        ("git-commit", ["-c", "user.name=Independent MVP verifier",
                        "-c", "user.email=independent-verifier@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-m", "Independent local replay"]),
        ("git-log", ["--no-pager", "log", "-1", "--format=%H%n%s"]),
        ("git-status", ["status", "--porcelain=v1"]),
        ("git-grep", ["--no-pager", "grep", "-n", "--", "needle-independent-replay"]),
        ("git-fsck", ["fsck", "--full"]),
        ("git-system-config", ["config", "--show-origin", "--get-regexp", r"^(http\.|credential\.)"]),
        ("git-exec-path", ["--exec-path"]),
    ]
    for name, args in cases:
        rows.append(launch_case(root, work, env, name, args, cwd=repo))
    shell = root / "usr/bin/sh.exe"
    if shell.is_file():
        observation = run([shell, "-c", "printf independent-named-sh-ok"], cwd=work, env=env,
                          output=work / "named-sh", timeout=60)
        rows.append({"name": "named-sh", "parent_raw_exit": observation["parent_raw_exit"],
                     "observation": str(work / "named-sh/observation.json")})
    hook = repo / ".git/hooks/pre-commit"
    if hook.parent.is_dir():
        hook.write_bytes(b"#!/bin/sh\nprintf independent-hook-ran\nexit 0\n")
        fixture.write_bytes(fixture.read_bytes() + b"hook-probe\n")
        save(work / "hook-fixture.json", {"path": str(hook), "sha256": sha(hook),
                                         "purpose": "User-owned real Git hook exercising the runtime-named /bin/sh dependency"})
        rows.append(launch_case(root, work, env, "hook-add", ["add", "--", "probe.txt"], cwd=repo))
        rows.append(launch_case(root, work, env, "hook-commit",
                                ["-c", "user.name=Independent MVP verifier",
                                 "-c", "user.email=independent-verifier@example.invalid",
                                 "-c", "commit.gpgsign=false", "commit", "-m", "Independent hook replay"], cwd=repo))
    bare = work / "bare clone with spaces"
    rows.append(launch_case(root, work, env, "local-bare-clone",
                            ["clone", "--bare", "--", str(repo), str(bare)], timeout=120))
    destination = work / "real public HTTPS clone"
    rows.append(launch_case(root, work, env, "git-https-clone",
                           ["-c", "pack.threads=1", "clone", "--depth=1", "--",
                            "https://github.com/octocat/Hello-World.git", str(destination)], timeout=240))
    if (destination / ".git").is_dir():
        rows.append(launch_case(root, work, env, "https-log", ["--no-pager", "log", "-1", "--format=%H%n%s"],
                                cwd=destination))
        rows.append(launch_case(root, work, env, "https-status", ["status", "--porcelain=v1"], cwd=destination))
        rows.append(launch_case(root, work, env, "https-fsck", ["fsck", "--full"], cwd=destination))
        rows.append(launch_case(root, work, env, "https-origin", ["remote", "get-url", "origin"], cwd=destination))
    save(work / "result.json", {
        "status": "raw-independent-baseline-results-not-a-verdict", "artifact": str(root),
        "environment_policy": str(work / "environment-policy.json"), "cases": rows,
        "producer_replay_scripts_used": False, "artifact_repairs": [],
        "resource_setting": "Public clone uses per-command pack.threads=1 for the allocated job budget",
        "claim_limits": "Case output, raw child exits and closure must be reviewed; this controller does not "
                        "turn a raw-zero parent into an artifact acceptance verdict",
    })
    print(json.dumps(rows, indent=2))
