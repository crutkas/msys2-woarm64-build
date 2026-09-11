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

    def test_db_keeps_full_recipe_payload_and_separate_test_gate(self):
        module.validate_source("db-msys", {
            "source": {"id": "db", "version": "6.2.32"},
            "libtool_dependency": {"manifest_sha256": "0" * 64},
            "dependency_abi": "MSYS runtime; MinGW/UCRT libraries are not substitutes"})
        for name in ("bin/msys-db_cxx-6.2.dll", "include/db_185.h", "include/db_cxx.h",
                     "lib/libdb.a", "lib/libdb_cxx.dll.a", "share/doc/db/html/index.html"):
            self.assertIn(name, module.PROFILES["db-msys"]["required"])
        shell = Path(__file__).with_name("build-msys-library.sh").read_text()
        for flag in ("--enable-compat185", "--enable-cxx", "--enable-dbm", "--enable-dynamic",
                     "docdir=/usr/share/doc/db/html"):
            self.assertIn(flag, shell)
        self.assertIn("native-msys-library-built-upstream-checks-pending",
                      Path(__file__).with_name("build-msys-library.py").read_text())

    def test_db_rejects_blanket_or_missing_cpp_qualification(self):
        from db_build_inputs import CPP_FRONTEND_SEAL, require_db_cpp_receipt
        name = "libexec/gcc/aarch64-pc-cygwin/15.0.1/cc1plus.exe"
        good = {"full_cpp_qualified": False, "files": {name: {"sha256": CPP_FRONTEND_SEAL}},
                "source_cpp_frontend_delta": {"changed_files": [name], "qualification": {
                    "normal_guard_raw_exit": 0, "matrix_runs": 7, "real_canary_failure_raw_exits": [1536, 1536]}}}
        require_db_cpp_receipt(good)
        for bad in ({}, {**good, "full_cpp_qualified": True}, {**good, "files": {}}):
            with self.assertRaises(ContractError):
                require_db_cpp_receipt(bad)

    def test_db_installed_raw_exit_requires_complete_current_generation(self):
        from db_native_checks import require_exit
        exe = self.root / "consumer.exe"
        event = {"executable": str(exe.resolve()), "created": 123456789, "raw_exit": 0}
        row = {"process": {"timed_out": False}, "evidence": {
            "native_target_exits": [event], "created_processes": 2, "observed_processes": 2}}
        self.assertEqual(require_exit(row, exe), event)
        for changed in (
            {**row["evidence"], "observed_processes": 1},
            {**row["evidence"], "native_target_exits": [{**event, "raw_exit": 1536}]},
            {**row["evidence"], "native_target_exits": [{**event, "created": 0}]},
            {**row["evidence"], "native_target_exits": [event, event]},
        ):
            with self.assertRaises(ContractError):
                require_exit({**row, "evidence": changed}, exe)

    def test_db_check_environment_preserves_pathext_but_not_user_flags(self):
        from db_native_checks import environment
        with mock.patch.dict(os.environ, {"CC": "old", "MAKEFLAGS": "-j64"}):
            env = environment(self.root / "prefix", self.root / "output")
        self.assertEqual(env["MAKEFLAGS"], "-j1")
        self.assertEqual(env["PATHEXT"], os.environ["PATHEXT"])
        self.assertNotIn("CC", env)
        self.assertEqual(env["WOARM64_NATIVE_ARG_CONVERSION"], "none")

    def test_db_detector_patch_does_not_force_private_mutexes_or_fake_macros(self):
        from db_build_inputs import MUTEX_PATCH_SEAL
        patch = Path(__file__).parent / "patches/db-6.2.32-aarch64-mutex-detection.patch"
        self.assertEqual(module.digest(patch), MUTEX_PATCH_SEAL)
        added = [line for line in patch.read_text().splitlines() if line.startswith("+") and not line.startswith("+++")]
        self.assertEqual(added, ["+#if (defined(__arm64__) || defined(__aarch64__)) && defined(__GNUC__)"] * 2)
        shell = Path(__file__).with_name("build-msys-library.sh").read_text()
        self.assertNotIn("--enable-posixmutexes", shell)
        self.assertNotIn("-D__arm64__", shell)

    def test_db_upstream_cxx_relay_preserves_golden_checks_and_fails_nonzero(self):
        from db_native_checks import CXX_RELAY_PATCH_SEAL
        patch = Path(__file__).parent / "patches/db-6.2.32-cxx-test-relay.patch"
        self.assertEqual(module.digest(patch), CXX_RELAY_PATCH_SEAL)
        text = patch.read_text()
        self.assertIn('cygpath -am "./$name.exe"', text)
        self.assertIn('error "native process $name failed"', text)
        self.assertNotIn("-\tcompare_result", text)
        self.assertNotIn("-\tdiff ", text)

    def test_db_native_libtool_fix_keeps_dependency_checks_and_preflights_both_tags(self):
        from db_build_inputs import LIBTOOL_PATH_PATCH_SEAL
        patch = Path(__file__).parent / "patches/db-6.2.32-native-libtool-paths.patch"
        self.assertEqual(module.digest(patch), LIBTOOL_PATH_PATCH_SEAL)
        self.assertNotIn("pass_all", patch.read_text())
        shell = Path(__file__).with_name("build-msys-library.sh").read_text()
        self.assertIn("for tag in c cxx", shell)
        self.assertIn('-no-undefined -rpath /usr/lib', shell)
        self.assertIn('"db-path-probe-$tag.lo" -lpthread', shell)

    def test_debug_capture_separator_is_not_passed_to_the_native_target(self):
        spec = importlib.util.spec_from_file_location(
            "db_capture_control", Path(__file__).with_name("capture-native-exception.py"))
        capture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(capture)
        argv = ["capture", "--executable", "cutest.exe", "--output", "out", "--", "-s", "TestQueue"]
        with mock.patch("sys.argv", argv), mock.patch.object(capture, "capture") as runner:
            capture.main()
        self.assertEqual(runner.call_args.args[1], ["-s", "TestQueue"])

    def test_queue_region_adaptation_does_not_remove_operations_or_assertions(self):
        from db_native_checks import QUEUE_PATCH_SEAL
        patch = Path(__file__).parent / "patches/db-6.2.32-queue-test-shared-region.patch"
        self.assertEqual(module.digest(patch), QUEUE_PATCH_SEAL)
        removed = "\n".join(line for line in patch.read_text().splitlines()
                            if line.startswith("-") and not line.startswith("---"))
        for fragment in ("CuAssert", "f_verify", "case ", "ops[]", "SH_LIST_", "SH_TAILQ_"):
            self.assertNotIn(fragment, removed)
        self.assertIn("QUEUE_REGION_BYTES", patch.read_text())

    def test_resumed_mutex_matrix_keeps_all_upstream_cases_and_load(self):
        from db_channel_checks import expected_mutex_matrix
        matrix = expected_mutex_matrix()
        self.assertEqual(len(matrix), 24)
        self.assertEqual(len(set(matrix)), 24)
        self.assertIn((4, 4, 128, 2000), matrix)
        self.assertEqual({row[2] for row in matrix}, {32, 64, 128})
        self.assertEqual({row[3] for row in matrix}, {2000})
        self.assertNotIn((1, 1, 32, 2000), matrix)

    def test_channel_transition_patch_keeps_message_assertions_and_bounds_promotion(self):
        from db_channel_checks import CHANNEL_PATCH_SHA
        patch = Path(__file__).parent / "patches/db-6.2.32-channel-master-transition.patch"
        self.assertEqual(module.digest(patch), CHANNEL_PATCH_SHA)
        text = patch.read_text()
        removed = "\n".join(line for line in text.splitlines() if line.startswith("-"))
        for operation in ("send_msg", "send_request", "check_dbt_string"):
            self.assertNotIn(operation, removed)
        for fragment in ("become_master(dbenv3)", "become_master(dbenv2)",
                         "await_condition(try_master, &transition, 60)",
                         "stats->st_master == stats->st_env_id", "return (DB_TIMEOUT)"):
            self.assertIn(fragment, text)

    def test_resumed_mutex_cannot_substitute_x64_bootstrap_or_new_runtime(self):
        from db_channel_checks import require_mutex_driver
        with self.assertRaisesRegex(ContractError, "native /bin/sh"):
            require_mutex_driver(None, None, None, "a" * 64)
        record = {"files": {name: {"sha256": "b" * 64} for name in
                  ("bin/sh.exe", "bin/rm.exe", "bin/mkdir.exe", "bin/msys-2.0.dll")}}
        with mock.patch("db_channel_checks.sealed_json", return_value=record), \
                mock.patch("db_channel_checks.verify_tree"), mock.patch("db_channel_checks.arm64_pe"):
            with self.assertRaisesRegex(ContractError, "separately qualified coherent DB cohort"):
                require_mutex_driver(self.root, self.root / "manifest.json", "c" * 64, "a" * 64)
            record["files"]["bin/msys-2.0.dll"]["sha256"] = "a" * 64
            self.assertEqual(require_mutex_driver(self.root, self.root / "manifest.json", "c" * 64, "a" * 64), record)

    def test_sqlite_driver_adoption_requires_exact_runtime_and_real_tmp(self):
        from db_native_driver import D70_SHA, FSTAB_SHA, validate_shell_record
        files = {f"fixture/{index}": {"sha256": "a" * 64, "size": 1} for index in range(8863)}
        files.update({name: {"sha256": sha, "size": 1} for name, sha in {
            "usr/bin/sh.exe": "6d76e238226f02579efad941e4e021ee5aea614b8a54bb6750f572f4acb62512",
            "usr/bin/rm.exe": "ce6b95b18aae78614e7e3c01b8979443a28a7dcd800f28af60971bb3ef5f5915",
            "usr/bin/mkdir.exe": "2768035ab6b0c14454d576c0c734259e755b7128bd9ddfabdfe01e705a14b584",
            "usr/bin/msys-2.0.dll": D70_SHA, "etc/fstab": FSTAB_SHA}.items()})
        record = {"runtime": {"files": files}, "required_runtime_directories": ["tmp"]}
        self.assertEqual(validate_shell_record(record), files)
        with self.assertRaises(ContractError):
            validate_shell_record({**record, "required_runtime_directories": []})
        files["usr/bin/msys-2.0.dll"]["sha256"] = "0" * 64
        with self.assertRaises(ContractError):
            validate_shell_record(record)

    def test_new_driver_epoch_requires_successful_exact_db_process_preflight(self):
        from db_channel_checks import HANDOFF_SHA, require_mutex_driver
        from db_native_driver import D70_SHA
        (self.root / "tmp").mkdir()
        files = {f"usr/bin/{name}": {"sha256": D70_SHA} for name in ("sh.exe", "rm.exe", "mkdir.exe", "msys-2.0.dll")}
        record = {"files": files, "required_runtime_directories": ["tmp"]}
        good = {"status": "private-native-db-d70-shell-process-api-preflight-passed",
                "inputs_unchanged": True, "base_db_handoff_sha256": HANDOFF_SHA,
                "runtime_manifest": {"sha256": "c" * 64}, "runtime_sha256": D70_SHA,
                "commands": {name: {"process": {"passed": True}} for name in ("c", "compat185", "process", "cpp-held")}}
        for qualified in (good, {**good, "inputs_unchanged": False}, {**good, "commands": {}}):
            with mock.patch("db_channel_checks.sealed_json", side_effect=[record, qualified]), \
                    mock.patch("db_channel_checks.verify_tree"), mock.patch("db_channel_checks.arm64_pe"):
                if qualified == good:
                    self.assertEqual(require_mutex_driver(self.root, self.root / "manifest.json", "c" * 64,
                        "a" * 64, self.root / "qualified.json", "b" * 64), record)
                else:
                    with self.assertRaises(ContractError):
                        require_mutex_driver(self.root, self.root / "manifest.json", "c" * 64,
                            "a" * 64, self.root / "qualified.json", "b" * 64)

    @unittest.skipUnless(os.name == "nt", "Windows process sampler")
    def test_mutex_process_sampler_excludes_unrelated_processes(self):
        from db_channel_checks import sample_native_workers
        self.assertEqual(sample_native_workers(self.root.resolve()), [])

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
        self.assertEqual(env["PATHEXT"], os.environ["PATHEXT"])
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
