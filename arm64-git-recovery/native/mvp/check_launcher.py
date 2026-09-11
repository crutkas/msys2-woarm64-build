"""Exercise the shipped CMD entrypoint with a bounded command, without claiming PTY qualification."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bounded_process import run
from artifact import ArtifactError, inventory, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    if output.exists():
        raise ArtifactError("A fresh launcher evidence directory is required")
    if any(character in str(root) for character in '%!\r\n"'):
        raise ArtifactError("The launcher fixture does not support CMD expansion characters in its root")
    before = inventory(root)
    launcher = root / "Git-Bash-Native.cmd"
    if not launcher.is_file() or before.get("usr/bin/bash.exe", {}).get("machine") != "0xAA64":
        raise ArtifactError("The native console entrypoint is missing")
    output.mkdir(parents=True)
    home = output / "home"
    home.mkdir()
    fixture = output / "invoke.cmd"
    fixture.write_text(
        '@echo off\n'
        f'call "{launcher}" -c "test \\"$MSYSTEM\\" = MINGWARM64 && '
        'test \\"$MSYS\\" = winsymlinks:sys && printf \'native-console-entry-ok\\n\' && git --version"\n'
        'exit /b %ERRORLEVEL%\n', encoding="utf-8", newline="\r\n")
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "PROGRAMDATA")
           if name in os.environ}
    env.update({"PATH": str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(home), "USERPROFILE": str(home), "TMP": str(output), "TEMP": str(output)})
    report = {"schema": 1, "passed": False, "root": str(root), "launcher_sha256": sha256(launcher),
              "fixture_sha256": sha256(fixture),
              "scope": "Actual CMD-to-login-Bash entrypoint and Git selection; redirected console, not PTY/job-control qualification"}
    try:
        with (output / "run.log").open("xb") as log:
            report["process"] = run([env["COMSPEC"], "/d", "/c", fixture],
                                    cwd=output, env=env, log=log, timeout=30)
        lines = (output / "run.log").read_text(encoding="utf-8").splitlines()
        report["inputs_unchanged"] = inventory(root) == before
        report["passed"] = (report["process"]["passed"] and report["inputs_unchanged"]
                            and "native-console-entry-ok" in lines
                            and "git version 2.55.0.windows.5" in lines)
    finally:
        write_json(output / "result.json", report)
    print(json.dumps(report))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
