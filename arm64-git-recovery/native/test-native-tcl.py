"""Exercise a relocated source-built Tcl with a hermetic PATH and live native/DLL evidence."""

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
    for name in ("root", "manifest", "output", "pwsh", "process-gate", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--tk", action="store_true")
    parser.add_argument("--winapp", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("Native Tcl fixture requires fresh output")
    if args.tk and args.winapp is None:
        raise ContractError("Tk keyboard/window evidence requires the explicit installed UI harness")
    verify_tree(args.root, args.manifest)
    original = inventory(args.root)
    root = args.output / "relocated"
    shutil.copytree(args.root, root)
    if inventory(root) != original:
        raise ContractError("Relocated Tcl copy differs")
    binary = root / ("bin/wish.exe" if args.tk else "bin/tclsh.exe")
    fixture = Path(__file__).parent / "fixtures/native-tcl-smoke.tcl"
    driver = fixture.with_name("native-tcl-test-driver.tcl")
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
    env.update({"PATH": str(root / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(args.output), "USERPROFILE": str(args.output),
                "TMP": str(args.output), "TEMP": str(args.output)})
    report = {"passed": False, "source_receipt_sha256": digest(args.manifest),
              "fixture_sha256": digest(fixture),
              "driver_sha256": digest(driver),
              "scope": "Relocated Tcl library discovery, UTF-8/file/zlib/arithmetic, in-memory SQLite/TDBC and threads"}
    if args.tk:
        report["tk_fixture_sha256"] = digest(fixture.with_name("native-tk-widgets.tcl"))
        report["ui_scope"] = "Native Tk window/PNG/fonts and HWND-targeted keyboard-to-button callback, not full UIA accessibility"

    def observe(pid):
        ready = args.output / "ready"
        failure = args.output / "fixture-error.txt"
        deadline = time.monotonic() + 20
        while not ready.exists() and not failure.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if failure.exists():
            raise ContractError(f"Native Tcl fixture failed: {failure.read_text()[:2000]}")
        if not ready.exists() or ready.read_text().strip() != str(pid):
            raise ContractError("The held Tcl process did not complete its functional fixture")
        process_report = args.output / "native-process.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                        "-ProcessId", str(pid), "-ReportPath", str(process_report)], check=True)
        identity = json.loads(process_report.read_text())
        if identity.get("Passed") is not True or Path(identity["Processes"][0]["ImagePath"]).resolve() != binary.resolve():
            raise ContractError("Observed Tcl process is not the relocated native executable")
        command = (f"(Get-Process -Id {pid}).Modules | ForEach-Object {{"
                   "[ordered]@{name=$_.ModuleName;path=$_.FileName;sha256=(Get-FileHash -LiteralPath $_.FileName).Hash}} | "
                   "ConvertTo-Json -Compress")
        observed = subprocess.run([str(args.pwsh), "-NoProfile", "-Command", command],
                                  capture_output=True, check=True)
        modules = json.loads(observed.stdout)
        (args.output / "loaded-modules.json").write_text(json.dumps(modules, indent=2) + "\n")
        loaded = {row["name"].lower(): row for row in modules}
        required = ("tcl86.dll", "libz.dll", "sqlite3530.dll", "tdbc1113.dll", "thread2813.dll",
                    *(["tk86.dll"] if args.tk else []))
        for name in required:
            row = loaded.get(name)
            if row is None:
                raise ContractError(f"Required native Tcl module was not loaded: {name}")
            path = Path(row["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ContractError(f"Tcl module came from outside its relocated stage: {name}")
            relative = path.relative_to(root.resolve()).as_posix()
            if row["sha256"].lower() != original[relative]["sha256"]:
                raise ContractError(f"Loaded Tcl module differs: {name}")
        if args.tk:
            widgets = json.loads((args.output / "widgets.json").read_text())
            report["tk_window_handles"] = widgets
            widgets = {name: str(int(value, 0)) for name, value in widgets.items()}
            if any(value == "0" for value in widgets.values()):
                raise ContractError("Tk returned an invalid native window handle")
            commands = [
                ["inspect", "-w", widgets["window"], "--interactive", "--json"],
                ["screenshot", "-w", widgets["window"], "-o", str(args.output / "initial.png")],
                ["send-keys", "--verbatim", "native Tk \u03bb", "-w", widgets["entry"], "--via", "post-message"],
                ["send-keys", "enter", "-w", widgets["entry"], "--via", "post-message"],
            ]
            report["ui_commands"] = []
            for arguments in commands:
                result = subprocess.run([str(args.winapp), "ui", *arguments], capture_output=True, timeout=20)
                report["ui_commands"].append({"arguments": arguments, "exit": result.returncode,
                                               "stdout": result.stdout.decode(errors="replace"),
                                               "stderr": result.stderr.decode(errors="replace")})
                if result.returncode:
                    raise ContractError(f"Native Tk UI harness failed: {arguments[0]}")
            deadline = time.monotonic() + 5
            saved = args.output / "tk-saved.txt"
            while not saved.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not saved.exists() or saved.read_bytes() != "native Tk \u03bb".encode():
                raise ContractError("Native Tk keyboard/button callback did not save exact Unicode")
            subprocess.run([str(args.winapp), "ui", "screenshot", "-w", widgets["window"],
                            "-o", str(args.output / "saved.png")], check=True, timeout=20)
        (args.output / "continue").write_bytes(b"go\n")

    try:
        gate = args.output / "native-pe.json"
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                        "-Root", str(root), "-ReportPath", str(gate)], check=True)
        if json.loads(gate.read_text()).get("Passed") is not True:
            raise ContractError("Relocated Tcl PE gate failed")
        with (args.output / "run.log").open("xb") as log:
            report["process"] = run([binary, driver, fixture, root, args.output, *(["tk"] if args.tk else [])], cwd=args.output,
                                    env=env, log=log, timeout=180 if args.tk else 90, on_started=observe)
        if not report["process"]["passed"] or b"native-tcl-smoke-passed" not in (args.output / "run.log").read_bytes():
            raise ContractError("Native Tcl functional fixture failed")
        expected = ("native Tcl \u03bb \u96ea\n" * 4096).encode()
        if (args.output / "roundtrip-\u03bb.txt").read_bytes() != expected:
            raise ContractError("Tcl Unicode file output differs")
        if inventory(root) != original:
            raise ContractError("The relocated Tcl payload changed")
        verify_tree(args.root, args.manifest)
        report["passed"] = True
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Relocated native Tcl/Tk libraries and functional behavior passed")


if __name__ == "__main__":
    main()
