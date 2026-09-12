#!/usr/bin/env python3
"""Rebuild one runtime exception object in an isolated copy, using recorded flags."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

RECIPE = Path(__file__).resolve().parent
OFFSETS = "49ac682b8f5ed4295d03abc2dab5953fc472684d42eb0b87d779057942b23566"
SOURCE = "275321387060abc9f643d45fe971956a5e4ea6cec45d409e64958e9ca1bf59a1"
LINK = "4768ec7eb106c3acacf07c4158a6509dbe4c953faf505d048866d3b3df4925e2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "output", "compile-expansion", "link-command"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--control", action="store_true", help="Rebuild unchanged source as a matched control")
    parser.add_argument("--patch", type=Path, default=RECIPE / "runtime-arm64-myfault-context.patch")
    args = parser.parse_args()
    base = args.base.resolve(strict=True)
    if sha(base / "source/winsup/cygwin/exceptions.cc") != SOURCE or sha(args.link_command) != LINK:
        raise ValueError("Runtime source or recorded link command differs")
    tls = base / "pair/a/winsup/cygwin/tlsoffsets"
    if sha(tls) != OFFSETS:
        raise ValueError("Preserved TLS offsets changed before preparation")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    if out == base or out.is_relative_to(base):
        raise ValueError("Use a distinct owner directory")
    inputs, logs = out / "inputs", out / "logs"
    inputs.mkdir()
    logs.mkdir()
    shutil.copy2(tls, inputs / "tlsoffsets.good")
    for original, destination in ((base / "source", out / "source"), (base / "prefix", out / "prefix"),
                                  (base / "pair/a", out / "build")):
        subprocess.run(["cp", "-a", str(original), str(destination)], check=True)
    build = out / "build/winsup/cygwin"
    for name in ("exceptions.o", "libdll.a", "new-msys-2.0.dll", "sigfe.o", "sigfe.s", "libmsys-2.0.a", "crt0.o"):
        shutil.copy2(build / name, inputs / name)
    patch = args.patch.resolve(strict=True)
    shutil.copy2(patch, inputs / "myfault.patch")
    shutil.copy2(Path(__file__), inputs / "replay-runtime-myfault.py")
    shutil.copy2(args.compile_expansion, inputs / "compile-expansion.original.txt")
    shutil.copy2(args.link_command, inputs / "link-command.original.sh")
    before = {str(p.relative_to(out)): sha(p) for p in inputs.iterdir() if p.is_file()}
    report = {"schema": 1, "status": "failed", "base": str(base), "control": args.control,
              "inputs": before, "source_before": SOURCE, "patch_sha256": sha(patch),
              "compile_expansion_sha256": sha(args.compile_expansion), "runs": [], "make_invoked": False}

    def rebase(text):
        for old, new in ((base / "pair/a", out / "build"), (base / "source", out / "source"),
                         (base / "prefix", out / "prefix")):
            text = text.replace(str(old), str(new))
        if str(base) in text:
            raise ValueError("Foreign source/build path remains in the replay command")
        return text

    compile_text = args.compile_expansion.read_text()
    start = compile_text.index("depbase=")
    end = compile_text.index("\nmake: Leaving", start)
    compile_text = "#!/usr/bin/env bash\nset -euo pipefail\ncd -- " + str(build) + "\n" + rebase(compile_text[start:end]) + "\n"
    compile_script = inputs / "compile.sh"
    compile_script.write_text(compile_text, encoding="utf-8", newline="\n")
    link_script = inputs / "link.sh"
    link_script.write_text(rebase(args.link_command.read_text()), encoding="utf-8", newline="\n")
    env = dict(os.environ, PATH=str(out / "prefix/bin") + ":/usr/bin:/bin",
               LC_ALL="C", SOURCE_DATE_EPOCH="1788224411")
    for key in ("LIBRARY_PATH", "COMPILER_PATH", "GCC_EXEC_PREFIX"):
        env.pop(key, None)

    def run(name, command, cwd=build):
        with (logs / (name + ".stdout")).open("xb") as stdout, (logs / (name + ".stderr")).open("xb") as stderr:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, timeout=180)
        report["runs"].append({"name": name, "argv": command, "exit": result.returncode})
        if result.returncode:
            raise ValueError(f"Isolated runtime {name} failed")

    try:
        if not args.control:
            run("patch-check", ["git", "-c", "core.autocrlf=false", "apply", "--check", str(patch)], out / "source")
            run("patch", ["git", "-c", "core.autocrlf=false", "apply", str(patch)], out / "source")
        run("compile", ["bash", str(compile_script)])
        ar = str(out / "prefix/bin/aarch64-pc-cygwin-ar")
        for name, archive in (("original", inputs / "libdll.a"),):
            directory = out / (name + "-members")
            directory.mkdir()
            run(name + "-members", [ar, "x", str(archive)], directory)
        run("replace-exception-member", [ar, "rD", "libdll.a", "exceptions.o"])
        run("link", ["bash", str(link_script)])
        members = out / "candidate-members"
        members.mkdir()
        run("candidate-members", [ar, "x", str(build / "libdll.a")], members)
        original = {p.name: sha(p) for p in (out / "original-members").iterdir()}
        candidate = {p.name: sha(p) for p in members.iterdir()}
        changed = [name for name in set(original) | set(candidate) if original.get(name) != candidate.get(name)]
        if set(changed) - {"exceptions.o"}:
            raise ValueError(f"Unrelated runtime members changed: {changed}")
        if sha(tls) != OFFSETS or sha(build / "tlsoffsets") != OFFSETS:
            raise ValueError("TLS offsets changed")
        if sha(base / "source/winsup/cygwin/exceptions.cc") != SOURCE:
            raise ValueError("Original runtime source changed")
        report.update(status="private-runtime-myfault-relink-complete-not-native-qualified",
                      source_after=sha(out / "source/winsup/cygwin/exceptions.cc"),
                      changed_members=changed,
                      outputs={name: {"path": str(build / name), "sha256": sha(build / name)}
                               for name in ("new-msys-2.0.dll", "libdll.a", "exceptions.o", "sigfe.o", "sigfe.s",
                                            "libmsys-2.0.a", "crt0.o")},
                      scope="One exception translation unit; unchanged TLS/trampolines and all other archive members. Recorded compile expansion and actual link replay fully rebased.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(out / "result.json")


if __name__ == "__main__":
    main()
