#!/usr/bin/env python3
"""Build a four-archive Windows API overlay without modifying its MSYS SDK."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import struct

RECIPE = Path(__file__).resolve().parent


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def contained(root, relative):
    relative = PurePosixPath(relative.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
        raise ValueError(f"Unsafe inventory path: {relative}")
    result = root.joinpath(*relative.parts).resolve(strict=True)
    if not result.is_relative_to(root):
        raise ValueError(f"Inventory escapes root: {relative}")
    return result


def archive_identity(path, dll):
    """Read every standard COFF member, not objdump's ARM64 machine decoder."""
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("Not a regular archive")
    offset, members, descriptors = 8, [], []
    allowed = {".text", ".data", ".bss", ".idata$2", ".idata$3", ".idata$4",
               ".idata$5", ".idata$6", ".idata$7"}
    while offset < len(data):
        header = data[offset:offset + 60]
        if len(header) != 60 or header[58:] != b"`\n":
            raise ValueError("Invalid archive member")
        name = header[:16].decode("ascii").strip()
        size = int(header[48:58])
        body = data[offset + 60:offset + 60 + size]
        if len(body) != size:
            raise ValueError("Truncated archive")
        offset += 60 + size + (size & 1)
        if name in ("/", "//"):
            continue
        if len(body) < 20:
            raise ValueError("Truncated COFF header")
        machine, count = struct.unpack_from("<HH", body)
        optional = struct.unpack_from("<H", body, 16)[0]
        if machine != 0xaa64 or optional or not 1 <= count <= 12:
            raise ValueError(f"Not an ordinary ARM64 COFF import member: {name}")
        sections = {}
        for index in range(count):
            start = 20 + 40 * index
            record = body[start:start + 40]
            if len(record) != 40:
                raise ValueError("Truncated section table")
            section = record[:8].rstrip(b"\0").decode("ascii")
            length, raw = struct.unpack_from("<II", record, 16)
            if section not in allowed or section in sections or raw + length > len(body):
                raise ValueError(f"Unexpected import section: {section}")
            if section in (".data", ".bss") and length:
                raise ValueError("Archive contains non-import data")
            if section == ".text" and length > 16:
                raise ValueError("Archive contains code larger than an import thunk")
            sections[section] = length
            if section == ".idata$7" and length:
                value = body[raw:raw + length].rstrip(b"\0")
                if value.lower().endswith(b".dll"):
                    descriptors.append(value.decode("ascii"))
        members.append({"name": name, "machine": "0xAA64", "sections": sections})
    if offset != len(data) or not members or [s.lower() for s in descriptors] != [dll.lower()]:
        raise ValueError(f"Wrong import DLL descriptor: {descriptors}")
    return {"sha256": identity(path)["sha256"], "members": members, "dll_descriptors": descriptors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-receipt", required=True, type=Path)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--source-root", required=True, type=Path,
                        help="Read-only export of the pinned w32api definition blobs")
    parser.add_argument("--process-runner", required=True, type=Path)
    parser.add_argument("--process-runner-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Use the native Windows-hosted compiler tools")
    if identity(args.compiler_receipt)["sha256"] != args.receipt_sha256:
        parser.error("Compiler receipt differs")
    if identity(args.process_runner)["sha256"] != args.process_runner_sha256:
        parser.error("Bounded process runner differs")
    base = json.loads(args.compiler_receipt.read_text(encoding="utf-8-sig"))
    if (base["schema"] != 1 or base["status"] != "byte-identical-relocated-input-not-new-qualification"
            or base["source_target"]["Triple"] != "aarch64-pc-cygwin"
            or base["source_target"]["Profile"] != "MSYS"
            or base["source_target"]["DataModel"] != "LP64"):
        parser.error("Expected the declared native MSYS compiler-copy receipt")
    prefix = Path(base["prefix"]).resolve(strict=True)
    if args.output.resolve().is_relative_to(prefix):
        parser.error("Never write into the immutable compiler prefix")
    lock = runpy.run_path(str(RECIPE / "source-lock.py"))["load_lock"](RECIPE)
    contract = json.loads((RECIPE / "windows-system-imports.json").read_text())
    if (contract["schema"] != 1 or contract["source"] != "mingw-w64" or
            contract["revision"] != lock["sources"]["mingw-w64"]["revision"] or
            set(contract["definitions"]) != {"wsock32", "bcrypt", "setupapi", "hid"}):
        parser.error("Import definitions and source lock disagree")
    source_root = args.source_root.resolve(strict=True)
    definitions = {}
    for name, spec in contract["definitions"].items():
        source = contained(source_root, spec["path"])
        if identity(source)["sha256"] != spec["sha256"]:
            parser.error(f"Pinned definition differs: {name}")
        lines = [line.strip() for line in source.read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith(";")]
        if lines[:2] != [f'LIBRARY "{spec["dll"]}"', "EXPORTS"] and lines[:2] != [
                f'LIBRARY {spec["dll"]}', "EXPORTS"]:
            parser.error(f"Unexpected DLL in definition: {name}")
        if spec["probe"] not in lines[2:] or any(not re.fullmatch(r"\w+", s) for s in lines[2:]):
            parser.error(f"Expected undecorated ARM64 function imports: {name}")
        definitions[name] = (source, lines[2:])

    def verify_base():
        for relative, expected in base["files"].items():
            path = contained(prefix, relative)
            if identity(path)["sha256"] != expected["sha256"] or path.stat().st_size != expected["size"]:
                raise ValueError(f"Compiler input differs: {relative}")
        actual = {p.relative_to(prefix).as_posix() for p in prefix.rglob("*") if p.is_file()}
        if actual != set(base["files"]):
            raise ValueError("Compiler inventory file set differs")
        for name in definitions:
            if (prefix / "aarch64-pc-cygwin" / "lib" / f"lib{name}.a").exists():
                raise ValueError(f"This additive overlay would replace {name}")

    verify_base()
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    for name in ("sources", "logs", "payload", "work", "probes"):
        (out / name).mkdir()
    lib = out / "payload" / "aarch64-pc-cygwin" / "lib"
    lib.mkdir(parents=True)
    shutil.copy2(args.process_runner, out / "sources" / "bounded_process.py")
    shutil.copy2(args.compiler_receipt, out / "sources" / "baseline-copy-receipt.json")
    shutil.copy2(RECIPE / "windows-system-imports.json", out / "sources")
    run_bounded = runpy.run_path(str(out / "sources" / "bounded_process.py"))["run"]
    native_process = runpy.run_path(str(RECIPE / "test-msys-ucontext.py"))["native_process"]
    env = {key: value for key, value in os.environ.items()
           if key.upper() in ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT")}
    env["PATH"] = str(prefix / "bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")
    env["SOURCE_DATE_EPOCH"] = "0"
    cc = prefix / "bin" / "gcc.exe"
    dlltool = prefix / "bin" / "dlltool.exe"
    assembler = prefix / "aarch64-pc-cygwin" / "bin" / "as.exe"
    report = {"schema": 1, "status": "failed", "compiler_receipt": identity(args.compiler_receipt),
              "base_prefix": str(prefix), "target": base["source_target"], "runs": [], "archives": {},
              "source_revision": contract["revision"],
              "source_repository": lock["sources"]["mingw-w64"]["repository"],
              "source_contract": identity(RECIPE / "windows-system-imports.json")}

    def run(name, command, cwd, *, expect=0, machine=False):
        measurements = []
        log = out / "logs" / (name + ".bin")
        with log.open("wb") as stream:
            result = run_bounded(
                list(map(str, command)), cwd=cwd, env=env, log=stream, timeout=120,
                on_started=(lambda pid: measurements.append(native_process(pid, Path(command[0]))))
                if machine else None)
        report["runs"].append({"name": name, "command": list(map(str, command)), "cwd": str(cwd),
                               "process": result, "native_processes": measurements, "log": identity(log)})
        if result["timed_out"] or result["active_at_boundary"] or result["remaining_process_ids"] or result["exit"] != expect:
            raise ValueError(f"Unexpected command or child-drain result: {name}: {result}")
        return log.read_bytes()

    def pe(name, path):
        shell = shutil.which("pwsh")
        if not shell:
            raise ValueError("Existing PowerShell 7 is required for the raw PE parser")
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        code = ("$ErrorActionPreference='Stop'; . " + quote(RECIPE / "Get-ToolchainPeIdentity.ps1")
                + "; Get-ToolchainPeIdentity -Path " + quote(path) + " | ConvertTo-Json -Depth 8")
        result = json.loads(run(name, [shell, "-NoProfile", "-Command", code], out).decode("utf-8-sig"))
        if not result["NativeArm64"] or not result["DynamicBase"]:
            raise ValueError("Expected an ASLR ARM64 PE image")
        return result

    try:
        if run("target", [cc, "-dumpmachine"], out).strip() != b"aarch64-pc-cygwin":
            raise ValueError("Wrong target compiler")
        report["tools"] = [identity(tool) for tool in (cc, dlltool, assembler)]
        for name, (source, exports) in definitions.items():
            spec = contract["definitions"][name]
            definition = out / "sources" / (name + ".def")
            shutil.copy2(source, definition)
            generated = []
            for attempt in (1, 2):
                work = out / "work" / f"{name}-{attempt}"
                work.mkdir()
                filename = f"lib{name}.a"
                run(f"{name}-generate-{attempt}", [
                    dlltool, "-m", "arm64", "-k", "--deterministic-libraries",
                    "--as", assembler, "--temp-prefix", f"import_{name}_",
                    "--input-def", definition, "--output-lib", filename], work, machine=True)
                archive = work / filename
                info = archive_identity(archive, spec["dll"])
                symbols = run(f"{name}-symbols-{attempt}", [
                    prefix / "bin" / "nm.exe", "--defined-only", archive], work).decode()
                defined = {line.split()[-1] for line in symbols.splitlines() if len(line.split()) >= 3}
                if {s for s in defined if s.startswith("__imp_")} != {"__imp_" + s for s in exports}:
                    raise ValueError(f"Definition/import-symbol coverage differs: {name}")
                generated.append(info)
            if generated[0]["sha256"] != generated[1]["sha256"]:
                raise ValueError(f"Import archive is not reproducible: {name}")
            shutil.copy2(out / "work" / f"{name}-1" / f"lib{name}.a", lib)
            report["archives"][name] = {
                "definition": identity(definition), "export_count": len(exports),
                "reproducible": True, **generated[0]}
        probes = out / "probes"
        # References make real IAT entries but do not invoke network, device,
        # cryptographic or authentication APIs. These fixtures are never run.
        references = probes / "windows-imports.s"
        references.write_text(".data\n.p2align 3\n.global windows_import_addresses\nwindows_import_addresses:\n"
                              + "".join(f" .quad __imp_{spec['probe']}\n"
                                        for spec in contract["definitions"].values()), encoding="ascii")
        obj = probes / "windows-imports.o"
        run("assemble-references", [assembler, references, "-o", obj], probes)
        source = probes / "windows-imports.c"
        source.write_text(
            "#if !defined(__MSYS__) || !defined(__aarch64__)\n#error Wrong target\n#endif\n"
            "typedef char lp64[(sizeof(void *) == 8 && sizeof(long) == 8) ? 1 : -1];\n"
            "int main(void) { return 0; }\n", encoding="ascii")
        libraries = [f"-l{name}" for name in definitions]
        negative = run("baseline-missing-imports", [cc, "-O2", source, obj, *libraries,
                                                   "-o", probes / "negative.exe"], probes, expect=1)
        if any(f"cannot find -l{name}".encode() not in negative for name in definitions):
            raise ValueError("The four original missing-library failures were not reproduced")
        executable = probes / "windows-imports.exe"
        run("normal-msys-link", [cc, "-O2", "-Wall", "-Wextra", "-Werror", source, obj,
                                "-L" + str(lib), *libraries, "-Wl,--no-insert-timestamp",
                                "-o", executable], probes, machine=True)
        image = pe("normal-msys-pe", executable)
        imports = {item["Dll"].lower(): item["Symbols"] for item in image["Imports"]}
        for spec in contract["definitions"].values():
            if spec["probe"] not in imports.get(spec["dll"].lower(), []):
                raise ValueError(f"Wrong linked Windows DLL/symbol: {spec['dll']}")
        if "msys-2.0.dll" not in imports or any(
                name in imports for name in ("cygwin1.dll", "msvcrt.dll", "ucrtbase.dll")):
            raise ValueError("MSYS runtime pairing was lost")
        report["link_probe"] = image
        report["payload"] = {
            p.relative_to(out / "payload").as_posix(): {"sha256": identity(p)["sha256"], "size": p.stat().st_size}
            for p in sorted(lib.glob("*.a"))}
        if len(report["payload"]) != 4:
            raise ValueError("Unexpected overlay file set")
        verify_base()
        report["baseline_inventory_unchanged"] = True
        report["status"] = "qualified-msys-windows-import-overlay-link-only"
        report["scope"] = (
            "Four additive Windows system import archives only; no CRT/header/runtime/compiler replacements. "
            "Native tool generation and ordinary MSYS link qualified, probe never executed; "
            "no Windows API/device/auth operation, FIDO package, runtime or C++ qualification.")
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Windows import overlay ready: {out / 'result.json'}")


if __name__ == "__main__":
    main()
