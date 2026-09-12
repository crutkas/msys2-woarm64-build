"""Exercise native find/xargs and their argument boundary to an ordinary Windows program."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from sources import ContractError, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "prefix", "output", "pwsh", "artifact-gate", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ContractError("Use a new fixture directory")
    args.output.mkdir(parents=True)
    tree = args.output / "tree"
    tree.mkdir()
    names = ("plain.txt", "with spaces.txt", "unicode-\u03bb.txt")
    for name in names:
        (tree / name).write_text("fixture\n")
    probe = args.output / "native-argv-probe.exe"
    source = Path(__file__).parent / "fixtures/native-argv-probe.c"
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
    env.update({"PATH": os.pathsep.join(map(str, (args.root / "usr/bin", args.prefix / "bin",
                                                 Path(os.environ["SystemRoot"]) / "System32"))),
                "LC_ALL": "C.UTF-8"})
    (args.output / "temp").mkdir()
    env["TMP"] = env["TEMP"] = str(args.output / "temp")
    compile_result = subprocess.run([str(args.prefix / "bin/gcc.exe"), "-O2", "-municode", str(source),
                                     "-o", str(probe)], env=env, capture_output=True)
    (args.output / "compile.stdout").write_bytes(compile_result.stdout)
    (args.output / "compile.stderr").write_bytes(compile_result.stderr)
    if compile_result.returncode:
        raise ContractError("Native argument probe compilation failed")
    subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.artifact_gate),
                    "-Path", str(probe), "-ReportPath", str(args.output / "probe-native.json")], check=True)
    executable = args.root / "usr/bin/find.exe"
    result = subprocess.run([str(executable), "tree", "-type", "f", "-name", "*.txt", "-print0"],
                            cwd=args.output, env=env, capture_output=True, timeout=15)
    (args.output / "find.stdout").write_bytes(result.stdout)
    (args.output / "find.stderr").write_bytes(result.stderr)
    expected = {f"tree/{name}" for name in names}
    found = {part.decode("utf-8") for part in result.stdout.split(b"\0") if part}
    records = [{"case": "find-unicode-and-spaces", "passed": result.returncode == 0 and
                not result.stderr and found == expected}]
    arguments = ["space value", 'quote"inside', "trailing\\", "", "\u03bb \U0001f642"]
    expected_lines = []
    for argument in arguments:
        encoded = argument.encode("utf-16-le")
        units = "".join(f"{int.from_bytes(encoded[index:index+2], 'little'):04x}"
                        for index in range(0, len(encoded), 2))
        expected_lines.append(f"{len(encoded)//2}:{units}")
    process = subprocess.Popen([str(args.root / "usr/bin/xargs.exe"), "-0", str(probe)],
                               cwd=args.output, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        subprocess.run([str(args.pwsh), "-NoProfile", "-File", str(args.process_gate),
                        "-ProcessId", str(process.pid),
                        "-ReportPath", str(args.output / "xargs-native-process.json")], check=True)
        stdout, stderr = process.communicate("\0".join([*arguments, ""]).encode("utf-8"), timeout=15)
        (args.output / "xargs.stdout").write_bytes(stdout)
        (args.output / "xargs.stderr").write_bytes(stderr)
        records.append({"case": "xargs-native-windows-argv", "passed": process.returncode == 0 and
                        not stderr and stdout.decode("ascii").splitlines() == expected_lines})
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    windows_tree = tree.resolve().as_posix()
    proc_tree = f"/proc/cygdrive/{windows_tree[0].lower()}/{windows_tree[3:]}"
    result = subprocess.run([str(executable), proc_tree, "-type", "f", "-exec", str(probe),
                             "--check-files", "{}", ";"], cwd=args.output, env=env,
                            capture_output=True, timeout=20)
    (args.output / "find-exec.stdout").write_bytes(result.stdout)
    (args.output / "find-exec.stderr").write_bytes(result.stderr)
    records.append({"case": "find-exec-windows-paths", "passed": result.returncode == 0 and
                    not result.stderr and result.stdout.decode().splitlines() == ["file-ok"] * len(names)})
    report = {"passed": all(record["passed"] for record in records), "cases": records,
              "scope": "Owned files only; no locate database or global filesystem scan",
              "find_sha256": digest(executable), "xargs_sha256": digest(args.root / "usr/bin/xargs.exe"),
              "probe_sha256": digest(probe)}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ContractError("Native find/xargs scenario failed; evidence retained")
    print("Native find/xargs and Windows argument/path interoperability passed")


if __name__ == "__main__":
    main()
