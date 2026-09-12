#!/usr/bin/env python3
"""Exercise normal shared GCC links, cross-DLL C++ EH and exact native module closure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import time

RECIPE = Path(__file__).resolve().parent


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if identity(args.runner)["sha256"] != args.runner_sha256:
        parser.error("Bounded process runner differs")
    root = args.root.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    sdk = root / "sdk"
    cc, cxx = sdk / "bin" / "gcc.exe", sdk / "bin" / "g++.exe"
    run_bounded = runpy.run_path(str(args.runner))["run"]
    native = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    modules = runpy.run_path(str(RECIPE / "native-loaded-modules.py"))["modules"]
    noninteractive = runpy.run_path(str(RECIPE / "run-msys-library-stage.py"))["noninteractive"]
    required = ["msys-2.0.dll", "msys-gcc_s-seh-1.dll", "msys-stdc++-6.dll",
                "msys-gomp-1.dll", "msys-atomic-1.dll"]
    inputs = []
    for name in required:
        source = sdk / "bin" / name
        inputs.append(identity(source))
        shutil.copy2(source, out / name)
    for name in ("shared-gcc-provider.cc", "shared-gcc-consumer.cc", "shared-gcc-c.c"):
        source = RECIPE / "probes" / name
        inputs.append(identity(source))
        shutil.copy2(source, out / name)
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")}
    env.update(PATH=str(out) + os.pathsep + str(sdk / "bin") + os.pathsep
               + str(Path(os.environ["SystemRoot"]) / "System32"), LC_ALL="C.UTF-8")
    report = {"schema": 1, "status": "failed", "inputs": inputs, "runs": [], "loaded_modules": {}}

    def run(name, command, *, expected=0, execute=False, marker=None):
        log = out / f"{name}.bin"
        observed = []

        def started(pid):
            observed.append(native(pid, Path(command[0])))
            if marker:
                deadline = time.monotonic() + 15
                while marker not in log.read_bytes():
                    if time.monotonic() >= deadline:
                        raise ValueError(f"Missing success marker from owned process {name}")
                    time.sleep(0.02)
                report["loaded_modules"][name] = modules(pid)

        with log.open("wb") as stream, noninteractive():
            result = run_bounded(list(map(str, command)), cwd=out, env=env, log=stream,
                                 timeout=45 if execute else 180, on_started=started if execute else None)
        report["runs"].append({"name": name, "command": list(map(str, command)), "process": result,
                               "native": observed, "log": identity(log)})
        if result["exit"] != expected or result["timed_out"] or result["active_at_boundary"]:
            raise ValueError(f"Command or native-child drain failed: {name}: {result}")
        return log.read_bytes()

    def pe(name, path):
        shell = shutil.which("pwsh")
        if not shell:
            raise ValueError("PowerShell 7 is required for raw PE parsing")
        quote = lambda p: "'" + str(p).replace("'", "''") + "'"
        code = ("$ErrorActionPreference='Stop'; . " + quote(RECIPE / "Get-ToolchainPeIdentity.ps1")
                + "; Get-ToolchainPeIdentity -Path " + quote(path) + " | ConvertTo-Json -Depth 9")
        return json.loads(run(name, [shell, "-NoProfile", "-Command", code]).decode("utf-8-sig"))

    try:
        for name, compiler in (("C", cc), ("CXX", cxx)):
            if run(name + "-target", [compiler, "-dumpmachine"]).strip() != b"aarch64-pc-cygwin":
                raise ValueError("Target is not MSYS")
        for filename in ("crt0.o", "libmsys-2.0.a", "libgcc_s.dll.a", "libstdc++.dll.a"):
            selected = Path(run("select-" + filename, [cxx, "-print-file-name=" + filename]).decode().strip())
            if not selected.resolve(strict=True).is_relative_to(sdk):
                raise ValueError("Normal linker input escaped the private SDK")
            inputs.append(identity(selected))
        run("provider-build", [cxx, "-std=c++17", "-O2", "-g", "-Wall", "-Werror", "-pthread", "-fstack-protector-strong",
                               "-shared", out / "shared-gcc-provider.cc",
                               "-Wl,--out-implib," + str(out / "provider.dll.a"), "-o", out / "provider.dll"])
        run("cpp-normal-link", [cxx, "-std=c++17", "-O2", "-g", "-Wall", "-Werror", "-pthread", "-fstack-protector-strong",
                                out / "shared-gcc-consumer.cc", out / "provider.dll.a",
                                "-o", out / "consumer.exe"])
        run("c-normal-link", [cc, "-std=gnu11", "-O2", "-g", "-Wall", "-Werror", "-fopenmp", "-fstack-protector-strong",
                              out / "shared-gcc-c.c", "-latomic", "-o", out / "consumer-c.exe"])
        report["pe"] = {}
        for name in ("provider.dll", "consumer.exe", "consumer-c.exe") + tuple(required[1:]):
            image = pe("pe-" + name, out / name)
            dlls = {entry["Dll"].lower() for entry in image["Imports"]}
            if not image["NativeArm64"] or not image["DynamicBase"] or "msys-2.0.dll" not in dlls:
                raise ValueError(f"Not a native MSYS image: {name}")
            if any(name in dlls for name in ("msvcrt.dll", "ucrtbase.dll", "cygwin1.dll")):
                raise ValueError("Wrong target C runtime")
            report["pe"][name] = image
        provider_imports = {item["Dll"].lower() for item in report["pe"]["provider.dll"]["Imports"]}
        if not {"msys-stdc++-6.dll", "msys-gcc_s-seh-1.dll"}.issubset(provider_imports):
            raise ValueError("Cross-DLL C++ fixture did not dynamically link both GCC runtimes")
        c_imports = {item["Dll"].lower() for item in report["pe"]["consumer-c.exe"]["Imports"]}
        if not {"msys-gcc_s-seh-1.dll", "msys-gomp-1.dll", "msys-atomic-1.dll"}.issubset(c_imports):
            raise ValueError("C probe did not dynamically use GCC arithmetic/OpenMP/atomic runtime")
        cpp_marker = b"native-msys-shared-gcc-cpp-ok"
        c_marker = b"native-msys-shared-gcc-c-ok"
        cpp_output = run("cpp-shared-runtime", [out / "consumer.exe", "--hold"], execute=True, marker=cpp_marker)
        c_output = run("c-shared-runtime", [out / "consumer-c.exe", "--hold"], execute=True, marker=c_marker)
        if cpp_output.replace(b"\r\n", b"\n") != cpp_marker + b"\n" or c_output.replace(b"\r\n", b"\n") != c_marker + b"\n":
            raise ValueError("Unexpected runtime probe output")
        for name, expected in (("cpp-shared-runtime", required[:3]), ("c-shared-runtime", required[:2] + required[3:])):
            loaded = {Path(item["path"]).name.lower(): item for item in report["loaded_modules"][name]}
            for filename in expected:
                if filename not in loaded or Path(loaded[filename]["path"]).resolve() != (out / filename).resolve():
                    raise ValueError(f"Incorrect loaded runtime path: {filename}")
                if loaded[filename]["sha256"] != identity(out / filename)["sha256"]:
                    raise ValueError("Loaded runtime bytes differ from the staged provider")
        if any(identity(item["path"]) != item for item in inputs):
            raise ValueError("Input changed during shared runtime qualification")
        report.update(status="native-msys-shared-gcc-runtimes-qualified",
                      nativeProcess=True, hostArchitecture="arm64", targetTriple="aarch64-pc-cygwin",
                      normal_link=True, cross_dll_cpp_exception=True, threads_tls_locale=True,
                      exact_loaded_dll_closure=True,
                      scope="Ordinary native shared-runtime C/C++ qualification; not debugger parity or all upstream package tests")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(out / "result.json")


if __name__ == "__main__":
    main()
