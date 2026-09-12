import json
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock
import uuid

from sources import ContractError, digest, inventory
from ssh_bootstrap import producer_files, snapshot_bootstrap


class SshBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ.get("SSH_TEST_ROOT", ".ssh-test-work")) / str(uuid.uuid4())
        self.root.mkdir(parents=True)
        self.source = self.root / "approved-source"
        (self.source / "usr" / "empty-directory").mkdir(parents=True)
        (self.source / "usr" / "data").write_bytes(b"unit fixture only; never executed")
        self.producer = self.root / "producer.json"
        self.rows = [{"Path": "usr\\data", "SHA256": digest(self.source / "usr" / "data")}]
        self.producer.write_text(json.dumps(self.rows), encoding="utf-8")
        self.descriptor = self.root / "descriptor.json"
        self.record = {
            "Status": "quiescent-preserved-bootstrap-source-currently-verified",
            "Source": str(self.source), "Consumers": 0, "Files": 1,
            "Inventory": str(self.producer), "InventorySHA256": digest(self.producer),
            "NoReadOfActivePrefix": str(self.root / "forbidden-active-prefix"),
        }
        self.write_descriptor()
        self.memory = mock.patch("ssh_bootstrap.require_memory", return_value=16)
        self.memory.start()

    def tearDown(self):
        self.memory.stop()
        shutil.rmtree(self.root)

    def write_descriptor(self):
        self.descriptor.write_text(json.dumps(self.record), encoding="utf-8")
        self.seal = digest(self.descriptor)

    def snapshot(self):
        return snapshot_bootstrap(self.descriptor, self.seal, self.root / "private")

    def test_complete_private_copy_preserves_empty_directories(self):
        before = inventory(self.source)
        with mock.patch("builtins.print"):
            report = self.snapshot()
        self.assertTrue(report["source_unchanged"])
        self.assertEqual(report["target_or_bootstrap_processes_launched"], 0)
        self.assertEqual(inventory(self.source), before)
        self.assertEqual(inventory(self.root / "private" / "msys64"), before)
        self.assertTrue((self.root / "private" / "msys64" / "usr" / "empty-directory").is_dir())
        self.assertTrue((self.root / "private" / "msys64.copy.json").is_file())
        with self.assertRaises(ContractError):
            self.snapshot()

    def test_wrong_descriptor_seal_and_active_source_rejected(self):
        with self.assertRaises(ContractError):
            snapshot_bootstrap(self.descriptor, "0" * 64, self.root / "private")
        self.record["NoReadOfActivePrefix"] = str(self.source)
        self.write_descriptor()
        with self.assertRaises(ContractError):
            self.snapshot()
        self.assertFalse((self.root / "private").exists())

    def test_nonquiescent_source_rejected(self):
        self.record["Consumers"] = 1
        self.write_descriptor()
        with self.assertRaises(ContractError):
            self.snapshot()

    def test_changed_source_or_inventory_rejected_before_copy(self):
        (self.source / "usr" / "data").write_bytes(b"changed")
        with self.assertRaises(ContractError):
            self.snapshot()
        self.assertFalse((self.root / "private").exists())
        self.producer.write_text("[]", encoding="utf-8")
        with self.assertRaises(ContractError):
            self.snapshot()

    def test_changed_copy_retains_failure_evidence(self):
        original_copy = shutil.copy2

        def corrupt(source, destination):
            original_copy(source, destination)
            Path(destination).write_bytes(b"corrupt")

        with mock.patch("ssh_bootstrap.shutil.copy2", side_effect=corrupt), mock.patch("builtins.print"):
            with self.assertRaises(ContractError):
                self.snapshot()
        result = json.loads((self.root / "private" / "result.json").read_text())
        self.assertEqual(result["status"], "failed")
        self.assertFalse((self.root / "private" / "msys64.copy.json").exists())

    def test_nested_output_rejected(self):
        with self.assertRaises(ContractError):
            snapshot_bootstrap(self.descriptor, self.seal, self.source / "nested")

    def test_unsafe_inventory_paths_and_duplicates_rejected(self):
        for rows in ([{"Path": "..\\outside", "SHA256": "a" * 64}],
                     [{"Path": "C:\\outside", "SHA256": "a" * 64}],
                     [{"Path": "file", "SHA256": "a" * 64}, {"Path": "FILE", "SHA256": "b" * 64}]):
            with self.subTest(rows=rows), self.assertRaises(ContractError):
                producer_files(rows)

    def test_memory_floor_failure_creates_no_copy(self):
        with mock.patch("ssh_bootstrap.require_memory", side_effect=ContractError("RAM floor")):
            with self.assertRaises(ContractError):
                self.snapshot()
        self.assertFalse((self.root / "private").exists())


if __name__ == "__main__":
    unittest.main()
