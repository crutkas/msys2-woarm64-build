"""Exercise native nano through its own MSYS PTY implementation, with Windows job containment."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from bounded_process import run
from sources import ContractError, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "runner", "output", "pwsh", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--curses-probe", type=Path, help="Exercise the actual C++ curses library instead of nano")
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("Fresh native editor fixture required")
    args.output.mkdir(parents=True)
    (args.output / "home").mkdir()
    fixture_root = args.output / "runtime"
    binaries = fixture_root / "usr/bin"
    binaries.mkdir(parents=True)
    runner = binaries / "editor-pty.exe"
    runtime = binaries / "msys-2.0.dll"
    shutil.copyfile(args.runner, runner)
    copied = {}
    names = ["msys-2.0.dll", "msys-ncursesw6.dll"]
    names += ["msys-ncurses++w6.dll", "msys-panelw6.dll", "msys-menuw6.dll", "msys-formw6.dll"] if args.curses_probe else ["nano.exe"]
    for name in names:
        source = args.root / "usr/bin" / name
        destination = binaries / name
        shutil.copyfile(source, destination)
        copied[name] = {"source": str(source), "sha256": digest(source)}
        if digest(destination) != copied[name]["sha256"]:
            raise ContractError("Editor fixture DLL or executable copy differs")
    terminfo = fixture_root / "usr/share/terminfo/78"
    terminfo.mkdir(parents=True)
    shutil.copyfile(args.root / "usr/share/terminfo/78/xterm-256color", terminfo / "xterm-256color")
    fixture = args.output / "editor.txt"
    fixture.write_bytes(b"before\n")
    editor = binaries / "nano.exe"
    if args.curses_probe:
        editor = binaries / "curses-probe.exe"
        shutil.copyfile(args.curses_probe, editor)
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env.update({"PATH": str(binaries) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(args.output / "home"), "TERM": "xterm-256color", "LC_ALL": "C.UTF-8",
                "TERMINFO": str(fixture_root / "usr/share/terminfo"), "TMP": str(args.output), "TEMP": str(args.output)})
    report = {"passed": False, "scope": "Actual MSYS PTY edit/save of owned Unicode file; no desktop/config/auth changes",
              "runner_sha256": digest(runner), "runtime_sha256": digest(runtime), "nano_sha256": digest(editor)}
    report["copied_native_inputs"] = copied
    if args.curses_probe:
        report["scope"] = "Actual native C++ curses window, varargs/readback and terminal input; no fake C++ headers"

    def observe(parent_pid):
        ready = args.output / "editor-ready.json"
        end = time.monotonic() + 20
        while not ready.exists() and time.monotonic() < end:
            time.sleep(0.05)
        if not ready.exists():
            raise ContractError("Native editor did not render in its MSYS terminal")
        child = json.loads(ready.read_text())
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                        "-ProcessId", str(child["windows_pid"]),
                        "-ReportPath", str(args.output / "nano-native-process.json")], check=True)
        identity = json.loads((args.output / "nano-native-process.json").read_text())
        if identity.get("Passed") is not True or identity["Processes"][0]["ImagePath"].casefold() != str(editor).casefold():
            raise ContractError("Observed editor process differs")
        script = (f"(Get-Process -Id {child['windows_pid']}).Modules | ForEach-Object {{"
                  "[ordered]@{name=$_.ModuleName;path=$_.FileName;sha256=(Get-FileHash -LiteralPath $_.FileName).Hash}} | "
                  "ConvertTo-Json -Compress")
        observed = subprocess.run([str(args.pwsh), "-NoProfile", "-Command", script],
                                  capture_output=True, check=True)
        modules = json.loads(observed.stdout)
        (args.output / "loaded-modules.json").write_text(json.dumps(modules, indent=2) + "\n")
        loaded = {row["name"].lower(): row for row in modules}
        required = ("msys-2.0.dll", "msys-ncursesw6.dll", *(["msys-ncurses++w6.dll"] if args.curses_probe else []))
        for name in required:
            row = loaded.get(name)
            if (row is None or Path(row["path"]).resolve() != (binaries / name).resolve()
                    or row["sha256"].lower() != copied[name]["sha256"]):
                raise ContractError(f"Different native terminal library loaded: {name}")
        report["parent_windows_pid"] = parent_pid
        report["editor_windows_pid"] = child["windows_pid"]
        (args.output / "continue").write_bytes(b"go\n")

    try:
        with (args.output / "runner.log").open("xb") as log:
            command = [runner, editor, fixture, *(["curses"] if args.curses_probe else [])]
            report["process"] = run(command, cwd=args.output, env=env, log=log,
                                    timeout=90, on_started=observe)
        report["saved_hex"] = fixture.read_bytes().hex()
        report["passed"] = report["process"]["passed"] and fixture.read_bytes() == "before after \u03bb\n".encode()
        if args.curses_probe:
            report["window"] = json.loads(fixture.read_text())
            report["passed"] = report["process"]["passed"] and report["window"]["passed"] is True
        if any(digest(row["source"]) != row["sha256"] or digest(binaries / name) != row["sha256"]
               for name, row in copied.items()):
            raise ContractError("A terminal fixture input changed during execution")
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ContractError("Native nano edit/save fixture failed")
    print("Native C++ curses window/formatting/readback/input passed" if args.curses_probe else
          "Native nano edited and saved the exact Unicode fixture through MSYS PTY")


if __name__ == "__main__":
    main()
