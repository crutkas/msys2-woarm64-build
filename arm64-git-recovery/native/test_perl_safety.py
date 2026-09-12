import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from perl_safety import GUARDS, verify_guards
from sources import ContractError


class PerlSafetyControls(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="perl-predicate-control-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name, guard in GUARDS.items():
            (self.root / name).write_text(guard + "\nif $issymlink $try; then\n    :\nfi\n")

    def test_both_uses_are_guarded(self):
        verify_guards(self.root)

    def test_each_unguarded_site_is_rejected(self):
        for name in GUARDS:
            with self.subTest(name=name):
                path = self.root / name
                saved = path.read_text()
                path.write_text("if $issymlink $try; then\n    :\nfi\n")
                with self.assertRaises(ContractError):
                    verify_guards(self.root)
                path.write_text(saved)

    def test_additional_unguarded_use_is_rejected(self):
        path = self.root / "Configure"
        path.write_text(path.read_text() + "if $issymlink $another; then\n    :\nfi\n")
        with self.assertRaises(ContractError):
            verify_guards(self.root)

    @unittest.skipUnless(os.environ.get("NATIVE_TEST_BASH"), "Explicit native Bash fixture path required")
    def test_empty_predicate_aborts_before_path_execution(self):
        env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
        for guard in GUARDS.values():
            with self.subTest(guard=guard):
                result = subprocess.run(
                    [os.environ["NATIVE_TEST_BASH"], "--noprofile", "--norc", "-c",
                     "issymlink=''; try='printf'; " + guard + '; if $issymlink "$try"; then :; fi'],
                    cwd=self.root, env=env, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"A tested symlink predicate is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
