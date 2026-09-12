import json
import os
from pathlib import Path
import shutil
import unittest
import uuid

from sources import ContractError
from ssh_crypt_consumer import matching_relay, validate_loaded


class CryptInstalledControls(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.environ.get("SSH_TEST_ROOT", ".ssh-test-work")) / str(uuid.uuid4())
        self.root.mkdir(parents=True)
        self.binary = self.root / "native-crypt-consumer.exe"
        self.expected = {name: {"path": str(self.root / name), "sha256": "a" * 64}
                         for name in ("msys-crypt-2.dll", "msys-2.0.dll")}

    def tearDown(self):
        shutil.rmtree(self.root)

    def identity(self):
        return {"pid": 123, "image": str(self.binary), "process_machine": 0, "native_machine": 0xAA64,
                "creation_filetime": 123456,
                "dlls": [{"name": name, **row} for name, row in self.expected.items()]}

    def test_exact_native_private_identity(self):
        validate_loaded(self.identity(), 123, self.binary, self.expected)

    def test_wrong_architecture_pid_image_or_generation_rejected(self):
        for name, value in (("pid", 124), ("image", str(self.root / "other.exe")),
                            ("process_machine", 0x8664), ("native_machine", 0x8664),
                            ("creation_filetime", 0)):
            with self.subTest(name=name), self.assertRaises(ContractError):
                validate_loaded({**self.identity(), name: value}, 123, self.binary, self.expected)

    def test_other_prefix_or_wrong_dll_bytes_rejected(self):
        for key, value in (("path", str(self.root / "other/msys-crypt-2.dll")), ("sha256", "b" * 64)):
            record = self.identity()
            record["dlls"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                validate_loaded(record, 123, self.binary, self.expected)
        record = self.identity()
        record["dlls"].pop()
        with self.assertRaises(ContractError):
            validate_loaded(record, 123, self.binary, self.expected)
        record = self.identity()
        record["dlls"].append(dict(record["dlls"][0]))
        with self.assertRaises(ContractError):
            validate_loaded(record, 123, self.binary, self.expected)

    def test_exact_generation_relay_and_raw_success_required(self):
        relay = {"child_pid": 123, "child_created": 123456, "sha256": "c" * 64, "raw_exit": 0, "portable_exit": 0}
        path = self.root / "relay.json"
        path.write_text(json.dumps(relay))
        matching_relay(self.root, self.identity(), "c" * 64)
        for key, value in (("child_created", 123457), ("raw_exit", 37), ("portable_exit", 37),
                            ("sha256", "d" * 64)):
            path.write_text(json.dumps({**relay, key: value}))
            with self.subTest(key=key), self.assertRaises(ContractError):
                matching_relay(self.root, self.identity(), "c" * 64)

    def test_duplicate_pid_relays_rejected(self):
        row = {"child_pid": 123, "child_created": 123456, "sha256": "c" * 64, "raw_exit": 0, "portable_exit": 0}
        for name in ("first.json", "second.json"):
            (self.root / name).write_text(json.dumps(row))
        with self.assertRaises(ContractError):
            matching_relay(self.root, self.identity(), "c" * 64)


if __name__ == "__main__":
    unittest.main()
