"""Bind an uninstalled CMocka build strictly for downstream compilation, never test admission."""

import json
from pathlib import Path

from cmake_test_replay import verify_build_files
from sources import ContractError, digest, verify_tree


def require_build_tree_mode(package, build_only, stage, result, source_manifest, result_sha256):
    supplied = (result is not None, source_manifest is not None, result_sha256 is not None)
    if not any(supplied):
        return False
    if not all(supplied) or package != "libcbor" or not build_only or stage is not None:
        raise ContractError("Uninstalled CMocka input requires libcbor build-only mode, all exact receipts, and no installed dependency stage")
    return True


def cmocka_build_input(result_path, source_manifest, compiler_receipt, expected_sha256):
    result_path, source_manifest = Path(result_path).resolve(), Path(source_manifest).resolve()
    if digest(result_path) != expected_sha256:
        raise ContractError("CMocka build-only result identity changed")
    record = json.loads(result_path.read_text(encoding="utf-8"))
    if (record.get("status") != "native-msys-cmake-built-not-tested" or record.get("package") != "cmocka" or
            record.get("inputs_unchanged") is not True or
            record.get("compiler_receipt_sha256") != digest(compiler_receipt) or
            record.get("source_manifest_sha256") != digest(source_manifest)):
        raise ContractError("CMocka must be the exact successful build-only input from this compiler/source cohort")
    root = result_path.parent
    verify_tree(root / "source", source_manifest)
    verify_build_files(root / "build", record["compiled_files"])
    paths = {"header": root / "source/include/cmocka.h",
             "import_library": root / "build/src/libcmocka.dll.a",
             "runtime_library": root / "build/src/msys-cmocka-0.dll"}
    if any(not path.is_file() for path in paths.values()):
        raise ContractError("The actual uninstalled CMocka header/import/DLL set is incomplete")
    return {
        "status": record["status"], "result_path": str(result_path), "result_sha256": expected_sha256,
        "source_manifest": str(source_manifest), "source_manifest_sha256": digest(source_manifest),
        "compiler_receipt_sha256": digest(compiler_receipt),
        "files": {name: {"path": str(path), "sha256": digest(path)} for name, path in paths.items()},
        "cmake_flags": {"CMOCKA_INCLUDE_DIR": paths["header"].parent.as_posix(),
                        "CMOCKA_LIBRARY": paths["import_library"].as_posix(),
                        "CMAKE_DISABLE_FIND_PACKAGE_PkgConfig": "ON"},
        "scope": "Existing uninstalled, untested CMocka used only to compile downstream targets; no CMocka execution/installation/package qualification inferred",
    }
