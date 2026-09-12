import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("private_replay", Path(__file__).with_name("replay-msys-cmake-private.py"))
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class PrivateReplayControls(unittest.TestCase):
    def test_relocation_preserves_flags_and_unrelated_input_paths(self):
        old, new = Path("frozen").resolve(), Path("private").resolve()
        text = f'{old.as_posix()}/build -std=c99 -O3 -Werror C:/frozen-sdk/lib'
        result = replay.relocate(text, old, new)
        self.assertEqual(result, f'{new.as_posix()}/build -std=c99 -O3 -Werror C:/frozen-sdk/lib')

    def test_case_insensitive_cache_paths_but_not_sibling_prefixes_relocated(self):
        old, new = Path("Frozen").resolve(), Path("Private").resolve()
        text = f"{old.as_posix().lower()}/build\n{old.as_posix()}-unrelated/build"
        self.assertEqual(replay.relocate(text, old, new),
                         f"{new.as_posix()}/build\n{old.as_posix()}-unrelated/build")

    @unittest.skipUnless(os.environ.get("NATIVE_TEST_CTEST"), "Explicit existing native CTest path required")
    def test_real_ctest_discovery_never_writes_frozen_dart_build_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original, private = root / "original", root / "private"
            original.mkdir()
            (original / "DartConfiguration.tcl").write_text(f"BuildDirectory: {original.as_posix()}\n")
            (original / "CMakeCache.txt").write_text(f"CMAKE_CACHEFILE_DIR:INTERNAL={original.as_posix()}\n")
            (original / "CTestTestfile.cmake").write_text('add_test(unexecuted "fixture.exe")\n')
            (original / "fixture.exe").write_bytes(b"never executed")
            before = replay.inventory(original)
            shutil.copytree(original, private)
            changes = replay.relocate_metadata(private, original, private)
            self.assertIn("DartConfiguration.tcl", changes)
            self.assertIn("CMakeCache.txt", changes)
            process = subprocess.run([os.environ["NATIVE_TEST_CTEST"], "--test-dir", str(private),
                                      "--show-only=json-v1"], capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(len(json.loads(process.stdout)["tests"]), 1)
            self.assertEqual(replay.inventory(original), before)
            self.assertTrue((private / "Testing/Temporary/LastTest.log").is_file())

    @unittest.skipUnless(os.environ.get("NATIVE_TEST_CMAKE") and os.environ.get("NATIVE_TEST_NINJA"),
                         "Explicit existing native CMake/Ninja paths required")
    def test_real_install_scripts_dispatch_and_manifest_stay_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            original, private = root / "original", root / "private"
            fixture = Path(__file__).parent / "fixtures/cmake-msys-staging"
            shutil.copytree(fixture, original / "source")
            cmake = os.environ["NATIVE_TEST_CMAKE"]
            configured = subprocess.run(
                [cmake, "-S", str(original / "source"), "-B", str(original / "build"), "-G", "Ninja",
                 f"-DCMAKE_MAKE_PROGRAM={Path(os.environ['NATIVE_TEST_NINJA']).as_posix()}",
                 "-DCMAKE_SYSTEM_NAME=MSYS", "-DCMAKE_INSTALL_PREFIX=/usr",
                 f"-DCMAKE_STAGING_PREFIX={(original / 'stage/usr').as_posix()}"],
                capture_output=True, timeout=30)
            self.assertEqual(configured.returncode, 0, configured.stderr)
            before = replay.inventory(original)
            shutil.copytree(original, private)
            changes = replay.relocate_metadata(private / "build", original, private)
            dispatch = original / "build/CMakeFiles/InstallScripts.json"
            if dispatch.exists():
                self.assertIn("CMakeFiles/InstallScripts.json", changes)
            installed = subprocess.run([cmake, "--install", str(private / "build"), "--prefix",
                                        (private / "stage/usr").as_posix()], capture_output=True, timeout=30)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertEqual(replay.inventory(original), before)
            self.assertTrue((private / "build/install_manifest.txt").is_file())
            self.assertEqual((private / "stage/usr/share/staging-control/payload.txt").read_bytes(),
                             (fixture / "payload.txt").read_bytes())

    def test_fido_requires_all_eight_safe_private_executables(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory).resolve()
            tests = []
            for name in sorted(replay.FIDO_TESTS):
                executable = build / (name + ".exe")
                executable.write_bytes(b"unexecuted validation fixture")
                tests.append({"name": name, "command": [str(executable)],
                              "properties": [{"name": "WORKING_DIRECTORY", "value": str(build)}]})
            discovery = {"kind": "ctestInfo", "version": {"major": 1}, "tests": tests}
            self.assertEqual(set(replay.validate_cases(discovery, "libfido2", build)), replay.FIDO_TESTS)
            tests[0]["name"] = "hardware-authentication"
            with self.assertRaises(ContractError):
                replay.validate_cases(discovery, "libfido2", build)
            tests[0]["name"] = sorted(replay.FIDO_TESTS)[0]
            tests[0]["command"][0] = str(build.parent / "outside.exe")
            with self.assertRaises(ContractError):
                replay.validate_cases(discovery, "libfido2", build)

    def test_missing_test_or_outside_working_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory).resolve()
            tests = []
            for index in range(49):
                executable = build / f"test-{index}.exe"
                executable.write_bytes(b"fixture")
                tests.append({"name": f"test-{index}", "command": [str(executable)],
                              "properties": [{"name": "WORKING_DIRECTORY", "value": str(build)}]})
            discovery = {"kind": "ctestInfo", "version": {"major": 1}, "tests": tests}
            self.assertEqual(len(replay.validate_cases(discovery, "cmocka", build)), 49)
            tests[0]["properties"][0]["value"] = str(build.parent)
            with self.assertRaises(ContractError):
                replay.validate_cases(discovery, "cmocka", build)
            tests.pop(0)
            with self.assertRaises(ContractError):
                replay.validate_cases(discovery, "cmocka", build)

    def test_only_known_empty_wrap_path_is_repaired_from_same_upstream_helper(self):
        tests = [{"name": name, "command": [name + ".exe"],
                  "properties": [{"name": "WORKING_DIRECTORY", "value": "private"},
                                 {"name": "ENVIRONMENT", "value": [path]}]}
                 for name, path in (("simple_test", "PATH=C:\\private\\build\\src;C:\\private\\runtime"),
                                    ("waiter_test_wrap", "PATH="))]
        discovery = {"kind": "ctestInfo", "version": {"major": 1}, "tests": tests}
        repaired = replay.repair_cmocka_wrap_environment(discovery)
        self.assertEqual(repaired["tests"][1]["command"], tests[1]["command"])
        self.assertEqual(repaired["tests"][1]["properties"][1]["value"], tests[0]["properties"][1]["value"])
        self.assertEqual(tests[1]["properties"][1]["value"], ["PATH="])
        tests[1]["properties"][1]["value"] = ["PATH=unrelated"]
        with self.assertRaises(ContractError):
            replay.repair_cmocka_wrap_environment(discovery)


if __name__ == "__main__":
    unittest.main()
