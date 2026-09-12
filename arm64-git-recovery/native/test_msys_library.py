import importlib.util
from contextlib import ExitStack, redirect_stderr
import io
import json
import os
from pathlib import Path
import re
import shutil
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

from sources import ContractError

spec = importlib.util.spec_from_file_location("msys_library", Path(__file__).with_name("build-msys-library.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MsysLibraryControls(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ.get("SSH_TEST_ROOT", ".ssh-test-work")) / str(uuid.uuid4())
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def args(self):
        return SimpleNamespace(
            package="libxcrypt", source=self.root / "source", manifest=self.root / "source.json",
            prefix=self.root / "compiler", compiler_receipt=self.root / "compiler.json",
            compiler_receipt_sha256="a" * 64, bootstrap=self.root / "bootstrap",
            bootstrap_receipt=self.root / "bootstrap.copy.json", output=self.root / "output",
            jobs=1, native_job_prefix=self.root / "observer", dependency_stage=None, dependency_manifest=None,
            documentation_driver=None, documentation_manifest=None,
        )

    def test_xz_keeps_full_cli_library_and_documentation_payload(self):
        module.validate_source("xz-msys", {
            "source": {"id": "xz", "version": "5.8.3"},
            "libtool_dependency": {"manifest_sha256": "0" * 64},
            "build_policy": {"windows_doxygen_paths": True},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})
        for name in ("bin/msys-lzma-5.dll", "bin/xz.exe", "lib/liblzma.a",
                     "lib/liblzma.dll.a", "share/doc/xz/api/index.html"):
            self.assertIn(name, module.PROFILES["xz-msys"]["required"])

    def test_xz_cannot_use_iconv_without_native_gettext(self):
        files = {name: {} for name in ("usr/include/iconv.h", "usr/lib/libiconv.dll.a",
                                      "usr/bin/msys-iconv-2.dll")}
        with self.assertRaises(ContractError):
            module.validate_dependency("xz-msys", files)
        files.update({name: {} for name in ("usr/include/libintl.h", "usr/lib/libintl.dll.a",
                                           "usr/bin/libintl-8.dll")})
        with self.assertRaises(ContractError):
            module.validate_dependency("xz-msys", files)
        files["usr/bin/msys-intl-8.dll"] = {}
        module.validate_dependency("xz-msys", files)

    def test_unpatched_xz_documentation_source_is_rejected(self):
        for policy in (None, {}, {"windows_doxygen_paths": False}):
            record = {"source": {"id": "xz", "version": "5.8.3"},
                      "libtool_dependency": {"manifest_sha256": "0" * 64},
                      "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes",
                      "build_policy": policy}
            with self.subTest(policy=policy), self.assertRaises(ContractError):
                module.validate_source("xz-msys", record)

    def test_gettext_requires_same_abi_iconv_payload(self):
        with self.assertRaises(ContractError):
            module.validate_dependency("gettext-msys", {})
        files = {name: {} for name in ("usr/include/iconv.h", "usr/lib/libiconv.dll.a",
                                      "usr/bin/libiconv-2.dll")}
        with self.assertRaises(ContractError):
            module.validate_dependency("gettext-msys", files)
        files["usr/bin/msys-iconv-2.dll"] = {}
        module.validate_dependency("gettext-msys", files)

    def test_zlib_uses_its_pinned_nonlibtool_build(self):
        module.validate_source("zlib-msys", {
            "source": {"id": "zlib", "version": "1.3.2"},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})
        self.assertIn("bin/msys-z.dll", module.PROFILES["zlib-msys"]["required"])

    def test_prepared_native_msys_input(self):
        module.validate_source("libxcrypt", {
            "source": {"id": "libxcrypt", "version": "4.5.2"},
            "libtool_dependency": {"manifest_sha256": "0" * 64},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})

    def test_raw_mingw_source_does_not_substitute(self):
        with self.assertRaises(ContractError):
            module.validate_source("libiconv-bootstrap", {"source": {"id": "libiconv", "version": "1.19"}})

    def test_wrong_package_version_is_rejected(self):
        with self.assertRaises(ContractError):
            module.validate_source("libxcrypt", {
                "source": {"id": "libxcrypt", "version": "4.4.0"},
                "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})

    def test_iconv_bootstrap_omission_is_explicit(self):
        self.assertIn("NLS explicitly disabled", module.PROFILES["libiconv-bootstrap"]["limitations"][0])

    def test_stock_generator_preparation_is_rejected(self):
        with self.assertRaisesRegex(ContractError, "bound MSYS-aware generator"):
            module.validate_source("libxcrypt", {
                "source": {"id": "libxcrypt", "version": "4.5.2"},
                "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})

    def test_exact_bootstrap_and_observer_metadata_required(self):
        args = self.args()
        good = {"status": "private-ssh-bootstrap-byte-identical-not-executed", "prefix": str(args.bootstrap),
                "source_unchanged": True, "complete_inventory_equality": True,
                "target_or_bootstrap_processes_launched": 0}
        module.validate_bootstrap(good, args.bootstrap)
        for key, value in (("status", "unsealed"), ("source_unchanged", False),
                           ("complete_inventory_equality", False), ("prefix", str(args.prefix))):
            with self.subTest(key=key), self.assertRaises(ContractError):
                module.validate_bootstrap({**good, key: value}, args.bootstrap)
        observer = {"status": "byte-identical-native-test-driver",
                    "source_handoff_sha256": module.OBSERVER_HANDOFF_SHA256,
                    "files": {name: {} for name in ("native-job.py", "native-target-exec.py", "native-target-exec.sh")}}
        module.validate_observer(observer)
        with self.assertRaises(ContractError):
            module.validate_observer({**observer, "source_handoff_sha256": "0" * 64})
        with self.assertRaises(ContractError):
            module.validate_observer({**observer, "files": {**observer["files"], "old-observer.py": {}}})

    def test_parent_adapter_identity_is_bound_for_future_launches(self):
        self.assertEqual(module.digest(module.OBSERVER_ADAPTER_PATH), module.LOADED_OBSERVER_ADAPTER_SHA256)
        with mock.patch.object(module, "digest", return_value="0" * 64), self.assertRaises(ContractError):
            module.require_seal(module.OBSERVER_ADAPTER_PATH, module.LOADED_OBSERVER_ADAPTER_SHA256,
                                "Loaded parent observer adapter")

    def test_wrong_new_compiler_seal_stops_before_any_execution(self):
        args = self.args()
        args.compiler_receipt.write_text("{}", encoding="utf-8")
        with mock.patch.object(module, "require_memory", return_value=16), \
                mock.patch.object(module, "support_identities") as compiler, \
                mock.patch.object(module, "run_observed") as observer:
            with self.assertRaisesRegex(ContractError, "compiler receipt.*seal differs"):
                module.build(args)
        compiler.assert_not_called()
        observer.assert_not_called()
        self.assertFalse(args.output.exists())

    def test_retired_compiler_is_never_launched(self):
        args = self.args()
        args.compiler_receipt_sha256 = next(iter(module.RETIRED_COMPILER_RECEIPTS))
        with mock.patch.object(module, "require_memory", return_value=16), \
                mock.patch.object(module, "require_seal"), \
                mock.patch.object(module, "support_identities") as compiler:
            with self.assertRaisesRegex(ContractError, "Historical compiler receipts"):
                module.build(args)
        compiler.assert_not_called()
        self.assertFalse(args.output.exists())

    def test_cc1_fix_hash_is_required_before_preprocessing(self):
        module.require_approved_cc1({"cc1": {"sha256": module.APPROVED_CC1_SHA256}})
        for support in ({}, {"cc1": None}, {"cc1": {"sha256": "0" * 64}}):
            with self.subTest(support=support), self.assertRaises(ContractError):
                module.require_approved_cc1(support)
        source = Path(__file__).with_name("build-msys-library.py").read_text()
        self.assertLess(source.index("require_approved_cc1(support)\n"),
                        source.index("definitions = subprocess.run"))

    def test_stack_guard_reference_filter_is_exact_not_a_public_symbol_waiver(self):
        patch = Path(__file__).parent / "patches/libxcrypt-coff-stack-guard-refptr-test.patch"
        self.assertEqual(module.digest(patch), module.LIBXCRYPT_GUARD_TEST_PATCH_SHA256)
        added = next(line for line in patch.read_text().splitlines() if line.startswith("+        sub"))
        expression = added.split("!~ /", 1)[1].split("/ },", 1)[0]
        for name in (".refptr.__stack_chk_guard", ".refptr._crypt_private", "_crypt_private", "__implementation"):
            with self.subTest(private=name):
                self.assertRegex(name, expression)
        for name in ("crypt_r", "crypt_ra", ".refptr.__stack_chk_guard_public", ".refptr.public_api",
                     "prefix.refptr.__stack_chk_guard", "_Zpublic_cpp"):
            with self.subTest(public=name):
                self.assertIsNone(re.search(expression, name))

    def test_only_symbol_test_source_change_is_allowed(self):
        source = {"files": {module.LIBXCRYPT_SYMBOL_TEST: module.LIBXCRYPT_SYMBOL_TEST_BEFORE,
                            "lib/crypt.c": {"sha256": "a" * 64, "size": 1}}}
        module.libxcrypt_test_customization(source)
        expected = {**source["files"], module.LIBXCRYPT_SYMBOL_TEST: module.LIBXCRYPT_SYMBOL_TEST_AFTER}
        with mock.patch.object(module, "inventory", return_value=expected):
            module.verify_libxcrypt_working_source(self.root, source)
        with mock.patch.object(module, "inventory", return_value={
                **expected, "lib/crypt.c": {"sha256": "b" * 64, "size": 1}}):
            with self.assertRaises(ContractError):
                module.verify_libxcrypt_working_source(self.root, source)
        with self.assertRaises(ContractError):
            module.libxcrypt_test_customization({"files": {}})

    def test_owned_environment_excludes_inherited_flags_and_caches(self):
        args = self.args()
        with mock.patch.dict(os.environ, {"CC": "unapproved", "LIBRARY_PATH": "old",
                                          "MAKEFLAGS": "-j8", "TEMP": "old-cache"}):
            env = module.launch_environment(args)
        self.assertNotIn("CC", env)
        self.assertNotIn("LIBRARY_PATH", env)
        self.assertEqual(env["MAKEFLAGS"], "-j1")
        self.assertEqual(env["OMP_NUM_THREADS"], "1")
        self.assertEqual(env["WOARM64_NATIVE_ARG_CONVERSION"], "none")
        self.assertEqual(env["CCACHE_DISABLE"], "1")
        for name in ("TEMP", "TMP", "HOME", "XDG_CACHE_HOME", "CCACHE_DIR"):
            self.assertTrue(Path(env[name]).is_relative_to(args.output.resolve()))

    def test_output_reuse_overlap_and_evidence_reuse_rejected(self):
        args = self.args()
        module.validate_output(args.output, [args.source])
        with self.assertRaises(ContractError):
            module.validate_output(args.source / "nested", [args.source])
        args.output.with_name(args.output.name + ".native-job.stdout").write_text("old", encoding="utf-8")
        with self.assertRaises(ContractError):
            module.validate_output(args.output, [args.source])

    def test_cli_enforces_jobs_one(self):
        argv = ["--package", "libxcrypt"]
        for name in ("source", "manifest", "prefix", "compiler-receipt", "bootstrap", "bootstrap-receipt",
                     "output", "native-job-prefix"):
            argv += ["--" + name, "example"]
        argv += ["--compiler-receipt-sha256", "a" * 64, "--jobs", "1"]
        self.assertEqual(module.parse_args(argv).jobs, 1)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            module.parse_args(argv[:-1] + ["2"])

    @staticmethod
    def summary():
        return "# TOTAL: 54\n# PASS: 53\n# SKIP: 1\n# XFAIL: 0\n# FAIL: 0\n# XPASS: 0\n# ERROR: 0\n"

    def test_full_upstream_suite_and_failures_are_not_waived(self):
        path = self.root / "test-suite.log"
        path.write_text(self.summary(), encoding="utf-8")
        result = module.libxcrypt_summary(path)
        self.assertEqual(result["counts"]["TOTAL"], 54)
        for text in (self.summary().replace("TOTAL: 54", "TOTAL: 53"),
                     self.summary().replace("PASS: 53", "PASS: 52").replace("FAIL: 0", "FAIL: 1"),
                     self.summary().replace("PASS: 53", "PASS: 0").replace("SKIP: 1", "SKIP: 54"),
                     self.summary() + "# PASS: 53\n"):
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ContractError):
                module.libxcrypt_summary(path)

    def test_shell_keeps_protections_all_hashes_and_observed_check(self):
        shell = Path(__file__).with_name("build-msys-library.sh").read_text()
        dispatcher = Path(__file__).with_name("native-msys-test-dispatch.sh").read_text()
        for fragment in ("--enable-hashes=all", "--enable-static --enable-shared", "-fstack-protector-strong",
                         'LOG_COMPILER=/usr/bin/bash $dispatcher', "CONFIG_SITE=/dev/null", "MAKEFLAGS=-j1",
                         "--cache-file=$output/cache/config.cache"):
            self.assertIn(fragment, shell)
        self.assertNotIn("-fno-stack-protector", shell)
        self.assertNotIn("check ||", shell)
        self.assertIn("WOARM64_NATIVE_ARG_CONVERSION:-} == none", dispatcher)
        self.assertIn('exec /usr/bin/bash "$driver/native-target-exec.sh" "$@"', dispatcher)
        self.assertIn('[[ -f "$toolchain/bin/msys-2.0.dll" && -f "$PWD/.libs/msys-crypt-2.dll" ]]', shell)
        self.assertIn('export PATH="$PWD/.libs:$toolchain/bin:/usr/bin"', shell)
        self.assertIn('"$output/native-test-path.txt"', shell)

    def run_mock_build(self, passed):
        args = self.args()
        for path in (args.source, args.prefix, args.bootstrap, args.native_job_prefix):
            path.mkdir()
        args.manifest.write_text(json.dumps({
            "source": {"id": "libxcrypt", "version": "4.5.2"},
            "libtool_dependency": {"manifest_sha256": "0" * 64},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes",
            "files": {module.LIBXCRYPT_SYMBOL_TEST: module.LIBXCRYPT_SYMBOL_TEST_BEFORE},
        }), encoding="utf-8")
        args.compiler_receipt.write_text(json.dumps({
            "prefix": str(args.prefix),
            "source_target": {"DataModel": "LP64", "Triple": "aarch64-pc-cygwin",
                              "Profile": "MSYS", "ThreadModel": "posix"},
        }), encoding="utf-8")
        args.bootstrap_receipt.write_text(json.dumps({
            "status": "private-ssh-bootstrap-byte-identical-not-executed", "prefix": str(args.bootstrap),
            "source_unchanged": True, "complete_inventory_equality": True,
            "target_or_bootstrap_processes_launched": 0, "directories": [],
        }), encoding="utf-8")
        driver_manifest = args.native_job_prefix.with_name("observer.manifest.json")
        driver_manifest.write_text(json.dumps({
            "status": "byte-identical-native-test-driver", "source_handoff_sha256": module.OBSERVER_HANDOFF_SHA256,
            "files": {name: {} for name in ("native-job.py", "native-target-exec.py", "native-target-exec.sh")},
        }), encoding="utf-8")

        def observed(command, **kwargs):
            self.assertEqual(kwargs["env"]["WOARM64_NATIVE_ARG_CONVERSION"], "none")
            self.assertEqual(kwargs["env"]["MAKEFLAGS"], "-j1")
            self.assertEqual(kwargs["driver_prefix"], args.native_job_prefix)
            self.assertEqual(kwargs["cwd"], args.output.resolve().parent)
            self.assertTrue(Path(command[0]).is_absolute())
            for name in ("log_path", "result_path", "relay_records"):
                self.assertTrue(kwargs[name].is_absolute())
            self.assertTrue((args.output / "launch-inputs.json").is_file())
            self.assertEqual(command[-1], "1")
            if passed:
                (args.output / "build").mkdir()
                (args.output / "build/test-suite.log").write_text(self.summary(), encoding="utf-8")
                for name in module.PROFILES["libxcrypt"]["required"]:
                    path = args.output / "stage/usr" / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"mock output only; not an executable")
            return {"passed": passed}

        with ExitStack() as stack:
            for name in ("require_seal", "verify_tree", "validate_preparation", "require_msys_ucontext_receipt",
                         "validate_abi", "verify_support", "verify_libxcrypt_working_source"):
                stack.enter_context(mock.patch.object(module, name))
            stack.enter_context(mock.patch.object(module, "verify_driver", return_value=driver_manifest))
            stack.enter_context(mock.patch.object(module, "require_memory", return_value=16))
            stack.enter_context(mock.patch.object(
                module, "support_identities", return_value={"cc1": {"sha256": module.APPROVED_CC1_SHA256}}))
            stack.enter_context(mock.patch.object(module, "verify_msys_jmp_headers", return_value={"unit": "mock"}))
            native_probe = stack.enter_context(mock.patch.object(
                module.subprocess, "run", return_value=SimpleNamespace(stdout=b"#define __aarch64__ 1\n")))
            runner = stack.enter_context(mock.patch.object(module, "run_observed", side_effect=observed))
            stack.enter_context(mock.patch("builtins.print"))
            if passed:
                report = module.build(args)
                self.assertEqual(report["status"], "native-msys-library-built-checked-bootstrap-driver")
                self.assertEqual(report["upstream_tests"]["counts"]["TOTAL"], 54)
                self.assertEqual(report["input_integrity_errors"], [])
                self.assertEqual(report["observer_adapter"]["source_sha256_at_import"],
                                 module.LOADED_OBSERVER_ADAPTER_SHA256)
                self.assertFalse(report["observer_adapter"]["file_changed_after_import"])
            else:
                with self.assertRaisesRegex(ContractError, "build/check failed"):
                    module.build(args)
                report = json.loads(args.output.with_name("output.result.json").read_text())
                self.assertEqual(report["status"], "failed")
            runner.assert_called_once()
            native_probe.assert_called_once()

    def test_real_launcher_flow_reaches_observer_with_mocked_native_execution(self):
        self.run_mock_build(True)

    def test_observer_failure_never_admits_stage(self):
        self.run_mock_build(False)


if __name__ == "__main__":
    unittest.main()
