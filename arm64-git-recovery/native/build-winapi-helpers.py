"""Build real credential helpers with explicitly identified cross or native Windows tools."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from sources import ContractError, digest, inventory, verify_tree
from compiler_tools import support_identities, verify_support


EXTRA_HELPERS = ("git-askpass.exe", "git-askyesno.exe", "git-credential-helper-selector.exe")
TARGET = "aarch64-w64-mingw32"
LINK_INPUTS = ("crt2.o", "crt2u.o", "libmingw32.a", "libmingwex.a", "libucrt.a",
               "libgcc.a", "libkernel32.a", "libuser32.a", "libadvapi32.a",
               "libgdi32.a", "libcomctl32.a")


def run(command, log, cwd=None, env=None):
    log.write("$ " + json.dumps(command) + "\n")
    log.flush()
    result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, check=False)
    log.write(result.stdout + "\n")
    log.flush()
    if result.returncode:
        raise ContractError(f"Command failed ({result.returncode}): {command[0]}; inspect build.log")
    return result.stdout.strip()


def build(sources, prefix, output, jobs, check_only=False, component="all"):
    if sys.platform != "linux" or platform.machine().lower() not in ("aarch64", "arm64"):
        raise ContractError("This driver is explicitly Linux-ARM64-hosted cross compilation")
    if not check_only and jobs < 1:
        raise ContractError("An explicitly approved positive compile-job budget is required")
    if component not in ("all", "wincred", "prompts"):
        raise ContractError("Unknown helper component")
    extra_helpers = () if component == "wincred" else EXTRA_HELPERS
    want_wincred = component != "prompts"
    sources, prefix, output = (Path(p).resolve() for p in (sources, prefix, output))
    if any(any(c.isspace() for c in str(p)) for p in (sources, prefix, output)):
        raise ContractError("The upstream Makefile requires build/tool/source paths without whitespace")
    if output.exists():
        raise ContractError("Use a new output directory; existing builds are never overwritten")
    compiler = prefix / "bin" / f"{TARGET}-gcc"
    windres = prefix / "bin" / f"{TARGET}-windres"
    for tool in (compiler, windres):
        if not tool.is_file():
            raise ContractError(f"Missing cross tool: {tool}")
    if not shutil.which("make"):
        raise ContractError("Missing host make; contact the bootstrap owner")
    for source in ("git-full", "build-extra"):
        verify_tree(sources / source, sources / f"{source}.inventory.json")
    tools = {str(tool): digest(tool) for tool in (compiler, windres)}
    environment = dict(os.environ)
    environment["PATH"] = str(prefix / "bin") + os.pathsep + environment.get("PATH", "")
    support_tools = support_identities(compiler, prefix, environment)
    output.mkdir(parents=True)
    with (output / "build.log").open("x", encoding="utf-8", newline="\n") as log:
        if run([str(compiler), "-dumpmachine"], log) != TARGET:
            raise ContractError("Wrong compiler target")
        inputs = {}
        for name in LINK_INPUTS:
            path = Path(run([str(compiler), f"-print-file-name={name}"], log))
            if not path.is_absolute() or not path.is_file():
                raise ContractError(f"MinGW CRT/import-library boundary is incomplete: {name}")
            inputs[name] = {"path": str(path), "sha256": digest(path)}
        if check_only:
            (output / "preflight.json").write_text(json.dumps({
                "status": "inputs-present-not-built", "target": TARGET, "inputs": inputs,
                "support_tools": support_tools
            }, indent=2) + "\n", encoding="utf-8")
            return
        extra = output / "extra-source"
        wincred = output / "wincred-source"
        if extra_helpers:
            shutil.copytree(sources / "build-extra/git-extra", extra)
        if want_wincred:
            shutil.copytree(sources / "git-full/contrib/credential/wincred", wincred)
        binaries = output / "binaries"
        binaries.mkdir()
        if extra_helpers:
            run(["make", f"-j{jobs}", "-f", "Makefile", f"CC={compiler}",
                 f"WINDRES={windres}", f"SRCDIR={extra}", f"BUILDDIR={binaries}",
                 "LDFLAGS=-Wl,--tsaware,--no-insert-timestamp",
                 *(str(binaries / name) for name in extra_helpers)], log, extra, environment)
        if want_wincred:
            run(["make", f"-j{jobs}", f"CC={compiler}",
                 "LDFLAGS=-Wl,--no-insert-timestamp", "LDLIBS=-ladvapi32",
                 "git-credential-wincred.exe"], log, wincred, environment)
        stage = output / "stage/clangarm64"
        (stage / "bin").mkdir(parents=True)
        (stage / "libexec/git-core").mkdir(parents=True)
        for name in extra_helpers:
            shutil.copyfile(binaries / name, stage / "bin" / name)
        if want_wincred:
            shutil.copyfile(wincred / "git-credential-wincred.exe",
                            stage / "libexec/git-core/git-credential-wincred.exe")
        licenses = stage / "share/licenses/native-credential-helpers"
        licenses.mkdir(parents=True)
        shutil.copyfile(sources / "build-extra/LICENSE.txt", licenses / "build-extra-LICENSE.txt")
        shutil.copyfile(sources / "git-full/COPYING", licenses / "git-COPYING")
        # Reject toolchain/CRT churn during linking rather than attaching stale provenance.
        for record in inputs.values():
            if digest(record["path"]) != record["sha256"]:
                raise ContractError(f"Link input changed during helper build: {record['path']}")
        for path, expected in tools.items():
            if digest(path) != expected:
                raise ContractError(f"Cross tool changed during helper build: {path}")
        verify_support(support_tools, compiler, prefix, environment)
        evidence = {
            "schema": 1, "status": "built-not-run", "build_host": "linux-aarch64-cross",
            "target": TARGET, "scope": "Selected real helpers only; not a complete git-extra package or Git distribution",
            "component": component, "helpers": list(extra_helpers) +
                (["git-credential-wincred.exe"] if want_wincred else []),
            "approved_jobs": jobs,
            "compiler": {"path": str(compiler), "sha256": tools[str(compiler)]},
            "windres": {"path": str(windres), "sha256": tools[str(windres)]},
            "source_manifests": {s: digest(sources / f"{s}.inventory.json")
                                 for s in ("git-full", "build-extra")},
            "link_inputs": inputs, "files": inventory(output / "stage"),
            "support_tools": support_tools,
            "pending": ["raw-native-ARM64-PE", "native-process", "credential-storage", "GUI-interaction"]
        }
        (output / "build-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n",
                                                   encoding="utf-8")


def build_windows(sources, prefix, native_root, output, jobs, pwsh, artifact_gate):
    if os.name != "nt" or not 1 <= jobs <= 10:
        raise ContractError("Native Windows and an explicit 1-10 job allocation are required")
    sources, prefix, native_root, output = map(lambda path: Path(path).resolve(),
                                              (sources, prefix, native_root, output))
    if output.exists() or any(" " in str(path) for path in (prefix, output)):
        raise ContractError("Use new space-free build/tool paths for the upstream Makefiles")
    for source in ("git-full", "build-extra"):
        verify_tree(sources / source, sources / f"{source}.inventory.json")
    native_files = inventory(native_root)
    compiler, windres = prefix / "bin/gcc.exe", prefix / "bin/windres.exe"
    make = native_root / "usr/bin/make.exe"
    env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC") if name in os.environ}
    env["PATH"] = os.pathsep.join(map(str, (native_root / "usr/bin", prefix / "bin",
                                          Path(os.environ["SystemRoot"]) / "System32")))
    env["LC_ALL"] = "C"
    support = support_identities(compiler, prefix, env)
    tools = {str(path): digest(path) for path in (compiler, windres, make, native_root / "usr/bin/bash.exe")}
    output.mkdir(parents=True)
    (output / "binaries").mkdir()
    (output / "temp").mkdir()
    env["TMP"] = env["TEMP"] = str(output / "temp")
    shutil.copytree(sources / "build-extra/git-extra", output / "extra-source")
    shutil.copytree(sources / "git-full/contrib/credential/wincred", output / "wincred-source")
    report = {"schema": 1, "status": "failed", "build_host": "windows-arm64-native",
              "orchestration": "native-make-bash-coreutils", "target": TARGET,
              "scope": "Real selected helpers; not full git-extra, SDK or Git distribution acceptance",
              "tools": tools, "support_tools": support, "native_root": native_files,
              "source_manifests": {name: digest(sources / f"{name}.inventory.json")
                                   for name in ("git-full", "build-extra")}}
    try:
        with (output / "build.log").open("x", encoding="utf-8") as log:
            for name, root in (("compiler-inputs", prefix), ("posix-inputs", native_root)):
                gate_report = output / f"{name}.json"
                run([str(pwsh), "-NoProfile", "-File", str(artifact_gate),
                     "-Root", str(root), "-ReportPath", str(gate_report)], log, env=env)
                proof = json.loads(gate_report.read_text())
                if proof.get("Passed") is not True or not proof.get("CandidateCount"):
                    raise ContractError("Nonempty native tool input gates are required")
            if run([str(compiler), "-dumpmachine"], log, env=env) != TARGET:
                raise ContractError("Wrong native compiler target")
            inputs = {}
            for name in LINK_INPUTS:
                path = Path(run([str(compiler), f"-print-file-name={name}"], log, env=env))
                if not path.is_absolute() or not path.is_file() or not path.resolve().is_relative_to(prefix):
                    raise ContractError(f"Native helper link input missing or outside prefix: {name}")
                inputs[name] = {"path": str(path), "sha256": digest(path)}
            report["link_inputs"] = inputs
            run([str(make), f"-j{jobs}", "-f", "extra-source/Makefile",
                 f"CC={compiler.as_posix()}", f"WINDRES={windres.as_posix()}",
                 "SRCDIR=extra-source", "BUILDDIR=binaries",
                 "LDFLAGS=-Wl,--tsaware,--no-insert-timestamp",
                 *[f"binaries/{name}" for name in EXTRA_HELPERS]], log, output, env)
            run([str(make), f"-j{jobs}", f"CC={compiler.as_posix()}",
                 "LDFLAGS=-Wl,--no-insert-timestamp", "LDLIBS=-ladvapi32",
                 "git-credential-wincred.exe"], log, output / "wincred-source", env)
        stage = output / "stage/clangarm64"
        (stage / "bin").mkdir(parents=True)
        (stage / "libexec/git-core").mkdir(parents=True)
        for name in EXTRA_HELPERS:
            shutil.copyfile(output / "binaries" / name, stage / "bin" / name)
        shutil.copyfile(output / "wincred-source/git-credential-wincred.exe",
                        stage / "libexec/git-core/git-credential-wincred.exe")
        licenses = stage / "share/licenses/native-credential-helpers"
        licenses.mkdir(parents=True)
        shutil.copyfile(sources / "build-extra/LICENSE.txt", licenses / "build-extra-LICENSE.txt")
        shutil.copyfile(sources / "git-full/COPYING", licenses / "git-COPYING")
        verify_support(support, compiler, prefix, env)
        if (inventory(native_root) != native_files or any(digest(path) != value for path, value in tools.items())
                or any(digest(row["path"]) != row["sha256"] for row in inputs.values())):
            raise ContractError("Native build inputs changed")
        report["files"] = inventory(output / "stage")
        report["status"] = "built-not-run"
        report["pending"] = ["raw-native-PE", "native-process", "credential protocol", "prompt interaction",
                             "selector with actual native Git"]
    finally:
        (output / "build-evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Built four real helpers using native Windows GCC, make, Bash and coreutils")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=0, help="Coordinator-approved compile-job budget")
    parser.add_argument("--check", action="store_true", help="Check prerequisites; never compile")
    parser.add_argument("--component", choices=("all", "wincred", "prompts"), default="all")
    parser.add_argument("--native-root", type=Path, help="Opt into native Windows make/Bash/coreutils orchestration")
    parser.add_argument("--pwsh", type=Path)
    parser.add_argument("--artifact-gate", type=Path)
    args = parser.parse_args()
    if args.native_root:
        if args.check or args.component != "all" or not args.pwsh or not args.artifact_gate:
            raise ContractError("Native Windows mode builds all four helpers and requires native input PE gates")
        build_windows(args.sources, args.prefix, args.native_root, args.output, args.jobs,
                      args.pwsh, args.artifact_gate)
    else:
        build(args.sources, args.prefix, args.output, args.jobs, args.check, args.component)


if __name__ == "__main__":
    main()
