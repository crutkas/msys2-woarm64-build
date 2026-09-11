import json
from pathlib import Path
import tempfile
import unittest

from artifact import ArtifactError, deterministic_zip, inventory, sha256, write_json
from moved_replay import extract
from seal import ARTIFACT_NAME
from verify_handoff import read_archive


class HandoffReadbackControls(unittest.TestCase):
    def fixture(self, base, *, omit_directory=False, wrong_files=False, wrong_machine=False):
        root = base / "input"
        root.mkdir()
        for name in ("etc", "tmp", "var/tmp", "home"):
            if not omit_directory or name != "home":
                (root / name).mkdir(parents=True, exist_ok=True)
        (root / "plain.txt").write_text("real fixture bytes\n", encoding="utf-8")
        files = inventory(root)
        if wrong_files:
            files = {}
        if wrong_machine:
            files["plain.txt"]["machine"] = "0x8664"
        source = {"commit": "fixture-source", "tree": "fixture-tree"}
        write_json(root / "manifest.json", {"top_source": source, "files": files})
        archive = base / "fixture.zip"
        receipt = {**deterministic_zip(root, archive), "source": source,
                   "artifact": ARTIFACT_NAME, "publication_authorized": True, "deterministic_recreation": True,
                   "manifest_sha256": sha256(root / "manifest.json")}
        return archive, receipt

    def test_exact_archive_can_be_extracted_without_adding_missing_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            archive, receipt = self.fixture(base)
            expected = read_archive(archive, receipt)
            moved = base / "moved directory"
            extract(archive, moved, expected)
            self.assertEqual(inventory(moved), expected)

    def test_digest_manifest_source_and_inventory_mismatches_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, receipt = self.fixture(Path(directory))
            for key, value in (("sha256", "wrong"), ("size", 0), ("manifest_sha256", "wrong"),
                               ("source", {"commit": "other"}), ("publication_authorized", False),
                               ("deterministic_recreation", False), ("artifact", "diagnostic.zip")):
                with self.subTest(key=key), self.assertRaises(ArtifactError):
                    read_archive(archive, {**receipt, key: value})
        for option in ("omit_directory", "wrong_files", "wrong_machine"):
            with tempfile.TemporaryDirectory() as directory:
                archive, receipt = self.fixture(Path(directory), **{option: True})
                with self.subTest(option=option), self.assertRaises(ArtifactError):
                    read_archive(archive, receipt)


if __name__ == "__main__":
    unittest.main()
