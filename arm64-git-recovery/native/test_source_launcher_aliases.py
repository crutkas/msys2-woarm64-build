import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from sources import ContractError, digest

spec = importlib.util.spec_from_file_location("source_preparation", Path(__file__).with_name("prepare-posix-tools.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@unittest.skipUnless(os.name == "posix", "The maintained source preparation runs on Linux")
class SourceLauncherControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="zstd-source-alias-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "tests/cli-tests/bin"
        self.bin.mkdir(parents=True)
        self.target = self.bin / "zstd"
        self.target.write_text('#!/bin/sh\nzstdname=$(basename $0)\n"$ZSTD_SYMLINK_DIR/$zstdname" "$@"\n')
        self.target.chmod(0o755)
        for name in ("unzstd", "zstdcat"):
            (self.bin / name).symlink_to("zstd")

    def test_exact_launcher_bytes_and_invocation_names_survive(self):
        commands = self.root / "commands"
        commands.mkdir()
        for name in ("unzstd", "zstdcat"):
            command = commands / name
            command.write_text('#!/bin/sh\nbasename "$0"\n')
            command.chmod(0o755)
        env = {**os.environ, "ZSTD_SYMLINK_DIR": str(commands)}
        before = {name: subprocess.check_output([self.bin / name], env=env) for name in ("unzstd", "zstdcat")}
        records = module.materialize_zstd_launchers(self.root)
        self.assertEqual(len(records), 2)
        for name in ("unzstd", "zstdcat"):
            alias = self.bin / name
            self.assertFalse(alias.is_symlink())
            self.assertEqual(digest(alias), digest(self.target))
            self.assertEqual(subprocess.check_output([alias], env=env), before[name])
            self.assertEqual(before[name], (name + "\n").encode())

    def test_unexpected_link_is_not_silently_flattened(self):
        (self.bin / "unexpected").symlink_to("zstd")
        with self.assertRaises(ContractError):
            module.materialize_zstd_launchers(self.root)
        self.assertTrue((self.bin / "unzstd").is_symlink())

    def test_changed_target_semantics_is_rejected(self):
        self.target.write_text("changed dispatch")
        with self.assertRaises(ContractError):
            module.materialize_zstd_launchers(self.root)
        self.assertTrue((self.bin / "zstdcat").is_symlink())


if __name__ == "__main__":
    unittest.main()
