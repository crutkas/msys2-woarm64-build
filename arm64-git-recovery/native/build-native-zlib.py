"""Build the pinned static zlib baseline with native Windows ARM64 GNU tools."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys

from compiler_tools import support_identities, verify_support
from sources import ContractError, digest, inventory, verify_tree


def recipe_objects(source):
    recipe = (source / "win32/Makefile.gcc").read_text()
    logical = recipe.replace("\\\n", " ")
    match = re.search(r"(?m)^OBJS\s*=\s*(.+)$", logical)
    if not match or not re.search(r"(?m)^OBJA\s*=\s*$", logical):
        raise ContractError("Unexpected zlib object recipe; review the pinned build instructions")
    names = match.group(1).split()
    if (not names or len(names) != len(set(names))
            or any(not re.fullmatch(r"[a-z0-9]+\.o", name) for name in names)):
        raise ContractError("Invalid or duplicate upstream object names")
    for name in names:
        if not (source / (name[:-2] + ".c")).is_file():
            raise ContractError(f"Missing upstream C source: {name}")
    if not re.search(r"(?m)^CFLAGS = \$\(LOC\) -O3 -Wall$", recipe):
        raise ContractError("Upstream compiler flags changed")
    if not re.search(r"(?m)^ARFLAGS = rcs$", recipe):
        raise ContractError("Upstream archive flags changed")
    return names


def verify_archive(path, objects):
    data = Path(path).read_bytes()
    if data[:8] != b"!<arch>\n":
        raise ContractError("Missing GNU archive header")
    found, offset = {}, 8
    while offset < len(data):
        if offset + 60 > len(data) or data[offset + 58:offset + 60] != b"`\n":
            raise ContractError("Malformed archive member header")
        name = data[offset:offset + 16].decode("ascii").strip()
        size = int(data[offset + 48:offset + 58])
        start, end = offset + 60, offset + 60 + size
        if size < 0 or end > len(data):
            raise ContractError("Archive member extends beyond the archive")
        if name not in ("/", "//", "/SYM64/"):
            name = name.removesuffix("/")
            if name not in objects or name in found:
                raise ContractError(f"Unexpected or duplicate archive member: {name}")
            member = data[start:end]
            if (len(member) < 20 or struct.unpack_from("<H", member)[0] != 0xaa64
                    or not 0 < struct.unpack_from("<H", member, 2)[0] <= 96):
                raise ContractError(f"Archive member is not an ARM64 COFF object: {name}")
            value = hashlib.sha256(member).hexdigest()
            if value != digest(objects[name]):
                raise ContractError(f"Archive member differs from its compiled object: {name}")
            found[name] = value
        offset = end + size % 2
    if set(found) != set(objects):
        raise ContractError("Incomplete static archive")
    return found


def build(source, manifest, prefix, tool_identities, output, jobs, pwsh, artifact_gate, process_gate,
          toolchain_proof=None):
    if os.name != "nt" or platform.machine().lower() not in ("arm64", "aarch64"):
        raise ContractError("This recipe requires native Windows ARM64 orchestration")
    if jobs != 1:
        raise ContractError("An explicitly allocated single job is required")
    source, manifest, prefix, output = (Path(p).resolve() for p in (source, manifest, prefix, output))
    if output.exists():
        raise ContractError("Use a new build directory")
    verify_tree(source, manifest)
    locked = json.loads(manifest.read_text())["source"]
    if locked["id"] != "zlib-historical" or locked["version"] != "1.3.1":
        raise ContractError("This is specifically the recovered zlib 1.3.1 baseline")
    names = recipe_objects(source)
    env = dict(os.environ)
    for name in list(env):
        if (name.startswith(("GCC_", "MSYS", "MINGW")) or name in
                ("COMPILER_PATH", "LIBRARY_PATH", "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH")):
            del env[name]
    env["PATH"] = str(prefix / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    compiler, archiver = prefix / "bin/gcc.exe", prefix / "bin/ar.exe"
    output.mkdir(parents=True)
    env["TMP"] = env["TEMP"] = str(output / "temp")
    (output / "temp").mkdir()
    commands, result = [], {
        "schema": 1, "status": "failed", "version": "1.3.1",
        "build_host": "windows-arm64-native", "target": "aarch64-w64-mingw32",
        "scope": "Historical static zlib baseline only; not final native Git/toolchain qualification",
        "pending": ["final-toolchain-admission-after-external-data-refptr-fix", "full-Git-integration"]
    }

    def run(name, command, stdin=None, expected=0):
        completed = subprocess.run([str(arg) for arg in command], input=stdin, cwd=output,
                                   env=env, capture_output=True, timeout=180)
        (output / f"{name}.stdout.bin").write_bytes(completed.stdout)
        (output / f"{name}.stderr.bin").write_bytes(completed.stderr)
        commands.append({
            "name": name, "argv": [str(arg) for arg in command], "exit_code": completed.returncode,
            "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest()
        })
        if completed.returncode != expected:
            raise ContractError(f"{name} exited {completed.returncode}; raw output retained in {output}")
        return completed.stdout

    def gate(name, script, arguments):
        report = output / f"{name}.json"
        run(name, [pwsh, "-NoProfile", "-File", script, *arguments, "-ReportPath", report])
        value = json.loads(report.read_text())
        if value.get("Passed") is not True:
            raise ContractError(f"Native gate did not pass: {name}")
        return value

    try:
        if run("target", [compiler, "-dumpmachine"]).strip() != b"aarch64-w64-mingw32":
            raise ContractError("Wrong native compiler target")
        support = support_identities(compiler, prefix, env)
        tools = {str(compiler): digest(compiler), str(archiver): digest(archiver),
                 **{entry["path"]: entry["sha256"] for entry in support.values()}}
        admitted = {str(Path(row["Path"]).resolve()).casefold(): row
                    for row in json.loads(Path(tool_identities).read_text())}
        for path, sha in tools.items():
            identity = admitted.get(path.casefold())
            if not identity or identity["SHA256"].lower() != sha or identity["Machine"] != "0xAA64":
                raise ContractError(f"Tool does not match the supplied native identity snapshot: {path}")
        libraries = {}
        for name in ("crt2.o", "libgcc.a", "libmingw32.a", "libmingwex.a", "libucrt.a",
                     "libkernel32.a"):
            value = run(f"resolve-{name}", [compiler, f"-print-file-name={name}"]).decode().strip()
            path = Path(value).resolve()
            if not Path(value).is_absolute() or not path.is_file() or not path.is_relative_to(prefix):
                raise ContractError(f"Unresolved native link input: {name}")
            libraries[name] = {"path": str(path), "sha256": digest(path)}
        result.update({
            "source_manifest_sha256": digest(manifest), "source_archive": locked,
            "upstream_recipe_sha256": digest(source / "win32/Makefile.gcc"),
            "tool_identity_snapshot_sha256": digest(tool_identities),
            "tools": tools, "support_tools": support, "link_inputs": libraries
        })
        if toolchain_proof:
            proof = json.loads(Path(toolchain_proof).read_text())
            if (proof.get("Passed") is not True or proof.get("Target") != "aarch64-w64-mingw32"
                    or Path(proof["CompilerProcess"]["Image"]).resolve() != compiler
                    or proof["CompilerProcess"].get("Machine") != "0xAA64"
                    or not proof.get("Runs") or any(row["ExitCode"] != 0 for row in proof["Runs"])):
                raise ContractError("Supplied toolchain proof does not qualify this native compiler")
            result["toolchain_proof"] = {"path": str(toolchain_proof), "sha256": digest(toolchain_proof)}
            result["pending"] = ["full-Git-integration"]
        gate("python-process", process_gate, ["-ProcessId", os.getpid()])
        held = subprocess.Popen([str(compiler), "-E", "-x", "c", "-"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=output, env=env)
        try:
            identity = gate("compiler-process", process_gate, ["-ProcessId", held.pid])
            if (identity["MeasuredCount"] != 1
                    or identity["Processes"][0]["ImagePath"].casefold() != str(compiler).casefold()):
                raise ContractError("Observed compiler image does not match the native driver")
            stdout, stderr = held.communicate(b"\n", timeout=30)
            if held.returncode != 0:
                raise ContractError("Observed compiler could not finish preprocessing")
        finally:
            if held.poll() is None:
                held.kill()
                held.communicate()
        copied = output / "source"
        shutil.copytree(source, copied)
        objects = {}
        for name in names:
            obj = output / name
            run(f"compile-{name}", [compiler, "-O3", "-Wall", "-I", copied, "-c",
                                   copied / (name[:-2] + ".c"), "-o", obj])
            objects[name] = obj
        archive = output / "libz.a"
        run("archive", [archiver, "rcs", archive, *objects.values()])
        result["archive_members"] = verify_archive(archive, objects)
        test_root = output / "tests"
        test_root.mkdir()
        for name in ("example", "minigzip"):
            obj = output / f"{name}.o"
            run(f"compile-{name}", [compiler, "-O3", "-Wall", "-I", copied, "-c",
                                   copied / f"test/{name}.c", "-o", obj])
            run(f"link-{name}", [compiler, "-o", test_root / f"{name}.exe", obj, archive])
        gate("test-artifacts", artifact_gate, ["-Root", test_root])
        example = run("upstream-example", [test_root / "example.exe"])
        if b"inflate with dictionary: hello, hello!" not in example:
            raise ContractError("Upstream example did not reach its final dictionary test")
        payload = bytes(range(256)) * 256 + b"native-arm64-zlib-baseline\n" * 4096
        compressed = run("gzip-compress", [test_root / "minigzip.exe"], payload)
        if gzip.decompress(compressed) != payload:
            raise ContractError("Independent Python decompressor rejected native minigzip output")
        reference = gzip.compress(payload, mtime=0)
        held = subprocess.Popen([str(test_root / "minigzip.exe"), "-d"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=output, env=env)
        try:
            gate("minigzip-process", process_gate, ["-ProcessId", held.pid])
            decompressed, stderr = held.communicate(reference, timeout=30)
            (output / "gzip-decompress.stdout.bin").write_bytes(decompressed)
            (output / "gzip-decompress.stderr.bin").write_bytes(stderr)
            if held.returncode != 0 or stderr or decompressed != payload:
                raise ContractError("Native decompressor did not reproduce independently compressed bytes")
        finally:
            if held.poll() is None:
                held.kill()
                held.communicate()
        verify_tree(source, manifest)
        verify_tree(copied, manifest)
        verify_support(support, compiler, prefix, env)
        for path, expected_sha in tools.items():
            if digest(path) != expected_sha:
                raise ContractError(f"Native tool changed during the build: {path}")
        for entry in libraries.values():
            if digest(entry["path"]) != entry["sha256"]:
                raise ContractError("Native CRT/library input changed during the build")
        stage = output / "stage"
        for rel, src in {
            "lib/libz.a": archive, "include/zlib.h": copied / "zlib.h",
            "include/zconf.h": copied / "zconf.h", "share/licenses/zlib/LICENSE": copied / "LICENSE"
        }.items():
            destination = stage / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, destination)
        result.update({
            "status": "native-windows-static-zlib-baseline-passed", "files": inventory(stage),
            "test_executables": inventory(test_root), "fixture_size": len(payload),
            "fixture_sha256": hashlib.sha256(payload).hexdigest(),
            "compressed_size": len(compressed), "independent_gzip_roundtrips": True
        })
    finally:
        result["commands"] = commands
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["status"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "manifest", "prefix", "tool-identities", "output",
                 "pwsh", "artifact-gate", "process-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--jobs", type=int, required=True)
    parser.add_argument("--toolchain-proof", type=Path)
    args = parser.parse_args()
    build(args.source, args.manifest, args.prefix, args.tool_identities, args.output,
          args.jobs, args.pwsh, args.artifact_gate, args.process_gate, args.toolchain_proof)


if __name__ == "__main__":
    main()
