"""Recover and exercise an explicitly emulated, standalone Doxygen bootstrap, without installation."""

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import tarfile
import zipfile

from bounded_process import run
from documentation_tools import verify_documentation
from sources import ContractError, digest, inventory, load_lock, recover

ZIP_FILES = {"doxygen.exe", "doxywizard.exe", "doxyindexer.exe", "doxysearch.cgi.exe", "libclang.dll"}


def validate_zip(entries):
    if len(entries) != len(ZIP_FILES) or {entry.filename for entry in entries} != ZIP_FILES:
        raise ContractError("Unexpected Doxygen bootstrap archive layout")
    for entry in entries:
        kind = stat.S_IFMT(entry.external_attr >> 16) if entry.create_system == 3 else 0
        if entry.is_dir() or entry.flag_bits & 1 or kind not in (0, stat.S_IFREG):
            raise ContractError("Unsupported Doxygen bootstrap archive member")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cache", "output", "pwsh", "artifact-gate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=Path(__file__).with_name("sources.lock.json"))
    args = parser.parse_args()
    output = args.output.resolve()
    probe = output.with_name(output.name + ".probe")
    manifest = output.with_name(output.name + ".manifest.json")
    if os.name != "nt" or any(path.exists() for path in (output, probe, manifest)):
        raise ContractError("Windows and fresh standalone driver/probe paths are required")
    locked = {row["id"]: row for row in load_lock(args.lock)["sources"]}
    binary, source = (locked[name] for name in ("doxygen-windows-x64-doc-bootstrap", "doxygen-source"))
    if binary["version"] != "1.18.0" or source["version"] != binary["version"]:
        raise ContractError("The documentation bootstrap requires its exact paired source release")
    for item in (binary, source):
        recover(item, args.cache)
    archive, source_archive = args.cache / binary["file"], args.cache / source["file"]
    output.mkdir(parents=True)
    probe.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        validate_zip(zipped.infolist())
        for entry in zipped.infolist():
            with zipped.open(entry) as src, (output / entry.filename).open("xb") as dest:
                shutil.copyfileobj(src, dest)
    with tarfile.open(source_archive) as tar:
        member = tar.getmember(source["prefix"] + "/LICENSE")
        if not member.isfile() or not 0 < member.size < 1024 * 1024:
            raise ContractError("Expected the actual bounded Doxygen source license")
        with tar.extractfile(member) as src, (output / "LICENSE").open("xb") as dest:
            shutil.copyfileobj(src, dest)
    before = inventory(output)
    for name in ("home", "temp"):
        (probe / name).mkdir()
    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC") if key in os.environ}
    env.update({"PATH": str(output) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"),
                "HOME": str(probe / "home"), "USERPROFILE": str(probe / "home"),
                "TMP": str(probe / "temp"), "TEMP": str(probe / "temp")})
    record = {"schema": 1, "status": "failed", "binary": binary, "source": source, "commands": [],
              "scope": "Standalone x64 emulated documentation bootstrap only; no installer, shared-prefix mutation, target compiler or distribution admission"}

    def command(name, argv):
        log = probe / f"{name}.log"
        with log.open("xb") as stream:
            process = run(argv, cwd=probe, env=env, log=stream, timeout=90)
        record["commands"].append({"name": name, "process": process, "log_sha256": digest(log)})
        return process, log

    try:
        gate_path = probe / "expected-nonnative-pe.json"
        process, _ = command("classify-x64", [args.pwsh, "-NoProfile", "-File", args.artifact_gate,
                                             "-Root", output, "-ReportPath", gate_path])
        gate = json.loads(gate_path.read_text())
        if (process["exit"] != 1 or process["timed_out"] or process["active_at_boundary"] or
                gate.get("Passed") is not False or gate.get("CandidateCount") != 5 or
                gate.get("ParsedCount") != 5 or any(row["Machine"] != "0x8664" for row in gate["Files"]) or
                any(not item.startswith("Non-native-ARM64 machine 0x8664:") for item in gate["Violations"])):
            raise ContractError("The documentation driver must be explicitly classified as x64, not native ARM64")
        record["architecture"] = "x86_64 emulated on Windows ARM64"
        process, version_log = command("version", [output / "doxygen.exe", "--version"])
        if not process["passed"] or version_log.read_text().strip().split()[0] != binary["version"]:
            raise ContractError("Doxygen version execution did not match the pinned release")
        fixture = Path(__file__).parent / "fixtures/documentation-probe.h"
        config = probe / "Doxyfile"
        config.write_text("\n".join([
            "PROJECT_NAME = DocumentationDriverControl",
            f'INPUT = "{fixture.resolve().as_posix()}"',
            f'OUTPUT_DIRECTORY = "{(probe / "generated").as_posix()}"',
            "GENERATE_HTML = YES", "GENERATE_XML = YES", "GENERATE_LATEX = NO",
            "NUM_PROC_THREADS = 1", "HAVE_DOT = NO", "QUIET = YES", "WARN_AS_ERROR = YES",
            "CLANG_ASSISTED_PARSING = NO", "EXTRACT_ALL = YES", ""]) , encoding="utf-8", newline="\n")
        process, _ = command("generate", [output / "doxygen.exe", config])
        if not process["passed"]:
            raise ContractError("The real documentation-generation control failed")
        record["documentation"] = verify_documentation(probe / "generated")
        if inventory(output) != before or digest(archive) != binary["sha256"] or digest(source_archive) != source["sha256"]:
            raise ContractError("Documentation bootstrap inputs changed")
        record.update({"status": "emulated-documentation-driver-qualified", "prefix": str(output),
                       "files": before, "fixture_sha256": digest(fixture),
                       "config_sha256": digest(config), "native_pe_rejection_sha256": digest(gate_path)})
    finally:
        with manifest.open("x", encoding="utf-8", newline="\n") as dest:
            json.dump(record, dest, indent=2)
            dest.write("\n")
    print(record["status"])


if __name__ == "__main__":
    main()
