import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from sources import ContractError
from documentation_exec import portable_exit
from documentation_tools import verify_xz_documentation

spec = importlib.util.spec_from_file_location("documentation_driver", Path(__file__).with_name("recover-documentation-driver.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DocumentationDriverControls(unittest.TestCase):
    def test_documentation_transport_preserves_nonzero_status(self):
        for code in (0, 1, 127, 255):
            self.assertEqual(portable_exit(code), code)
        for code in (256, 1536, 0xC0000005, -1):
            self.assertEqual(portable_exit(code), 255)

    def test_archive_requires_exact_flat_regular_members(self):
        entries = [zipfile.ZipInfo(name) for name in module.ZIP_FILES]
        module.validate_zip(entries)
        for invalid in (entries[:-1], entries + [entries[0]], entries + [zipfile.ZipInfo("../outside")]):
            with self.assertRaises(ContractError):
                module.validate_zip(invalid)
        entries[0].create_system = 3
        entries[0].external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ContractError):
            module.validate_zip(entries)

    def test_empty_documentation_or_a_banner_cannot_qualify(self):
        with tempfile.TemporaryDirectory(prefix="documentation-control-") as temporary:
            root = Path(temporary)
            (root / "xml").mkdir()
            (root / "html").mkdir()
            (root / "xml/index.xml").write_text("<doxygenindex/>")
            (root / "html/index.html").write_text("Doxygen 1.18.0")
            with self.assertRaises(ContractError):
                module.verify_documentation(root)
            (root / "xml/index.xml").write_text(
                "<doxygenindex><name>documentation_probe</name>"
                "<name>documentation_probe_count</name></doxygenindex>")
            self.assertIn("documentation_probe_count", module.verify_documentation(root)["documented_elements"])

    def test_xz_requires_api_pages_and_its_actual_version(self):
        with tempfile.TemporaryDirectory(prefix="xz-documentation-control-") as temporary:
            root = Path(temporary)
            for name in ("index.html", "structlzma__stream.html", "lzma12_8h.html", "version_8h.html"):
                (root / name).write_text("API content")
            (root / "index.html").write_text('<span id="projectnumber">&#160;5.8.3</span>')
            self.assertEqual(verify_xz_documentation(root, "5.8.3")["project_version"], "5.8.3")
            with self.assertRaises(ContractError):
                verify_xz_documentation(root, "5.8.2")
            (root / "version_8h.html").write_text("")
            with self.assertRaises(ContractError):
                verify_xz_documentation(root, "5.8.3")


if __name__ == "__main__":
    unittest.main()
