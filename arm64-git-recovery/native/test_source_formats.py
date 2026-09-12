import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from sources import ContractError, digest, recover


class SourceFormatControls(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-source-format-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()

    def identity(self, name, archive_format):
        return {"id": "fixture", "version": "1", "file": name, "prefix": "bundle",
                "url": "https://example.invalid/never-downloaded", "format": archive_format,
                "sha256": digest(self.cache / name)}

    def test_zip_contents_permissions_and_inventory(self):
        with zipfile.ZipFile(self.cache / "source.zip", "w") as archive:
            member = zipfile.ZipInfo("bundle/configure")
            member.create_system = 3
            member.external_attr = (stat.S_IFREG | 0o755) << 16
            archive.writestr(member, b"#!/bin/sh\nexit 0\n")
        item = self.identity("source.zip", "zip")
        result = recover(item, self.cache, self.root / "out")
        self.assertEqual(result["files"], 1)
        path = self.root / "out/fixture/configure"
        self.assertEqual(path.read_bytes(), b"#!/bin/sh\nexit 0\n")
        if os.name != "nt":
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
        self.assertEqual(recover(item, self.cache, self.root / "out")["files"], 1)

    def test_zip_traversal_wrong_prefix_case_alias_and_link_rejected(self):
        for index, names in enumerate((["bundle/../escape"], ["wrong/file"],
                                       ["bundle/one", "bundle/ONE"], ["bundle/link"])):
            with self.subTest(names=names):
                filename = f"bad-{index}.zip"
                with zipfile.ZipFile(self.cache / filename, "w") as archive:
                    for name in names:
                        member = zipfile.ZipInfo(name)
                        if name.endswith("/link"):
                            member.create_system = 3
                            member.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(member, b"data")
                with self.assertRaises(ContractError):
                    recover(self.identity(filename, "zip"), self.cache, self.root / f"out-{index}")

    def test_raw_patch_is_hash_bound_and_reusable(self):
        path = self.cache / "patch-001"
        path.write_bytes(b"pinned patch\n")
        item = self.identity(path.name, "file")
        recover(item, self.cache, self.root / "out")
        record = json.loads((self.root / "out/fixture.inventory.json").read_text())
        self.assertEqual(list(record["files"]), ["patch-001"])
        path.write_bytes(b"changed")
        with self.assertRaises(ContractError):
            recover(item, self.cache, self.root / "out")


if __name__ == "__main__":
    unittest.main()
