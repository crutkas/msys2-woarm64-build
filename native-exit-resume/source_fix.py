"""Qualify a private single-member source delta, not a producer library rebuild."""

import argparse
import json
import os
from pathlib import Path
import sys

from resume import ROOT, copy_locked, digest, free_memory, load, verify_inputs, write
from build_scratch import TC
from bounded_process import run
from native_job_runner import noninteractive_error_mode

PRODUCER = Path(r"C:\agtc-libs-01")
BUILD = ROOT / "source-build"
SOURCE_SHA = "1980a757de9b1798fd659d6bda39906c7e10c7513d9dec0ecc6094c2a8ab5ef4"


def prepare():
    verify_inputs()
    BUILD.mkdir(exist_ok=False)
    dependency = PRODUCER / "build/aarch64-pc-cygwin/libgcc/unwind-seh.dep"
    copies = [copy_locked(dependency, BUILD / "input.dep", digest(dependency))]
    rule = dependency.read_text().replace("\\\n", " ").splitlines()[0]
    if not rule.startswith("unwind-seh.o: "):
        raise RuntimeError("Unexpected generated dependency rule")
    paths = set()
    for name in rule.split(": ", 1)[1].split():
        path = Path(name)
        if not path.is_absolute():
            path = dependency.parent / path
        path = path.resolve(strict=True)
        if not path.is_relative_to(PRODUCER):
            raise RuntimeError(f"Dependency is outside authorized producer root: {path}")
        paths.add(path)
    for path in sorted(paths):
        copies.append(copy_locked(path, BUILD / "closure" / path.relative_to(PRODUCER), digest(path)))
    source = BUILD / "closure/source/libgcc/unwind-seh.c"
    if digest(source) != SOURCE_SHA:
        raise RuntimeError("Retained unwind source differs from exact diagnosis")
    copies.append(copy_locked(source, BUILD / "patched/libgcc/unwind-seh.c", SOURCE_SHA))
    for name, runtime in (("source-control", ROOT / "baseline/usr/bin/msys-2.0.dll"),
                          ("source-fixed", ROOT / "baseline/usr/bin/msys-2.0.dll"),
                          ("source-fixed-d70", ROOT / "d70/usr/bin/msys-2.0.dll")):
        for path, rel in ((runtime, Path("usr/bin/msys-2.0.dll")),
                          (ROOT / "baseline/etc/fstab", Path("etc/fstab"))):
            copies.append(copy_locked(path, ROOT / name / rel, digest(path)))
    write(BUILD / "prepared.json", {"schema": 1, "copies": copies,
          "source_sha256": SOURCE_SHA, "source": str(source),
          "patched": str(BUILD / "patched/libgcc/unwind-seh.c"),
          "scope": "Copied new native generated-header closure; not reconstruction of historical Linux-hosted member"})
    print(json.dumps({"copied_dependencies": len(paths), "patched_source": str(BUILD / "patched/libgcc/unwind-seh.c")}))


def build():
    verify_inputs()
    prepared = load(BUILD / "prepared.json")
    patched = Path(prepared["patched"])
    for row in prepared["copies"]:
        if digest(row["source"]) != row["before"] or (row["copy"] != str(patched) and digest(row["copy"]) != row["copied"]):
            raise RuntimeError(f"Copied closure changed: {row['source']}")
    expected = load(ROOT / "scratch-build/result.json")["tool_inputs_before_after"]
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Compiler changed: {path}")
    closure = BUILD / "closure"
    includes = [
        closure / "build/aarch64-pc-cygwin/libgcc", closure / "build/gcc",
        closure / "source/libgcc", closure / "source/gcc", closure / "source/include",
        closure / "source/libgcc/config/libbid",
    ]
    system_includes = [
        closure / "sdk/lib/gcc/aarch64-pc-cygwin/15.0.1/include",
        closure / "sdk/aarch64-pc-cygwin/include", closure / "sdk/aarch64-pc-cygwin/include/w32api",
    ]
    flags = ["-g", "-O2", "-DIN_GCC", "-DCROSS_DIRECTORY_STRUCTURE", "-W", "-Wall",
             "-Wno-error=narrowing", "-Wwrite-strings", "-Wcast-qual", "-Wstrict-prototypes",
             "-Wmissing-prototypes", "-Wold-style-definition", "-DIN_LIBGCC2", "-fbuilding-libgcc",
             "-fno-stack-protector", "-Werror", "-Wno-prio-ctor-dtor", "-Wno-error=attributes",
             "-Wno-error=unused-parameter", "-Wno-error=missing-prototypes", "-Wno-error=unused-function",
             "-DENABLE_DECIMAL_BID_FORMAT", "-DHAVE_CC_TLS", "-DUSE_EMUTLS", "-fexceptions", "-nostdinc"]
    for path in includes:
        flags.extend(["-I", str(path)])
    for path in system_includes:
        flags.extend(["-isystem", str(path)])
    commands = []
    for name, source in (("source-control", Path(prepared["source"])), ("source-fixed", patched)):
        obj = BUILD / f"{name}.o"
        commands.append((name + "-object", [str(TC / "bin/gcc.exe"), *flags, "-c", str(source), "-o", str(obj)]))
        for fixture, object_path in (("exception-fixture", ROOT / "scratch-build/fixture.o"),
                                     ("unwind-matrix", ROOT / "matrix-build/matrix.o")):
            argv = [str(TC / "bin/g++.exe"), "-static-libgcc", "-static-libstdc++",
                    str(object_path), str(obj), f"-Wl,-Map,{BUILD / (name + '-' + fixture + '.map')}",
                    "-o", str(ROOT / name / "usr/bin" / f"{fixture}.exe")]
            commands.append((name + "-" + fixture, argv))
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env.update({"PATH": os.pathsep.join([str(TC / "bin"), str(Path(env["SystemRoot"]) / "System32")]),
                "TMP": str(BUILD), "TEMP": str(BUILD), "HOME": str(BUILD), "USERPROFILE": str(BUILD)})
    records = []
    for name, argv in commands:
        memory = free_memory()
        with noninteractive_error_mode(), (BUILD / f"{name}.log").open("xb") as log:
            result = run(argv, cwd=BUILD, env=env, log=log, timeout=120)
        record = {"command": argv, "result": result, "free_before": memory, "free_after": free_memory()}
        records.append(record)
        write(BUILD / f"{name}.json", record)
        if not result["passed"]:
            raise RuntimeError(f"Single-member experiment failed: {name}")
    copies = []
    for name in ("exception-fixture.exe", "unwind-matrix.exe"):
        path = ROOT / "source-fixed/usr/bin" / name
        copies.append(copy_locked(path, ROOT / "source-fixed-d70/usr/bin" / name, digest(path)))
    for path in BUILD.glob("*.map"):
        text = path.read_text()
        if "libgcc.a(unwind-seh.o)" in text or "_GCC_specific_handler" not in text:
            raise RuntimeError("Link map does not confirm private single-member override")
    for path, sha in expected.items():
        if digest(path) != sha:
            raise RuntimeError(f"Compiler changed after source experiment: {path}")
    outputs = {str(ROOT / cohort / "usr/bin" / name): digest(ROOT / cohort / "usr/bin" / name)
               for cohort in ("source-control", "source-fixed", "source-fixed-d70")
               for name in ("exception-fixture.exe", "unwind-matrix.exe")}
    write(BUILD / "result.json", {"schema": 1, "builds": records, "outputs": outputs, "copies": copies,
          "source_before_sha256": SOURCE_SHA, "source_after_sha256": digest(patched),
          "control_object_sha256": digest(BUILD / "source-control.o"),
          "fixed_object_sha256": digest(BUILD / "source-fixed.o"),
          "link_maps": {str(path): digest(path) for path in BUILD.glob("*.map")},
          "new_native_single_member_experiment": True, "historical_member_reconstructed": False,
          "producer_sdk_libraries_modified": False, "producer_admission": False})
    print(json.dumps({"outputs": outputs, "source_after": digest(patched)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "build"))
    args = parser.parse_args()
    (prepare if args.action == "prepare" else build)()
