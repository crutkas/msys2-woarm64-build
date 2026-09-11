"""Record one exact expected-negative hook phase without granting it an observer allowance."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from artifact import ArtifactError, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Existing validation-only extraction with the qualified helper")
    parser.add_argument("--observer-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("Negative-phase evidence root must be fresh")
    output.mkdir()
    relays = output / "relays"
    relays.mkdir()
    (output / "empty.config").write_bytes(b"")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PROGRAMDATA") if key in os.environ}
    env.update({"PATH": str(root / "mingwarm64/bin") + os.pathsep + str(root / "usr/bin") + os.pathsep +
                        str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(output), "USERPROFILE": str(output), "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(output / "empty.config"), "GIT_TERMINAL_PROMPT": "0",
                "GIT_AUTHOR_NAME": "Native fixture", "GIT_COMMITTER_NAME": "Native fixture",
                "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                "WOARM64_NATIVE_EXIT_DIR": str(relays),
                "WOARM64_EXIT_CONTRACT_SOURCE_SHA256": "f48410b8162602ca6f5b6366c49d424c3b58c7aa222899073add0212df06a082"})
    git = root / "mingwarm64/bin/git.exe"
    repo = output / "repo"
    subprocess.run([git, "init", "--initial-branch=main", repo], env=env, capture_output=True, check=True)
    (repo / "payload.txt").write_text("initial\n")
    subprocess.run([git, "-C", repo, "add", "payload.txt"], env=env, capture_output=True, check=True)
    subprocess.run([git, "-C", repo, "commit", "-m", "initial"], env=env, capture_output=True, check=True)
    before = subprocess.check_output([git, "-C", repo, "rev-parse", "HEAD"], env=env)
    hook = repo / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nprintf 'negative-hook-executed\\n' > .git/negative-hook-observed\nexit 73\n",
                    encoding="utf-8", newline="\n")
    (repo / "payload.txt").write_text("changed\n")
    phase = Path(__file__).with_name("negative_hook_phase.sh").resolve()
    arguments = ["/usr/bin/msys-exit-contract.exe", "--spawn", "msys-git-hook-negative-v1", "1",
                 "/usr/bin/bash", phase.as_posix(), "/mingwarm64/bin/git.exe", repo.as_posix()]
    command = [sys.executable, "-I", "-B", str(args.observer_source / "native-job.py"),
               "--cwd", str(output), "--target-root", str(root), "--relay-records", str(relays),
               "--log", str(output / "run.log"), "--result", str(output / "native-job.json"),
               "--timeout", "90", "--", str(root / "usr/bin/bash.exe"), "--noprofile", "--norc", "-c",
               '"$@"; test "$(cat "$MVP_REPO/.git/negative-hook-observed")" = negative-hook-executed',
               "negative-hook-cause", *arguments]
    env["MVP_REPO"] = repo.as_posix()
    process = subprocess.run(command, env=env, capture_output=True, timeout=110)
    (output / "observer.stderr").write_bytes(process.stderr)
    (output / "observer.stdout").write_bytes(process.stdout)
    after = subprocess.check_output([git, "-C", repo, "rev-parse", "HEAD"], env=env)
    observation = json.loads((output / "native-job.json").read_text())
    marker = (repo / ".git/negative-hook-observed").read_text().strip()
    write_json(output / "result.json", {
        "schema": 1, "scope": "Exact negative-hook phase causality; no new observer allowance requested by this script",
        "phase_path": str(phase), "phase_sha256": sha256(phase), "argv": arguments,
        "hook_sha256": sha256(hook), "hook_observed": marker, "head_unchanged": before == after,
        "parent_raw_exit": observation["parent_raw_exit"], "observer_exit": process.returncode,
        "observer_passed": observation["passed"], "unrelayed_high_exits": observation["unrelayed_high_exits"],
        "observer_sha256": sha256(args.observer_source / "native-job.py"),
        "native_job_sha256": sha256(output / "native-job.json"),
        "helper_records": [json.loads(path.read_text()) for path in relays.glob("*.json")]})
    print(json.dumps({"parent_raw_exit": observation["parent_raw_exit"], "marker": marker,
                      "head_unchanged": before == after, "unrelayed_high_exits": observation["unrelayed_high_exits"]}))


if __name__ == "__main__":
    main()
