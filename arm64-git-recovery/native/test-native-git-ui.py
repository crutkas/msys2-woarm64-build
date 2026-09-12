"""Exercise installed GitGUI/gitk sources on a disposable repository with actual native Tk and Git."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from bounded_process import run
from sources import ContractError, digest, inventory, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "manifest", "output", "pwsh", "process-gate", "artifact-gate", "winapp"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--tool", action="append", choices=("gitk", "git-gui"))
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("A fresh isolated Git UI fixture is required")
    verify_tree(args.root, args.manifest)
    original = inventory(args.root)
    root = args.output / "relocated"
    shutil.copytree(args.root, root)
    if inventory(root) != original:
        raise ContractError("Git UI fixture copy differs")
    for name in ("home", "temp", "repository"):
        (args.output / name).mkdir()
    global_config = args.output / "empty-global-config"
    global_config.write_bytes(b"")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (root / "usr/bin", root / "clangarm64/bin",
                                                Path(os.environ["SystemRoot"]) / "System32"))),
                "HOME": str(args.output / "home"), "USERPROFILE": str(args.output / "home"),
                "TMP": str(args.output / "temp"), "TEMP": str(args.output / "temp"),
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(global_config),
                "GIT_TERMINAL_PROMPT": "0", "GIT_EXEC_PATH": str(root / "clangarm64/libexec/git-core")})
    repo = args.output / "repository"
    git = root / "clangarm64/bin/git.exe"
    wish = root / "usr/bin/wish.exe"
    fixtures = Path(__file__).parent / "fixtures"
    fixture = fixtures / "native-git-gui.tcl"
    driver = fixtures / "native-tcl-test-driver.tcl"
    report = {"passed": False, "source_manifest_sha256": digest(args.manifest),
              "fixture_sha256": digest(fixture), "driver_sha256": digest(driver),
              "scope": "Actual installed GitGUI/gitk sources with native Tk, real local Git repository/content; launcher wrappers and edit/commit UI actions are separate",
              "requested_tools": args.tool or ["gitk", "git-gui"],
              "text_policy": "Repository-local gui.encoding=utf-8; default Windows system codepage is not changed",
              "setup": [], "cases": []}

    def git_command(*arguments):
        index = len(report["setup"])
        with (args.output / f"git-{index}.log").open("xb") as log:
            result = run([git, *arguments], cwd=repo, env=env, log=log, timeout=30)
        report["setup"].append({"arguments": arguments, "process": result})
        if not result["passed"]:
            raise ContractError("Disposable Git UI repository setup failed")

    try:
        gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(root), "-ReportPath", str(gate)], check=True)
        if json.loads(gate.read_text()).get("Passed") is not True:
            raise ContractError("Integrated Git GUI native PE gate failed")
        git_command("init", "--initial-branch=main")
        git_command("config", "user.name", "Native fixture")
        git_command("config", "user.email", "fixture@example.invalid")
        git_command("config", "gui.encoding", "utf-8")
        (repo / "tracked.txt").write_text("first native content\n", newline="\n")
        git_command("add", "tracked.txt")
        git_command("commit", "-m", "Native ARM64 first fixture")
        (repo / "tracked.txt").write_text("second native content \u03bb\n", encoding="utf-8", newline="\n")
        git_command("commit", "-am", "Native ARM64 second fixture")
        (repo / "tracked.txt").write_text("uncommitted native change \u03bb\n", encoding="utf-8", newline="\n")
        for tool in report["requested_tools"]:
            output = args.output / tool
            output.mkdir()
            case = {"tool": tool, "passed": False}
            report["cases"].append(case)

            def observe(pid):
                ready, failure = output / "ready", output / "fixture-error.txt"
                deadline = time.monotonic() + 25
                while not ready.exists() and not failure.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if failure.exists():
                    raise ContractError(f"Git UI fixture error: {failure.read_text(encoding='utf-8')[:2000]}")
                if not ready.exists() or ready.read_text().strip() != str(pid):
                    raise ContractError("Git GUI did not finish loading its repository content")
                process_report = output / "native-process.json"
                subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                                "-ProcessId", str(pid), "-ReportPath", str(process_report)], check=True)
                identity = json.loads(process_report.read_text())
                if (identity.get("Passed") is not True or
                        Path(identity["Processes"][0]["ImagePath"]).resolve() != wish.resolve()):
                    raise ContractError("Git UI is not using the integrated native wish")
                command = (f"(Get-Process -Id {pid}).Modules | ForEach-Object {{"
                           "[ordered]@{name=$_.ModuleName;path=$_.FileName;sha256=(Get-FileHash -LiteralPath $_.FileName).Hash}} | "
                           "ConvertTo-Json -Compress")
                result = subprocess.run([str(args.pwsh), "-NoProfile", "-Command", command],
                                        capture_output=True, check=True)
                modules = json.loads(result.stdout)
                (output / "modules.json").write_text(json.dumps(modules, indent=2) + "\n")
                loaded = {row["name"].lower(): row for row in modules}
                for name in ("tk86.dll", "tcl86.dll", "libz.dll"):
                    row = loaded.get(name)
                    expected_path = root / "usr/bin" / name
                    if (row is None or Path(row["path"]).resolve() != expected_path.resolve() or
                            row["sha256"].lower() != digest(expected_path)):
                        raise ContractError(f"Integrated Git GUI loaded a different module: {name}")
                hwnd = str(int((output / "window.txt").read_text().strip(), 0))
                for action in (["inspect", "--interactive", "--json"],
                               ["screenshot", "-o", str(output / "window.png")]):
                    result = subprocess.run([str(args.winapp), "ui", *action, "-w", hwnd],
                                            capture_output=True, timeout=20)
                    (output / f"{action[0]}.stdout").write_bytes(result.stdout)
                    (output / f"{action[0]}.stderr").write_bytes(result.stderr)
                    if result.returncode:
                        raise ContractError(f"Git GUI native UI observation failed: {action[0]}")
                case["widget_text_sha256"] = digest(output / "widget-text.txt")
                case["window_title"] = (output / "title.txt").read_text(encoding="utf-8")
                (output / "continue").write_bytes(b"go\n")

            with (output / "run.log").open("xb") as log:
                case["process"] = run([wish, driver, fixture, root, output, tool],
                                      cwd=repo, env=env, log=log, timeout=90, on_started=observe)
            case["passed"] = (case["process"]["passed"] and
                              b"native-git-gui-fixture-passed" in (output / "run.log").read_bytes())
            if not case["passed"]:
                raise ContractError("Native Git GUI process failed or retained children")
        git_command("fsck", "--strict")
        if inventory(root) != original:
            raise ContractError("Git GUI changed its distribution payload")
        verify_tree(args.root, args.manifest)
        report["passed"] = True
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Integrated native {', '.join(report['requested_tools'])} displayed actual local repository content")


if __name__ == "__main__":
    main()
