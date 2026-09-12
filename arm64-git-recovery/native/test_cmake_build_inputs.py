import json
from pathlib import Path
import tempfile
import unittest

from cmake_build_inputs import cmocka_build_input, require_build_tree_mode
from sources import ContractError, digest, inventory


class CmakeBuildInputControls(unittest.TestCase):
    def test_only_explicit_compile_only_libcbor_may_use_build_tree(self):
        values = (Path("result"), Path("source"), "1" * 64)
        self.assertTrue(require_build_tree_mode("libcbor", True, None, *values))
        self.assertFalse(require_build_tree_mode("libcbor", True, None, None, None, None))
        for package, build_only, stage, result, source, sha in (
                ("libcbor", False, None, *values), ("cmocka", True, None, *values),
                ("libcbor", True, Path("installed"), *values),
                ("libcbor", True, None, values[0], None, values[2])):
            with self.assertRaises(ContractError):
                require_build_tree_mode(package, build_only, stage, result, source, sha)

    def test_exact_source_compiler_and_three_real_input_files_are_bound(self):
        with tempfile.TemporaryDirectory(prefix="cmocka-build-input-") as temporary:
            root = Path(temporary)
            source, build = root / "source", root / "build"
            (source / "include").mkdir(parents=True)
            (build / "src").mkdir(parents=True)
            (source / "include/cmocka.h").write_bytes(b"unexecuted header fixture")
            for name in ("libcmocka.dll.a", "msys-cmocka-0.dll"):
                (build / "src" / name).write_bytes(b"unexecuted library fixture")
            source_manifest, compiler, result = root / "source.json", root / "compiler.json", root / "result.json"
            source_manifest.write_text(json.dumps({"files": inventory(source)}))
            compiler.write_text("compiler identity fixture")
            result.write_text(json.dumps({"package": "cmocka", "status": "native-msys-cmake-built-not-tested",
                                          "inputs_unchanged": True, "compiler_receipt_sha256": digest(compiler),
                                          "source_manifest_sha256": digest(source_manifest),
                                          "compiled_files": inventory(build)}))
            receipt = cmocka_build_input(result, source_manifest, compiler, digest(result))
            self.assertEqual(receipt["status"], "native-msys-cmake-built-not-tested")
            self.assertEqual(receipt["cmake_flags"]["CMAKE_DISABLE_FIND_PACKAGE_PkgConfig"], "ON")
            self.assertEqual(receipt["cmake_flags"]["CMOCKA_LIBRARY"], (build / "src/libcmocka.dll.a").resolve().as_posix())
            with self.assertRaises(ContractError):
                cmocka_build_input(result, source_manifest, compiler, "0" * 64)
            (build / "src/msys-cmocka-0.dll").write_bytes(b"changed")
            with self.assertRaises(ContractError):
                cmocka_build_input(result, source_manifest, compiler, digest(result))
