import importlib.util
from pathlib import Path
import tempfile
import unittest

from sources import ContractError, digest

spec = importlib.util.spec_from_file_location("libtool_input", Path(__file__).with_name("copy-libtool-input.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LibtoolInputControls(unittest.TestCase):
    def test_full_inventory_and_changed_macro(self):
        with tempfile.TemporaryDirectory(prefix="libtool-input-") as directory:
            root = Path(directory)
            (root / "libtool.m4").write_bytes(b"fixture")
            rows = [{"Path": "libtool.m4", "SHA256": digest(root / "libtool.m4")}]
            self.assertEqual(len(module.verify_rows(root, rows)), 1)
            (root / "libtool.m4").write_bytes(b"changed")
            with self.assertRaises(ContractError):
                module.verify_rows(root, rows)

    def test_extra_file_and_case_duplicate_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="libtool-input-") as directory:
            root = Path(directory)
            (root / "macro").write_bytes(b"fixture")
            rows = [{"Path": "macro", "SHA256": digest(root / "macro")}]
            with self.assertRaises(ContractError):
                module.verify_rows(root, rows + [{"Path": "MACRO", "SHA256": rows[0]["SHA256"]}])
            (root / "extra").write_bytes(b"untracked")
            with self.assertRaises(ContractError):
                module.verify_rows(root, rows)


if __name__ == "__main__":
    unittest.main()
