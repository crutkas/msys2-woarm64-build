import json
from pathlib import Path
import tempfile
import unittest

from sources import ContractError, digest, inventory
from sqlite_consumer_inputs import merge_files, sealed_json, verify_files


class ConsumerInputsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.target = self.root / "target"
        self.source.mkdir()
        self.target.mkdir()

    def test_sealed_metadata_rejects_changes(self):
        path = self.root / "receipt.json"
        path.write_text(json.dumps({"status": "candidate"}))
        sha = digest(path)
        self.assertEqual(sealed_json(path, sha)["status"], "candidate")
        path.write_text(json.dumps({"status": "admitted"}))
        with self.assertRaises(ContractError):
            sealed_json(path, sha)

    def test_matching_files_can_merge_but_different_runtime_cannot(self):
        (self.source / "runtime.dll").write_bytes(b"old")
        files = inventory(self.source)
        merge_files(self.source, self.target, files)
        verify_files(self.target, files)
        merge_files(self.source, self.target, files)
        (self.target / "runtime.dll").write_bytes(b"new")
        with self.assertRaises(ContractError):
            merge_files(self.source, self.target, files)

    def test_explicit_overlay_is_not_accidentally_copied(self):
        (self.source / "runtime.dll").write_bytes(b"old")
        (self.source / "sqlite.dll").write_bytes(b"sqlite")
        merge_files(self.source, self.target, inventory(self.source), omit=("runtime.dll",))
        self.assertFalse((self.target / "runtime.dll").exists())
        self.assertEqual((self.target / "sqlite.dll").read_bytes(), b"sqlite")

    def test_rejects_links_and_traversal(self):
        for path, row in (("link", {"symlink": "file"}), ("../outside", {"sha256": "x", "size": 1})):
            with self.subTest(path=path), self.assertRaises(ContractError):
                merge_files(self.source, self.target, {path: row})

    def test_inventory_does_not_bless_added_files(self):
        (self.source / "sqlite.dll").write_bytes(b"sqlite")
        files = inventory(self.source)
        (self.source / "extra.dll").write_bytes(b"extra")
        with self.assertRaises(ContractError):
            verify_files(self.source, files)
