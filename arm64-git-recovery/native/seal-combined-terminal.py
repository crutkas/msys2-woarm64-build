"""Publish additive package/runtime compatibility receipts and an MVP-only projection."""

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import zipfile

from sources import ContractError, digest, inventory
from ssh_bootstrap import write_json

inputs = importlib.import_module("prepare-combined-terminal")
ROOT, HERE = inputs.ROOT, inputs.HERE
REQUIRED = {
    "readline-shared-tty": ("readline-signals", "shared", "tty"),
    "readline-shared-kill": ("readline-signals", "shared", "kill"),
    "readline-static-tty": ("readline-signals", "static", "tty"),
    "readline-static-kill": ("readline-signals", "static", "kill"),
    "ncurses-shared": ("ncurses", "shared", None),
    "ncurses-static": ("ncurses", "static", None),
    "libedit-shared": ("libedit", "shared", None),
    "libedit-static": ("libedit", "static", None),
    "history-shared": ("history", "shared", None),
    "history-static": ("history", "static", None),
}


def main():
    output = ROOT / "handoff"
    if output.exists():
        raise ContractError("Fresh final compatibility handoff required")
    record = json.loads((ROOT / "inputs.json").read_text())
    inputs.sealed(inputs.HANDOFF, inputs.HANDOFF_SHA)
    cases = {}
    for key, expected in REQUIRED.items():
        candidates = []
        for result in sorted(ROOT.glob(key + "-*/result.json")):
            case = json.loads(result.read_text())
            if case["status"] == "passed-real-AA64-packages-on-combined-native-runtime":
                candidates.append((result, case))
        if not candidates:
            raise ContractError(f"No successful required compatibility proof: {key}")
        result, case = candidates[-1]
        if (case["kind"], case["linkage"]) != expected[:2] or (expected[2] and case["signal_mode"] != expected[2]):
            raise ContractError(f"Wrong case scope: {key}")
        if (case["runtime_sha256"] != inputs.RUNTIME_SHA
                or case["input_receipt_sha256"] != digest(ROOT / "inputs.json")
                or not case["process"]["passed"] or not case["result"]["passed"]):
            raise ContractError("A successful target proof is required, not a parent zero or old epoch")
        cases[key] = {"path": str(result), "sha256": digest(result),
                      "launch": str(result.parent / "launch.json"),
                      "launch_sha256": digest(result.parent / "launch.json"),
                      "launcher_pid": case["pid"], "launcher_creation_filetime": case["creation_filetime"],
                      "process": case["process"], "api": case["result"]["api"],
                      "loaded_modules": {"path": str(result.parent / "loaded-modules.json"),
                                         "sha256": digest(result.parent / "loaded-modules.json")},
                      "pty_transcript_sha256": case["result"]["transcript_sha256"]}
    payload = ROOT / "runtime-payload"
    if inventory(payload) != record["runtime_payload_files"]:
        raise ContractError("Runtime-only projection changed since package extraction")
    output.mkdir()
    archive = output / "native-terminal-runtime-907afa09.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, row in record["runtime_payload_files"].items():
            if name.endswith((".a", ".exe", ".la", ".pc")) or name.startswith("usr/include/"):
                raise ContractError("Devel/static/unrelated tools leaked into MVP projection")
            zipped.write(payload / name, name)
    with zipfile.ZipFile(archive) as zipped:
        if set(zipped.namelist()) != set(record["runtime_payload_files"]):
            raise ContractError("MVP ZIP coverage mismatch")
        for name, row in record["runtime_payload_files"].items():
            if hashlib.sha256(zipped.read(name)).hexdigest() != row["sha256"]:
                raise ContractError("MVP ZIP member hash mismatch")
    dlls = {name: {**row, **inputs.pe((payload / name).read_bytes())}
            for name, row in record["runtime_payload_files"].items() if name.endswith(".dll")}
    packages = []
    for package in record["packages"]:
        path = Path(package["path"])
        inputs.sealed(path, package["sha256"])
        if path.stat().st_size != package["size"]:
            raise ContractError("Package archive size changed")
        packages.append({key: package[key] for key in ("path", "size", "sha256", "provider", "provider_export_sha256", "pkginfo")})
    provenance = {}
    for name, source in record["source_provenance"].items():
        inputs.sealed(source["handoff"], source["handoff_sha256"])
        producer = json.loads(Path(source["handoff"]).read_text())
        working = producer.get("source", {}).get("working_source_manifest")
        working_sha = producer.get("source", {}).get("working_source_manifest_sha256")
        if working:
            inputs.sealed(working, working_sha)
        provenance[name] = {**source, "working_source_tree_manifest": working,
                            "working_source_tree_manifest_sha256": working_sha,
                            "static_cpp_delta": producer.get("static_cpp_delta"),
                            "static_library_delta": producer.get("static_library_delta"),
                            "original_runtime_sha256": producer["runtime_sha256"]}
    code_paths = [HERE / "prepare-combined-terminal.py", HERE / "test-combined-terminal.py",
                  HERE / "seal-combined-terminal.py", HERE / "test_combined_terminal.py",
                  HERE / "fixtures/native-readline-signals.c",
                  HERE / "bounded_process.py", HERE / "test_bounded_process.py"]
    code = output / "maintained"
    code.mkdir()
    for path in code_paths:
        shutil.copyfile(path, code / path.name)
    report = {
        "schema": 1, "status": "admitted-terminal-package-bytes-compatible-with-combined-907-native-runtime-in-named-scopes",
        "runtime": {"path": str(payload / "usr/bin/msys-2.0.dll"), "sha256": inputs.RUNTIME_SHA,
                    "size": (payload / "usr/bin/msys-2.0.dll").stat().st_size,
                    "machine": "0xAA64", "handoff": str(inputs.HANDOFF), "handoff_sha256": inputs.HANDOFF_SHA,
                    "source_commit": record["runtime_source_commit"], "source_manifest": record["runtime_source_tree_manifest"]},
        "real_packages": packages, "all_package_pe": record["all_package_pe"],
        "source_provenance": provenance, "cases": cases,
        "mvp_projection": {"path": str(archive), "size": archive.stat().st_size, "sha256": digest(archive),
                           "files": record["runtime_payload_files"], "dlls": dlls,
                           "scope": "DLLs, canonical terminfo, licenses/locale/data and inputrc only; excludes devel/static/unrelated tools"},
        "observer_manifest_sha256": inputs.OBSERVER_SHA,
        "input_receipt": str(ROOT / "inputs.json"), "input_receipt_sha256": digest(ROOT / "inputs.json"),
        "maintained_sources": inventory(code),
        "helper_controls": {"path": str(ROOT / "helper-tests-02.log"),
                            "sha256": digest(ROOT / "helper-tests-02.log"),
                            "scope": "28 existing/new unittest cases, including AA64 rejection, full signal matrix, retained orphan failure and bounded teardown"},
        "failed_attempts_preserved": [
            {"path": str(path), "sha256": digest(path), "error": result.get("error")}
            for path in sorted(ROOT.glob("*/result.json"))
            if (result := json.loads(path.read_text())).get("status") == "failed"
        ],
        "rebuilds": {"runtime": False, "admitted_libraries": False, "admitted_packages": False, "only_test_fixtures_compiled": True},
        "supported_test_path": {"x64_payloads": 0, "native_python": True, "private_DLL_PATH": True,
                                "real_owned_MSYS_PTY": True, "desktop_console_touched": False},
        "scope_limits": ["Additive compatibility, not a relabeling of original producer build/runtime provenance",
                         "Does not replace the Bash/SSH/Git/HTTPS supported-path acceptance owned by their producers and MVP assembly",
                         "OS modules are host Windows components, not redistributed package payload",
                         "Runtime-only ZIP uses canonical usr/share/terminfo; original package relative symlink stays in unchanged package archives"],
    }
    write_json(output / "handoff.json", report)
    print(json.dumps({"handoff": str(output / "handoff.json"), "sha256": digest(output / "handoff.json"),
                      "runtime_zip": str(archive), "runtime_zip_sha256": digest(archive),
                      "cases": len(cases), "AA64_runtime_DLLs": len(dlls)}), flush=True)


if __name__ == "__main__":
    main()
