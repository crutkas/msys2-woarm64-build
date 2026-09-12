"""Fail-closed composition of a private native SQLite shell-consumer runtime."""

import json
from pathlib import Path
import shutil

from sources import ContractError, digest, inventory, relative_path


def sealed_json(path, expected):
    path = Path(path)
    if digest(path) != expected:
        raise ContractError(f"Sealed consumer receipt differs: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_files(root, expected):
    actual = inventory(root)
    if actual != expected:
        changed = sorted(p for p in actual.keys() | expected.keys() if actual.get(p) != expected.get(p))
        raise ContractError(f"Consumer input inventory differs: {root}: {changed[:12]}")


def merge_files(source, destination, files, *, omit=()):
    for name, row in files.items():
        relative_path(name)
        if name in omit:
            continue
        if "symlink" in row:
            raise ContractError(f"Native consumer composition requires explicit link support: {name}")
        target = destination / name
        if target.exists():
            if not target.is_file() or digest(target) != row["sha256"]:
                raise ContractError(f"Conflicting consumer payload without an explicit overlay: {name}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
            if digest(target) != row["sha256"]:
                raise ContractError(f"Consumer copy changed: {name}")


def compose(lock, runtime):
    baseline = sealed_json(lock["baseline"]["manifest"], lock["baseline"]["sha256"])
    if (baseline["status"] != "native-msys-sqlite-targeted-consumers-recorded"
            or baseline["input_integrity_errors"] or not baseline["tdbc_passed"]
            or baseline["shell_pipe_passed"] or baseline["shell5_import_passed"]):
        raise ContractError("The exact failed shell/passed TDBC baseline is required")
    base_root = Path(lock["baseline"]["root"]) / "runtime"
    verify_files(base_root, baseline["runtime_files"])
    utilities = sealed_json(lock["utilities"]["manifest"], lock["utilities"]["sha256"])
    utility_root = Path(lock["utilities"]["root"])
    verify_files(utility_root, utilities["files"])
    bash = sealed_json(lock["bash"]["manifest"], lock["bash"]["sha256"])
    bash_root = Path(lock["bash"]["root"])
    for name in ("usr/bin/bash.exe", "usr/bin/sh.exe"):
        if (bash["files"][name]["sha256"] != lock["bash"]["binary_sha256"]
                or digest(bash_root / name) != lock["bash"]["binary_sha256"]):
            raise ContractError("Native Bash/sh candidate bytes differ")
    runtime_receipt = sealed_json(lock["runtime"]["receipt"], lock["runtime"]["receipt_sha256"])
    if (runtime_receipt["status"] != "coherent-runtime-execvp-errno-qualified"
            or runtime_receipt["binaries"]["runtime"]["sha256"] != lock["runtime"]["sha256"]
            or digest(lock["runtime"]["path"]) != lock["runtime"]["sha256"]):
        raise ContractError("Qualified d70 runtime receipt differs")
    provider = sealed_json(lock["runtime_provider"]["manifest"], lock["runtime_provider"]["sha256"])
    if provider["status"] != "admitted-current-d70-native-msys2-runtime-exported":
        raise ContractError("Expected the separately admitted d70 runtime export")
    runtime.mkdir()
    overlays = ("usr/bin/bash.exe", "usr/bin/sh.exe", "usr/bin/msys-2.0.dll")
    # Both stages contain their own generated global Info index. Keep the
    # original baseline index in this runtime-only composition; do not
    # overwrite either producer's index or claim a newly installed package.
    info_index = "usr/share/info/dir"
    if info_index not in baseline["runtime_files"] or info_index not in utilities["files"]:
        raise ContractError("Expected both pinned producer Info indexes")
    merge_files(utility_root, runtime, utilities["files"], omit=(*overlays, info_index))
    merge_files(base_root, runtime, baseline["runtime_files"], omit=overlays)
    for name in overlays[:2]:
        shutil.copyfile(bash_root / name, runtime / name)
    shutil.copyfile(lock["runtime"]["path"], runtime / overlays[2])
    files = inventory(runtime)
    for name, row in baseline["runtime_files"].items():
        if name not in overlays and files.get(name) != row:
            raise ContractError(f"An original SQLite/Tcl dependency file changed: {name}")
    if files["etc/fstab"] != baseline["runtime_files"]["etc/fstab"]:
        raise ContractError("Private mount policy must not change")
    verify_files(base_root, baseline["runtime_files"])
    verify_files(utility_root, utilities["files"])
    return {
        "files": files, "old_runtime_sha256": baseline["runtime_files"]["usr/bin/msys-2.0.dll"]["sha256"],
        "runtime_sha256": lock["runtime"]["sha256"],
        "bash_sha256": lock["bash"]["binary_sha256"],
        "fstab_unchanged": True, "sqlite_tcl_zlib_files_unchanged": True,
        "utility_info_index_not_overlaid": {"path": info_index, "record": utilities["files"][info_index],
                                            "reason": "Runtime-only composite retains baseline Info index; not package installation"},
        "scope": "Native shell/utilities addition and d70 runtime substitution only; Bash candidate admission remains pending",
    }
