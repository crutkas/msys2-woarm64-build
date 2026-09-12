import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from perl_profiles import STRICT_PROFILE, SYSTEM_PROFILE, profile_record, require_system_environment
from perl_system_inputs import require_separate_output
from sources import ContractError


class PerlProfileControls(unittest.TestCase):
    def test_output_cannot_overlap_current_published_inputs(self):
        root = Path.cwd()
        published = root / "published"
        require_separate_output(root / "owned-output", [published])
        for output in (published, published / "new-build", root):
            with self.subTest(output=output), self.assertRaises(ContractError):
                require_separate_output(output, [published])

    def test_strict_cli_stays_default_and_alternative_is_named(self):
        script = Path(__file__).with_name("build-native-perl.py")
        strict = subprocess.run([sys.executable, "-B", script, "--help"], capture_output=True, text=True, timeout=15)
        self.assertEqual(strict.returncode, 0)
        self.assertIn("Default profile: nativestrict", strict.stdout)
        self.assertIn("--handoff-sha256", strict.stdout)
        alternative = subprocess.run([sys.executable, "-B", script, "--profile", SYSTEM_PROFILE, "--help"],
                                     capture_output=True, text=True, timeout=15)
        self.assertEqual(alternative.returncode, 0)
        self.assertIn("--input-spec", alternative.stdout)
        self.assertIn("compiler/source-link compatibility", alternative.stdout)
        self.assertNotIn("--handoff-sha256", alternative.stdout)

    def test_alternative_does_not_claim_strict_qualification(self):
        self.assertEqual(profile_record(STRICT_PROFILE)["MSYS"], "winsymlinks:nativestrict")
        record = profile_record(SYSTEM_PROFILE)
        self.assertIs(record["NativeWindowsSymlinkQualification"], False)
        self.assertEqual(record["MSYS"], "winsymlinks:sys")
        with self.assertRaises(ContractError):
            profile_record("automatic-fallback")

    def test_native_parent_contract_rejects_foreign_conversion_overrides(self):
        base = {"MSYS": "winsymlinks:sys", "MSYSTEM": "CYGWIN"}
        require_system_environment(base)
        for name, value in (("MSYS", "winsymlinks:nativestrict"), ("MSYSTEM", "MSYS"),
                            ("MSYS2_ARG_CONV_EXCL", "*"), ("MSYS2_ENV_CONV_EXCL", "PATH"),
                            ("BASH_ENV", "startup"), ("ENV", "startup")):
            with self.subTest(name=name), self.assertRaises(ContractError):
                require_system_environment({**base, name: value})

    @unittest.skipUnless(os.environ.get("PERL_NATIVE_UTILITY_ROOT"), "Current qualified native utility root required")
    def test_actual_supported_posix_symlinks(self):
        root = Path(os.environ["PERL_NATIVE_UTILITY_ROOT"]).resolve()
        environment = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC") if name in os.environ}
        environment.update({"MSYS": "winsymlinks:sys", "MSYSTEM": "CYGWIN",
                            "PATH": str(root / "usr/bin") + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32")})
        with tempfile.TemporaryDirectory(prefix="perl-system-links-") as temporary:
            target = Path(temporary) / "probe"
            result = subprocess.run([str(root / "usr/bin/bash.exe"), "--noprofile", "--norc",
                                     Path(__file__).with_name("perl-system-symlink-check.sh").resolve().as_posix(),
                                     target.as_posix()], env=environment, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(b"PERL_SYSTEM_SYMLINKS=PASS", result.stdout)
            self.assertIn(b"NATIVE_WINDOWS_SYMLINK_QUALIFICATION=false", result.stdout)


if __name__ == "__main__":
    unittest.main()
