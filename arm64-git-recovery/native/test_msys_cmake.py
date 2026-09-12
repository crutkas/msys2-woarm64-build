import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sources import ContractError, inventory

spec = importlib.util.spec_from_file_location("msys_cmake", Path(__file__).with_name("build-msys-cmake.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MsysCmakeControls(unittest.TestCase):
    def test_fido_keeps_features_but_rejects_device_test_install_mode(self):
        flags = module.PROFILES["libfido2"]["flags"]
        for name in ("USE_WINHELLO", "BUILD_TESTS", "BUILD_TOOLS", "BUILD_EXAMPLES", "BUILD_MANPAGES",
                     "BUILD_SHARED_LIBS", "BUILD_STATIC_LIBS"):
            self.assertEqual(flags[name], "ON")
        self.assertTrue(module.require_fido_mode("libfido2", True, Path("inputs"), "1" * 64, None))
        for build_only, manifest, sha, stage in ((False, Path("inputs"), "1" * 64, None),
                                                (True, None, None, None),
                                                (True, Path("inputs"), "1" * 64, Path("installed"))):
            with self.assertRaises(ContractError):
                module.require_fido_mode("libfido2", build_only, manifest, sha, stage)

    def test_fido_feature_proof_comes_from_actual_compile_commands(self):
        commands = [{"file": name, "command": "gcc -DUSE_WINHELLO -D_WIN32_WINNT=0x0600 -std=c99"}
                    for name in ("winhello.c", "hid_win.c")]
        self.assertEqual(module.verify_fido_features(commands)["windows_sources"], ["hid_win.c", "winhello.c"])
        with self.assertRaises(ContractError):
            module.verify_fido_features(commands[:1])
        commands[0]["command"] += " -D_WIN32"
        with self.assertRaises(ContractError):
            module.verify_fido_features(commands)

    def test_build_only_cannot_be_mistaken_for_observed_test_mode(self):
        self.assertIsNone(module.require_test_observer(True, None))
        with self.assertRaises(ContractError):
            module.require_test_observer(False, None)
        with self.assertRaises(ContractError):
            module.require_test_observer(True, Path("retired-or-unneeded-observer"))

    def test_ctest_always_uses_child_observation_and_preserves_failure(self):
        root = Path("owned-cmake-output").resolve()
        driver = Path("qualified-native-driver").resolve()
        env = {"WOARM64_NATIVE_TEST_ROOT": str(root)}
        failure = {"passed": False, "exit": 0}
        with patch.object(module, "run_observed", return_value=failure) as observed:
            with patch.object(module, "run") as parent_only:
                result = module.execute_stage("ctest", ["ctest.exe", "--test-dir", root / "build"],
                                              output=root, env=env, native_job_prefix=driver)
        self.assertIs(result, failure)
        parent_only.assert_not_called()
        self.assertEqual(observed.call_args.kwargs["driver_prefix"], driver)
        self.assertEqual(observed.call_args.kwargs["relay_records"], root / "native-exits")
        self.assertEqual(observed.call_args.kwargs["result_path"], root / "ctest.native-job.json")
        self.assertEqual(observed.call_args.kwargs["env"], env)

    @unittest.skipUnless(os.environ.get("NATIVE_TEST_CMAKE") and os.environ.get("NATIVE_TEST_NINJA"),
                         "Explicit existing native CMake/Ninja paths are required for the host-only staging control")
    def test_real_msys_staging_never_installs_into_global_usr(self):
        source = Path(__file__).parent / "fixtures/cmake-msys-staging"
        with tempfile.TemporaryDirectory(prefix="msys-cmake-staging-") as directory:
            root = Path(directory)
            build, stage = root / "build", root / "stage/usr"
            cmake, ninja = os.environ["NATIVE_TEST_CMAKE"], os.environ["NATIVE_TEST_NINJA"]
            result = subprocess.run([cmake, "-S", str(source), "-B", str(build), "-G", "Ninja",
                                     f"-DCMAKE_MAKE_PROGRAM={Path(ninja).as_posix()}",
                                     "-DCMAKE_SYSTEM_NAME=MSYS", "-DCMAKE_INSTALL_PREFIX=/usr",
                                     f"-DCMAKE_STAGING_PREFIX={stage.as_posix()}"],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            install_script = (build / "cmake_install.cmake").read_text()
            self.assertIn(f'set(CMAKE_INSTALL_PREFIX "{stage.as_posix()}")', install_script)
            result = subprocess.run([cmake, "--install", str(build)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((stage / "share/staging-control/payload.txt").read_bytes(),
                             (source / "payload.txt").read_bytes())

    def test_cbor_requires_real_msys_test_dependency(self):
        with self.assertRaises(ContractError):
            module.validate_dependency("libcbor", {})
        files = {name: {} for name in ("usr/include/cmocka.h", "usr/lib/libcmocka.dll.a")}
        with self.assertRaises(ContractError):
            module.validate_dependency("libcbor", files)
        files["usr/bin/msys-cmocka-0.dll"] = {}
        module.validate_dependency("libcbor", files)

    def test_requested_profiles_keep_tests_and_required_features(self):
        self.assertEqual(module.PROFILES["libcbor"]["flags"]["WITH_TESTS"], "ON")
        self.assertNotIn("CBOR_CUSTOM_ALLOC", module.PROFILES["libcbor"]["flags"])
        self.assertIn("cbor_set_allocs", module.PROFILES["libcbor"]["required_exports"]["src/msys-cbor-0.14.dll"])
        self.assertEqual(module.PROFILES["cmocka"]["flags"]["UNIT_TESTING"], "ON")
        self.assertEqual(module.PROFILES["cmocka"]["flags"]["CMOCKA_SOURCE_COMPILE_DATABASE"], "OFF")
        self.assertEqual(module.PROFILES["zstd"]["flags"]["ZSTD_PROGRAMS_LINK_SHARED"], "ON")
        self.assertEqual(module.PROFILES["zstd"]["flags"]["ZSTD_BUILD_PROGRAMS"], "ON")

    def test_zstd_cannot_silently_lose_shell_test_prerequisites(self):
        with self.assertRaises(ContractError):
            module.verify_bootstrap("zstd", None, None)
        with tempfile.TemporaryDirectory(prefix="zstd-private-bootstrap-") as directory:
            root = Path(directory)
            prefix, manifest = root / "bootstrap", root / "bootstrap.copy.json"
            (prefix / "usr/bin").mkdir(parents=True)
            for name in ("bash", "sh", "uname"):
                (prefix / f"usr/bin/{name}.exe").write_bytes(b"unexecuted unit fixture")
            record = {"status": "private-emulated-build-input-copy", "prefix": str(prefix.resolve()),
                      "source_handoff_sha256": "1" * 64, "files": inventory(prefix)}
            manifest.write_text(json.dumps(record))
            qualification = module.verify_bootstrap("zstd", prefix, manifest)
            self.assertIn("x64 emulated", qualification["scope"])
            for package in ("cmocka", "libcbor"):
                self.assertIsNone(module.verify_bootstrap(package, None, None))
                with self.assertRaises(ContractError):
                    module.verify_bootstrap(package, prefix, manifest)
            (prefix / "usr/bin/uname.exe").unlink()
            record["files"] = inventory(prefix)
            manifest.write_text(json.dumps(record))
            with self.assertRaisesRegex(ContractError, "uname"):
                module.verify_bootstrap("zstd", prefix, manifest)

    def test_changed_private_shell_driver_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="zstd-private-bootstrap-drift-") as directory:
            root = Path(directory)
            prefix, manifest = root / "bootstrap", root / "bootstrap.copy.json"
            (prefix / "usr/bin").mkdir(parents=True)
            for name in ("bash", "sh", "uname"):
                (prefix / f"usr/bin/{name}.exe").write_bytes(b"unexecuted unit fixture")
            record = {"status": "private-emulated-build-input-copy", "prefix": str(prefix.resolve()),
                      "source_handoff_sha256": "1" * 64, "files": inventory(prefix)}
            manifest.write_text(json.dumps(record))
            (prefix / "usr/bin/bash.exe").write_bytes(b"changed")
            with self.assertRaises(ContractError):
                module.verify_bootstrap("zstd", prefix, manifest)

    def test_empty_failed_and_unreviewed_skipped_tests_rejected(self):
        with tempfile.TemporaryDirectory(prefix="msys-ctest-control-") as directory:
            report = Path(directory) / "ctest.xml"
            for content in ('<testsuite/>', '<testsuite><testcase name="x"><failure/></testcase></testsuite>',
                            '<testsuite><testcase name="x"><skipped/></testcase></testsuite>'):
                report.write_text(content)
                with self.assertRaises(ContractError):
                    module.test_results(report)
            report.write_text('<testsuite><testcase name="real"/></testsuite>')
            self.assertEqual(module.test_results(report), ["real"])


if __name__ == "__main__":
    unittest.main()
