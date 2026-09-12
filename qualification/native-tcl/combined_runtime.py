"""Qualify already-built native MSYS Tcl with the sealed combined runtime and export its package."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zipfile

import qualify
from finalize import generation_state, reference
from package_provider import ALIASES, RECIPE, RECIPE_SHA
from qualify import ROOT, digest, import_tools, read_json, require, require_memory, verify_inputs, write_json


OUTPUT = ROOT / "combined-20260911-01"
HANDOFF = Path(r"C:\Users\crutkasLocal\.copilot\session-state\67ba2e76-32e2-4f0d-a2fe-844ee8fe1d8a"
               r"\files\combined-runtime-20260911\handoff\combined-runtime-handoff.json")
HANDOFF_SHA = "f8c7c49b46fdf0844555b99d3c1e4d2c342817a8b01eef1e9f283875796e2b9b"
OLD_HANDOFF = ROOT / "handoff-04/result.json"
OLD_HANDOFF_SHA = "7e4b6af51a6423f426fbb85720f7506de703ec801f65c8957f2df184a3548194"
PROVIDER = ROOT / "provider-02"
RUNTIME_SHA = "907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c"
TOTAL_FIELDS = ("total", "passed", "skipped", "failed")
SHARED_FILES = {"usr/bin/msys-2.0.dll", "usr/bin/msys-z.dll", "etc/fstab"}


def local_path(value):
    if value.startswith("/root/"):
        return Path(r"\\wsl.localhost\Ubuntu") / Path(value[1:].replace("/", "\\"))
    return Path(value)


def stable_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def pe_record(path):
    """Read machine and normal/delay import tables from the actual on-disk PE bytes."""
    data = path.read_bytes()

    def unpack(fmt, offset):
        require(0 <= offset <= len(data) - struct.calcsize(fmt), "PE structure outside file")
        return struct.unpack_from(fmt, data, offset)

    require(data[:2] == b"MZ", "Expected actual PE DOS signature")
    pe = unpack("<I", 60)[0]
    require(pe >= 64 and data[pe:pe + 4] == b"PE\0\0", "Expected PE signature")
    machine, count = unpack("<HH", pe + 4)
    optional_size, characteristics = unpack("<HH", pe + 20)
    optional = pe + 24
    require(machine == 0xAA64 and optional_size >= 112 and unpack("<H", optional)[0] == 0x20B,
            f"Package contains a non-AA64 PE32+ image: {path}")
    sections = []
    for index in range(count):
        entry = optional + optional_size + index * 40
        _, virtual, raw_size, raw = unpack("<IIII", entry + 8)
        require(raw + raw_size <= len(data), "PE section outside file")
        sections.append((virtual, raw_size, raw))

    def offset_for(rva, size):
        matches = [(raw + rva - virtual, raw + raw_size) for virtual, raw_size, raw in sections
                   if virtual <= rva and rva + size <= virtual + raw_size]
        require(len(matches) == 1, "Unmapped or ambiguous PE RVA")
        return matches[0]

    def name_for(rva):
        start, end = offset_for(rva, 1)
        stop = data.find(b"\0", start, end)
        require(stop > start, "Unterminated PE import name")
        return data[start:stop].decode("ascii")

    imports = {}
    directory_count = unpack("<I", optional + 108)[0]
    for directory_index, descriptor_size in ((1, 20), (13, 32)):
        if directory_count <= directory_index:
            continue
        require(optional_size >= 112 + (directory_index + 1) * 8, "Truncated PE directories")
        rva, size = unpack("<II", optional + 112 + directory_index * 8)
        if not rva:
            continue
        require(size >= descriptor_size, "Truncated import directory")
        offset, limit = offset_for(rva, descriptor_size)
        while True:
            require(offset + descriptor_size <= limit, "Unterminated PE import descriptors")
            values = unpack("<" + "I" * (descriptor_size // 4), offset)
            if not any(values):
                break
            if directory_index == 1:
                original, _, _, name_rva, first = values
                thunk = original or first
            else:
                attributes, name_rva, _, first, thunk, _, _, _ = values
                require(attributes == 1, "VA-form delay imports need separate review")
                thunk = thunk or first
            name = name_for(name_rva).lower()
            require(name not in imports, "Duplicate normal/delay DLL import")
            table, table_end = offset_for(thunk, 8)
            symbols = []
            while True:
                require(table + 8 <= table_end, "Unterminated import thunk")
                value = unpack("<Q", table)[0]
                if value == 0:
                    break
                symbols.append({"ordinal": value & 0xFFFF} if value & (1 << 63)
                               else {"name": name_for(value + 2)})
                table += 8
            imports[name] = symbols
            offset += descriptor_size
    return {"path": str(path), "size": len(data), "sha256": digest(path),
            "machine": "0xAA64", "format": "PE32+", "is_dll": bool(characteristics & 0x2000),
            "imports": imports}


def verify_origin():
    sources = import_tools()
    require(digest(HANDOFF) == HANDOFF_SHA, "Combined runtime handoff changed")
    require(digest(OLD_HANDOFF) == OLD_HANDOFF_SHA, "Old Tcl handoff changed")
    runtime = read_json(HANDOFF)
    require(runtime["runtime"]["sha256"] == RUNTIME_SHA and
            runtime["results"]["headers_and_jump_abi_unchanged"] is True,
            "Expected the exact combined runtime and unchanged public jump ABI")
    for name in ("runtime", "second_runtime", "import_library", "startup", "header",
                 "generated_header", "source_manifest"):
        row = runtime[name]
        require(digest(local_path(row["path"])) == row["sha256"], f"Runtime handoff input changed: {name}")
    sources.verify_tree(PROVIDER / "payload", PROVIDER / "result.json")
    require(digest(RECIPE) == RECIPE_SHA, "Pinned Tcl packaging recipe changed")
    verify_inputs()
    return runtime


def prepare():
    sources = import_tools()
    runtime = verify_origin()
    OUTPUT.mkdir()
    shutil.copytree(PROVIDER / "payload", OUTPUT / "runtime")
    shutil.copyfile(local_path(runtime["runtime"]["path"]), OUTPUT / "runtime/usr/bin/msys-2.0.dll")
    shutil.copyfile(OUTPUT / "runtime/usr/bin/tclsh8.6.exe", OUTPUT / "runtime/usr/bin/tclsh.exe")
    for path in Path(__file__).parent.iterdir():
        if path.suffix in (".py", ".tcl"):
            shutil.copyfile(path, OUTPUT / path.name)
    original = sources.inventory(PROVIDER / "payload")
    private = sources.inventory(OUTPUT / "runtime")
    require(set(private) - set(original) == {"usr/bin/tclsh.exe"} and
            set(original) - set(private) == set() and
            {p for p in original if private[p] != original[p]} == {"usr/bin/msys-2.0.dll"} and
            private["usr/bin/tclsh.exe"] == private["usr/bin/tclsh8.6.exe"],
            "Only the qualified runtime and declared byte-identical interpreter alias may change")
    pe = {name: pe_record(OUTPUT / "runtime" / name) for name in private
          if (OUTPUT / "runtime" / name).suffix.lower() in (".exe", ".dll")}
    from pe_exports import export_names
    exports = set(export_names((OUTPUT / "runtime/usr/bin/msys-2.0.dll").read_bytes()))
    for row in pe.values():
        for symbol in row["imports"].get("msys-2.0.dll", []):
            require("name" in symbol and symbol["name"] in exports,
                    "An existing Tcl/zlib/extension import is not exported by the new runtime")
    inputs = read_json(ROOT / "inputs.json")
    source = Path(r"C:\ag-e138920f\tcl-msys-02\source")
    source_files = inputs["shared"][str(source)]
    raw_manifest = Path(r"C:\ag-e138920f\sqlite-tcl-inputs-01\sources\tcl-msys.inventory.json")
    recipe_manifest = RECIPE.parent.parent.with_name("msys-upstream-recipes.inventory.json")
    raw = read_json(raw_manifest)
    recipe = read_json(recipe_manifest)
    write_json(OUTPUT / "inputs.json", {
        "schema": 1, "runtime_handoff": reference(HANDOFF), "old_tcl_handoff": reference(OLD_HANDOFF),
        "old_provider": reference(PROVIDER / "result.json"),
        "qualified_runtime": {name: {"path": str(local_path(runtime[name]["path"])),
                                     "sha256": runtime[name]["sha256"]}
                              for name in ("runtime", "second_runtime", "import_library", "startup",
                                           "header", "generated_header", "source_manifest")},
        "runtime_files": private, "all_runtime_view_pe": pe,
        "runtime_import_names_resolved": True,
        "scope": "Already-built Tcl binaries are not relinked: combined import-library/CRT identities "
                 "are verified as runtime provenance, not falsely claimed as original Tcl build inputs",
        "source_provenance": {
            "upstream": raw["source"], "archive_manifest": reference(raw_manifest),
            "upstream_fossil_commit": (ROOT / "source/manifest.uuid").read_text().strip(),
            "upstream_git_commit": None,
            "source_tree": {"algorithm": "sha256-canonical-json-path-size-sha256-inventory",
                            "sha256": stable_digest(source_files), "files": len(source_files),
                            "path": str(source), "inventory": source_files},
            "recipe": reference(RECIPE), "recipe_repository": "https://github.com/msys2/MSYS2-packages",
            "recipe_commit": recipe["source"]["version"], "recipe_collection_manifest": reference(recipe_manifest),
            "official_source_patch": reference(ROOT / "tools/patches/tcl-msys-8.6.12.src.patch"),
            "build_completion": reference(Path(r"C:\ag-e138920f\tcl-msys-finish-03\result.json")),
            "compiler_receipt": reference(Path(r"C:\ag-e138920f\tc-guard-01.copy.json")),
            "runtime_publication": runtime["publication"], "runtime_source_manifest": runtime["source_manifest"],
        },
        "scripts": {p.name: reference(p) for p in OUTPUT.iterdir() if p.suffix in (".py", ".tcl")},
    })
    print(json.dumps({"prepared": str(OUTPUT), "files": len(private), "pe_count": len(pe),
                      "runtime": RUNTIME_SHA}), flush=True)


def verify_private():
    sources = import_tools()
    inputs = read_json(OUTPUT / "inputs.json")
    require(sources.inventory(OUTPUT / "runtime") == inputs["runtime_files"], "Private new runtime view changed")
    for row in inputs["scripts"].values():
        require(digest(row["path"]) == row["sha256"], "Combined qualification script snapshot changed")
    verify_origin()
    return inputs


def test(name, mode, files=None, interpreter_name="tclsh8.6.exe"):
    verify_private()
    result = qualify.run("combined-20260911-01-" + name, mode, files, runtime=OUTPUT / "runtime", jobs=2,
                         interpreter_name=interpreter_name)
    path = ROOT / ("combined-20260911-01-" + name)
    observed = read_json(path / "native-job.json")
    require(observed["observation_count_matches"] and not observed["timed_out"] and
            not observed["unobserved_process_ids"], "Incomplete new-runtime process evidence")
    launch = read_json(path / "launch.json")
    state = generation_state(launch["pid"], launch["creation_filetime"])
    verify_private()
    row = {"name": name, "mode": mode, "result": reference(path / "result.json"),
           "semantic_passed": result["semantic_passed"], "observer_passed": observed["passed"],
           "launch": launch, "modules": reference(path / "validated-modules.json"),
           "summaries": result["summaries"], "skips": result["skipped_tests"],
           "failed_tests": result["failed_tests"], "file_errors": result["file_errors"],
           "observer": reference(path / "native-job.json"), "observation": observed,
           "drain": state}
    print(json.dumps({"completed": name, "launch": launch, "semantic_passed": row["semantic_passed"],
                      "observer_passed": row["observer_passed"], "summaries": row["summaries"]}), flush=True)
    return row


def run_tests():
    require(Path(__file__).parent == OUTPUT, "Run the sealed private driver snapshot")
    profile = read_json(OLD_HANDOFF)["coverage"]["files"]
    rows = []
    api = test("api", "api")
    rows.append(api)
    require(api["semantic_passed"] and api["observer_passed"], "Installed API failed against new runtime")
    alias = test("alias-api", "api", interpreter_name="tclsh.exe")
    rows.append(alias)
    require(alias["semantic_passed"] and alias["observer_passed"], "Actual unversioned Tcl alias failed")
    for name in profile:
        row = test(name, "suite", [name])
        rows.append(row)
        if not row["semantic_passed"] or (name != "basic" and not row["observer_passed"]):
            write_json(OUTPUT / "tests.json", {"status": "failed", "rows": rows, "not_run": profile[len(rows) - 2:]})
            raise ValueError(f"New-runtime test qualification failed: {name}")
    write_json(OUTPUT / "tests.json", {
        "status": "native-new-runtime-api-and-scoped-core-semantics-passed",
        "rows": rows, "full_suite": False, "expected_negative_observer_unchanged": True,
    })
    publish()


def publish():
    sources = import_tools()
    inputs = verify_private()
    tests = read_json(OUTPUT / "tests.json")
    require(tests["status"] == "native-new-runtime-api-and-scoped-core-semantics-passed",
            "Package needs actual new-runtime test qualification first")
    package = OUTPUT / "package"
    package.mkdir()
    for name in inputs["runtime_files"]:
        if name in SHARED_FILES:
            continue
        destination = package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OUTPUT / "runtime" / name, destination)
    aliases = {}
    for name, relative in ALIASES.items():
        target = (package / name).parent / relative
        target = target.resolve()
        require(target.is_relative_to(package) and target.is_file(), "Known alias target must be an internal file")
        if (package / name).exists():
            require(digest(package / name) == digest(target), "Existing declared alias is not byte-identical")
        else:
            shutil.copyfile(target, package / name)
        aliases[name] = {"kind": "explicit-byte-identical-copy-not-symlink", "recipe_relative_target": relative,
                         "resolved_target": target.relative_to(package).as_posix(), "sha256": digest(target),
                         "executable": name.endswith(".exe")}
    files = sources.inventory(package)
    require(not any("symlink" in row for row in files.values()), "ZIP provider may not contain implicit links")
    pe = {}
    for name in files:
        path = package / name
        with path.open("rb") as stream:
            header = stream.read(2)
        if header == b"MZ" or path.suffix.lower() in (".exe", ".dll", ".pyd", ".ocx", ".scr", ".cpl"):
            pe[name] = pe_record(path)
    totals, skipped = Counter(), Counter()
    for row in (item for item in tests["rows"] if item["mode"] == "suite"):
        require(len(row["summaries"]) == 1, "One summary per unchanged core file required")
        totals.update({k: row["summaries"][0][k] for k in TOTAL_FIELDS})
        skipped.update(reason for _, reason in row["skips"])
    archive = OUTPUT / "tcl-msys-8.6.12-arm64-combined-907afa.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=(2021, 10, 29, 0, 0, 0))
            entry.create_system = 0
            zip.writestr(entry, (package / name).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(archive) as zip:
        require(sorted(zip.namelist()) == sorted(files), "Archive inventory differs")
        for name in files:
            require(hashlib.sha256(zip.read(name)).hexdigest() == files[name]["sha256"],
                    "Archive file bytes differ")
    require(sources.inventory(package) == files, "Export changed during ZIP creation")
    states = []
    for row in tests["rows"]:
        observed = row["observation"]
        for item in observed["native_target_exits"]:
            states.append(generation_state(item["pid"], item["created"]))
    verify_private()
    write_json(OUTPUT / "package-manifest.json", {"files": files})
    write_json(OUTPUT / "result.json", {
        "schema": 1, "status": "native-tcl-package-combined-runtime-scoped-qualified",
        "package": "tcl-msys", "version": "8.6.12", "target": "aarch64-pc-cygwin",
        "build_host": "windows-arm64-native-existing-build", "qualification_host": "windows-arm64-native",
        "package_root": str(package), "files": files, "manifest": reference(OUTPUT / "package-manifest.json"),
        "archive": {**reference(archive), "size": archive.stat().st_size}, "pe": pe,
        "all_packaged_pe_aa64": True, "aliases": aliases,
        "source_provenance": inputs["source_provenance"], "inputs": reference(OUTPUT / "inputs.json"),
        "runtime_handoff": reference(HANDOFF), "runtime_sha256": RUNTIME_SHA,
        "runtime_dependencies": {name: inputs["runtime_files"][name] for name in sorted(SHARED_FILES)},
        "dependency_contract": "Artifact assembler supplies canonical usr/bin/msys-2.0.dll at exact907afa "
                               "and native msys-z.dll plus approved private mounts. Package does not overwrite these.",
        "compatibility_runtime_root": str(OUTPUT / "runtime"), "tests": reference(OUTPUT / "tests.json"),
        "coverage": {"files": [row["name"] for row in tests["rows"] if row["mode"] == "suite"], "totals": dict(totals),
                     "constraint_skips": dict(skipped), "full_suite": False},
        "admission": "Actual native interpreter/extensions and selected unchanged core qualification against "
                     "new runtime; do not substitute old1bdf results as current evidence",
        "limitations": [
            "Full upstream/bundled suites not run",
            "Original expected-negative high-exit collector records retained; no universal exit-domain promotion",
            "Native MSYS Unix Tcl is not MinGW GUI Tcl/Tk; no Tk provided",
            "External MySQL/ODBC/Postgres accounts/connectors not exercised; SQLite binding owned separately",
            "Declared executable alias is a byte-identical copy, not a symlink; actual alias launch is qualified",
        ],
        "old_inputs_unchanged": True, "runtime_or_tcl_rebuilds": 0, "x64_payload_count": 0,
        "drain": {"recorded_utc": datetime.now(timezone.utc).isoformat(), "generations": states,
                  "observed_jobs": len(tests["rows"]), "active_owned_generations": 0,
                  "fresh_grant": 2, "returnable_jobs": 2, "free_memory": require_memory()},
    })
    print(json.dumps({"result": reference(OUTPUT / "result.json"), "archive": reference(archive),
                      "coverage": dict(totals), "packaged_pe": len(pe)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "test"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        run_tests()
