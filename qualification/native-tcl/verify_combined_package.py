"""Replay the delivered Tcl ZIP from a fresh extraction with only its declared native dependencies."""

import json
from pathlib import Path
import shutil
import zipfile

import combined_runtime
import qualify
from finalize import generation_state, reference
from qualify import ROOT, digest, import_tools, read_json, require, verify_inputs, write_json


ORIGINAL = ROOT / "combined-20260911-01"
OUTPUT = ROOT / "combined-20260911-package-01"


def main():
    sources = import_tools()
    combined_runtime.verify_private()
    receipt_path = ORIGINAL / "result.json"
    receipt = read_json(receipt_path)
    require(receipt["runtime_sha256"] == combined_runtime.RUNTIME_SHA and receipt["all_packaged_pe_aa64"],
            "Expected the actual newly-qualified native Tcl package")
    archive = Path(receipt["archive"]["path"])
    require(digest(archive) == receipt["archive"]["sha256"], "Package archive changed")
    OUTPUT.mkdir()
    for path in Path(__file__).parent.iterdir():
        if path.suffix in (".py", ".tcl"):
            shutil.copyfile(path, OUTPUT / path.name)
    runtime = OUTPUT / "extracted"
    runtime.mkdir()
    with zipfile.ZipFile(archive) as zip:
        require(len(zip.infolist()) == len(receipt["files"]) and
                set(zip.namelist()) == set(receipt["files"]), "ZIP member set differs from package receipt")
        for entry in zip.infolist():
            parts = entry.filename.split("/")
            require(not entry.is_dir() and all(part not in ("", ".", "..") for part in parts) and
                    ":" not in entry.filename and "\\" not in entry.filename and
                    entry.create_system == 0 and not entry.external_attr & 0x400,
                    "Only explicit regular Windows ZIP files are accepted")
            destination = runtime.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zip.open(entry) as source, destination.open("xb") as target:
                shutil.copyfileobj(source, target)
    require(sources.inventory(runtime) == receipt["files"], "Extracted package is not byte-identical")
    dependencies = {}
    for name, record in receipt["runtime_dependencies"].items():
        origin = ORIGINAL / "runtime" / name
        require(digest(origin) == record["sha256"], "Declared dependency changed")
        destination = runtime / name
        require(not destination.exists(), "Package may not overwrite assembler-owned dependencies")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
        dependencies[name] = record
    files = sources.inventory(runtime)
    require(files == {**receipt["files"], **dependencies}, "Unexpected extraction/runtime dependency")
    before = reference(receipt_path)
    pe = {name: combined_runtime.pe_record(runtime / name)
          for name in files if (runtime / name).suffix.lower() in (".exe", ".dll")}
    write_json(OUTPUT / "inputs.json", {
        "package": before, "archive": reference(archive), "files": files,
        "declared_dependency_additions": dependencies, "pe": pe,
        "scripts": {p.name: reference(p) for p in OUTPUT.iterdir() if p.suffix in (".py", ".tcl")},
    })
    row = qualify.run("combined-20260911-zip-alias-api", "api", runtime=runtime, jobs=2,
                      interpreter_name="tclsh.exe")
    run_root = ROOT / "combined-20260911-zip-alias-api"
    observed = read_json(run_root / "native-job.json")
    require(row["status"] == "passed" and observed["observation_count_matches"] and
            observed["created_processes"] == observed["observed_processes"] == 2 and
            len(observed["native_target_exits"]) == 1 and
            observed["native_target_exits"][0]["raw_exit"] == 0,
            "Actual extracted package alias/API must succeed with complete raw exit evidence")
    native = observed["native_target_exits"][0]
    drain = generation_state(native["pid"], native["created"])
    require(sources.inventory(runtime) == files, "Package/API changed the extracted runtime")
    require(digest(receipt_path) == before["sha256"], "Original combined receipt changed")
    combined_runtime.verify_private()
    verify_inputs()
    write_json(OUTPUT / "qualification.json", {
        "status": "actual-zip-extracted-native-tcl-alias-and-extensions-passed",
        "inputs": reference(OUTPUT / "inputs.json"), "result": reference(run_root / "result.json"),
        "launch": read_json(run_root / "launch.json"), "raw_observer": reference(run_root / "native-job.json"),
        "modules": reference(run_root / "validated-modules.json"), "drain": drain,
        "files_unchanged": True, "all_pe_aa64": True,
        "scope": "Windows ZIP regular-file extraction plus exact declared907afa/zlib/fstab dependencies; "
                 "actual unversioned Tcl alias and core/Itcl/TDBC/Thread API, no x64 driver"},
    )
    receipt["supersedes"] = before
    receipt["zip_extraction_qualification"] = reference(OUTPUT / "qualification.json")
    receipt["actual_supported_paths"] = [
        "usr/bin/tclsh.exe", "usr/bin/tclsh8.6.exe", "usr/bin/libtcl8.6.dll",
        "usr/lib/itcl4.2.2", "usr/lib/tdbc1.1.3", "usr/lib/thread2.8.7",
    ]
    receipt["not_supported_without_separate_native_provider"] = [
        "tdbc::mysql native MySQL/MariaDB client", "tdbc::postgres native PostgreSQL client",
        "tdbc::odbc native ODBC connector", "tdbc::sqlite3 separate native sqlite3 Tcl binding",
        "MinGW Tcl/Tk GUI",
    ]
    receipt["metadata_contract"] = read_json(ROOT / "provider-02/result.json")["metadata_contract"]
    receipt["drain"]["observed_jobs"] += 1
    receipt["drain"]["generations"].append(drain)
    receipt["limitations"] = [item for item in receipt["limitations"]
                              if not item.startswith("Declared executable alias")]
    receipt["limitations"].append(
        "Known aliases are explicit byte-identical regular copies, not symlinks; actual extracted tclsh.exe exercised")
    write_json(OUTPUT / "package-receipt.json", receipt)
    print(json.dumps({"package_receipt": reference(OUTPUT / "package-receipt.json"),
                      "actual_extraction_proof": reference(OUTPUT / "qualification.json"),
                      "native_pid": native["pid"], "birth": native["created"],
                      "archive": receipt["archive"], "returnable_jobs": 2}), flush=True)


if __name__ == "__main__":
    main()
