"""Copy the admitted Bash package and historical native suite inputs for fresh 907 execution."""

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile

from sources import ContractError, digest, inventory, relative_path, verify_tree
from ssh_bootstrap import require_memory, write_json

terminal = importlib.import_module("prepare-combined-terminal")
ROOT = Path(r"C:\ag-bash907-20260911-02")
HERE = Path(__file__).resolve().parent
BASH_ROOT = Path(r"C:\ag-bash-e138-01\bash-full-immutable-18")
BASE_SUITE = Path(r"C:\ag-bash-e138-01\bash-full-immutable-18-suite-02")
PROVIDER = Path(r"C:\ap11-native-provider-intake\bash-qualified-d70-v1")
EXPORT_SHA = "f485f6e2b0ee76fe44fc1b416354367c1325d46a9d30efa39a884d7f472c747c"
BASH_SHA = "39ef42f62906be249b650dd9e0760109161c40c5b4e047093ef7e16b138c5d6a"
RUNTIME = Path(r"C:\Users\crutkasLocal\.copilot\session-state\67ba2e76-32e2-4f0d-a2fe-844ee8fe1d8a\files\combined-runtime-20260911\native-01\usr\bin\msys-2.0.dll")


def imports(data):
    pe = struct.unpack_from("<I", data, 60)[0]
    optional = pe + 24
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    sections = []
    for i in range(count):
        entry = optional + opt_size + i * 40
        _, rva, size, offset = struct.unpack_from("<IIII", data, entry + 8)
        sections.append((rva, size, offset))

    def offset(rva, length):
        matches = [raw + rva - start for start, size, raw in sections if start <= rva and rva + length <= start + size]
        if len(matches) != 1 or matches[0] + length > len(data):
            raise ContractError("PE import RVA outside file")
        return matches[0]

    rva, size = struct.unpack_from("<II", data, optional + 120)
    if not rva:
        return []
    start = offset(rva, min(size, 20))
    result = []
    while True:
        descriptor = struct.unpack_from("<IIIII", data, start)
        if not any(descriptor):
            break
        string = offset(descriptor[3], 1)
        end = data.find(b"\0", string)
        if end < string:
            raise ContractError("Unterminated PE import")
        result.append(data[string:end].decode("ascii"))
        start += 20
    return result


def main():
    resume = sys.argv[1:] == ["--resume-closure"]
    if sys.argv[1:] and not resume:
        raise ContractError("Unknown preparation argument")
    if ROOT.exists() and not resume:
        raise ContractError("Fresh Bash907 root required")
    terminal.sealed(PROVIDER / "export.json", EXPORT_SHA)
    contract_path = Path(r"C:\ap11-native-provider-intake\bash-runtime907-qualification-input-v1.json")
    terminal.sealed(contract_path, "4dc1ff625c82d762d25f157538146288758b7ffa2a150e09c6c4e8b28e137162")
    contract = json.loads(contract_path.read_text())
    terminal.sealed(Path(r"C:\ag-bash-e138-01\bash-provider-handoff-02\handoff.json"),
                    "f1aaeac6acb81efe8163cad3ea08a8f6432f7a77a9b1e2d0dae48b10efd8d58f")
    terminal.sealed(BASH_ROOT / "stage.inventory.json", "570915d5b63441d70ad6fc65acd186cace5c19b8ad428a07ed650968916c92f1")
    stage_manifest = json.loads((BASH_ROOT / "stage.inventory.json").read_text())
    actual_stage = inventory(BASH_ROOT / "stage")
    if actual_stage != {name: {key: row[key] for key in ("sha256", "size")}
                        for name, row in stage_manifest["files"].items()}:
        raise ContractError("Actual immutable Bash stage bytes differ")
    for name, row in stage_manifest["files"].items():
        if "machine" in row:
            if row["machine"].lower() != "0xaa64":
                raise ContractError("Non-native declared stage image")
            terminal.pe((BASH_ROOT / "stage" / name).read_bytes())
    terminal.sealed(BASE_SUITE / "qualification.json", "53c3267c22d75aa228b71b4b499960340f88af198af9ee0811a87365e636c268")
    terminal.sealed(RUNTIME, terminal.RUNTIME_SHA)
    terminal.sealed(terminal.HANDOFF, terminal.HANDOFF_SHA)
    require_memory()
    ROOT.mkdir(exist_ok=resume)
    (ROOT / "receipts").mkdir(exist_ok=resume)
    (ROOT / "packages").mkdir(exist_ok=resume)
    prior = inventory(BASE_SUITE / "runtime")
    for name in prior:
        if "symlink" in prior[name]:
            raise ContractError("Historical test driver links require explicit handling")
    if not resume:
        shutil.copytree(BASE_SUITE / "runtime", ROOT / "runtime")
    if (not resume and inventory(ROOT / "runtime") != prior) or inventory(BASE_SUITE / "runtime") != prior:
        raise ContractError("Historical native test driver changed during copy")
    shutil.copyfile(RUNTIME, ROOT / "runtime/usr/bin/msys-2.0.dll")
    package_row = next(row for row in json.loads((PROVIDER / "export.json").read_text())["packages"] if row["name"] == "bash")
    package = Path(package_row["path"])
    terminal.sealed(package, package_row["sha256"])
    shutil.copyfile(package, ROOT / "packages" / package.name)
    package_files, package_links = {}, []
    with tarfile.open(package) as archive:
        for member in archive.getmembers():
            name = member.name.removeprefix("./").rstrip("/")
            relative_path(name)
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                package_links.append({"path": name, "target": member.linkname})
                continue
            if not member.isfile():
                raise ContractError(f"Unsupported package member: {name}")
            data = archive.extractfile(member).read()
            package_files[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if name.startswith("."):
                (ROOT / "receipts" / name[1:]).write_bytes(data)
            else:
                target = ROOT / "runtime" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    for name in ("bash.exe", "sh.exe"):
        terminal.sealed(ROOT / "runtime/usr/bin" / name, BASH_SHA)
    for row in contract["subjectDependencies"]["files"]:
        source = Path(contract["subjectDependencies"]["sourceRoot"]) / row["path"]
        terminal.sealed(source, row["sha256"])
        if source.stat().st_size != row["bytes"]:
            raise ContractError("Subject dependency size differs")
        target = ROOT / "runtime/usr" / row["path"]
        shutil.copyfile(source, target)
        terminal.sealed(target, row["sha256"])
    shutil.copyfile(RUNTIME, ROOT / "runtime/usr/bin/msys-2.0.dll")
    terminal.sealed(ROOT / "runtime/usr/bin/msys-2.0.dll", terminal.RUNTIME_SHA)
    source_before = inventory(BASH_ROOT / "source")
    if any("symlink" in row for row in source_before.values()):
        raise ContractError("Build source snapshot contains a link; do not silently materialize it")
    if not resume:
        shutil.copytree(BASH_ROOT / "source", ROOT / "source")
    if inventory(ROOT / "source") != source_before or inventory(BASH_ROOT / "source") != source_before:
        raise ContractError("Frozen Bash source changed during adoption")
    if not resume:
        write_json(ROOT / "source.inventory.json", {"source": str(BASH_ROOT / "source"), "files": source_before})
    elif json.loads((ROOT / "source.inventory.json").read_text())["files"] != source_before:
        raise ContractError("Resumed source snapshot changed")
    for file in ("printenv.exe", "recho.exe", "xcase.exe", "zecho.exe"):
        source = BASH_ROOT / "source/tests" / file
        target = ROOT / "runtime/usr/bin" / file
        if digest(source) != digest(target):
            raise ContractError("Upstream support executable differs from actual build")
    terminfo = terminal.ROOT / "runtime-payload/usr/share/terminfo"
    if not resume:
        shutil.copytree(terminfo, ROOT / "runtime/usr/share/terminfo")
    elif inventory(terminfo) != inventory(ROOT / "runtime/usr/share/terminfo"):
        raise ContractError("Resumed terminfo differs")
    private = inventory(ROOT / "runtime")
    images = {}
    for name, row in private.items():
        path = ROOT / "runtime" / name
        with path.open("rb") as file:
            magic = file.read(2)
        if name.endswith((".exe", ".dll")) or magic == b"MZ":
            data = path.read_bytes()
            images[name] = {**row, **terminal.pe(data), "imports": imports(data)}
    dll_names = {Path(name).name.casefold() for name in images if name.startswith("usr/bin/")}
    system = Path(r"C:\Windows\System32")
    missing = []
    for name, row in images.items():
        for dll in row["imports"]:
            if dll.casefold() not in dll_names and not (system / dll).is_file() and not dll.lower().startswith(("api-ms-", "ext-ms-")):
                missing.append({"image": name, "dll": dll})
    if missing:
        raise ContractError(f"Unresolved private PE closure: {missing}")
    source_pe = {}
    for path in (ROOT / "source").rglob("*"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            magic = stream.read(2)
        if magic == b"MZ":
            name = path.relative_to(ROOT / "source").as_posix()
            source_pe[name] = {**terminal.pe(path.read_bytes()), "sha256": digest(path), "size": path.stat().st_size}
    for path in (PROVIDER / "export.json", PROVIDER / "handoff.json", BASH_ROOT / "stage.inventory.json",
                 BASE_SUITE / "qualification.json", Path(r"C:\ag-bash-e138-01\bash-provider-handoff-02\handoff.json"),
                 terminal.HANDOFF):
        target = ROOT / "receipts" / (path.parent.name + "-" + path.name)
        shutil.copyfile(path, target)
    # Observer and fixture compiler are already exact combined-input copies, never payload shims.
    observer = terminal.ROOT / "observer"
    shutil.copytree(observer, ROOT / "observer")
    shutil.copyfile(terminal.ROOT / "observer.manifest.json", ROOT / "observer.manifest.json")
    verify_tree(ROOT / "observer", ROOT / "observer.manifest.json")
    expected_cases = sorted(path.name for path in (ROOT / "source/tests").glob("run-*")
                            if path.name not in ("run-all", "run-minimal", "run-gprof")
                            and not path.name.endswith((".orig", "~")))
    inputs = {"schema": 1, "status": "AA64-only-private-Bash907-closure-ready-not-yet-qualified",
              "root": str(ROOT), "bash_sha256": BASH_SHA, "runtime_sha256": terminal.RUNTIME_SHA,
              "provider_qualification_contract": str(contract_path),
              "provider_qualification_contract_sha256": digest(contract_path),
              "subject_dependencies": contract["subjectDependencies"],
              "runtime_source": str(RUNTIME), "runtime_handoff_sha256": terminal.HANDOFF_SHA,
              "package": {"source": str(package), "copy": str(ROOT / "packages" / package.name),
                          "sha256": package_row["sha256"], "size": package.stat().st_size,
                          "files": package_files, "links": package_links},
              "historical_test_tool_inputs": {"root": str(BASE_SUITE / "runtime"), "files": prior,
                    "scope": "Exact previous86-case native test-only closure; not full Coreutils/other-provider admission"},
              "private_runtime_files": private, "pe_images": images,
              "source_snapshot_manifest": str(ROOT / "source.inventory.json"),
              "source_snapshot_manifest_sha256": digest(ROOT / "source.inventory.json"),
              "source_release_archive": next(row for row in json.loads((HERE / "sources.lock.json").read_text())["sources"] if row["id"] == "bash"),
              "source_pe_images": source_pe,
              "source_producer_handoff_sha256": "f1aaeac6acb81efe8163cad3ea08a8f6432f7a77a9b1e2d0dae48b10efd8d58f",
              "expected_upstream_cases": expected_cases, "cases": len(expected_cases),
              "old_runtime_qualification_not_rebound": True, "bash_or_libraries_rebuilt": False,
              "unresolved_imports": missing}
    write_json(ROOT / "inputs.json", inputs)
    print(json.dumps({"root": str(ROOT), "pe_images": len(images), "upstream_cases": len(expected_cases),
                      "inputs_sha256": digest(ROOT / "inputs.json")}), flush=True)


if __name__ == "__main__":
    main()
