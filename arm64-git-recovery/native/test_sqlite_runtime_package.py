from compression import zstd
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from sources import ContractError

spec = importlib.util.spec_from_file_location("sqlite_package", Path(__file__).with_name("package-sqlite-runtime.py"))
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class RuntimePackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.archive = Path(self.directory.name) / "libsqlite.pkg.tar.zst"
        self.pkginfo = package.package_info(3, 123)

    def write_archive(self, entries):
        with zstd.ZstdFile(self.archive, "w") as stream, tarfile.open(fileobj=stream, mode="w|") as tar:
            for name, value in entries:
                info = tarfile.TarInfo(name)
                info.size = len(value)
                tar.addfile(info, io.BytesIO(value))

    def test_metadata_is_native_msys_runtime_only(self):
        text = self.pkginfo.decode()
        self.assertIn("pkgname = libsqlite\n", text)
        self.assertIn("arch = aarch64\n", text)
        self.assertIn("depend = msys2-runtime\n", text)
        self.assertNotIn("mingw", text)

    def test_archive_verifies_exact_payload_not_just_hash_of_compressed_file(self):
        name, value = "usr/bin/msys-sqlite3-0.dll", b"abc"
        expected = {name: {"size": 3, "sha256": hashlib.sha256(value).hexdigest()}}
        self.write_archive([(".PKGINFO", self.pkginfo), (name, value)])
        self.assertEqual(len(package.verify_archive(self.archive, expected, self.pkginfo)), 2)
        for extra in ([("extra.dll", b"x")], [(name, value)]):
            self.write_archive([(".PKGINFO", self.pkginfo), (name, value), *extra])
            with self.assertRaises(ContractError):
                package.verify_archive(self.archive, expected, self.pkginfo)
