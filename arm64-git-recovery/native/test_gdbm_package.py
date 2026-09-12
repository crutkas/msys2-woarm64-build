import gzip
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from gdbm_package import create_archive, metadata, readback, split_files
from sources import ContractError, inventory


class GdbmPackageControls(unittest.TestCase):
    def test_complete_split_preserves_compat_and_nls(self):
        names = (
            "usr/bin/gdbmtool.exe", "usr/bin/cyggdbm-6.dll", "usr/bin/cyggdbm_compat-4.dll",
            "usr/include/gdbm.h", "usr/include/gdbm/ndbm.h",
            "usr/lib/libgdbm.a", "usr/lib/libgdbm_compat.dll.a",
            "usr/share/locale/de/LC_MESSAGES/gdbm.mo", "usr/share/licenses/gdbm/COPYING",
        )
        groups = split_files({name: {"sha256": "a" * 64, "size": 1} for name in names})
        self.assertIn("usr/bin/cyggdbm_compat-4.dll", groups["libgdbm"])
        self.assertIn("usr/include/gdbm/ndbm.h", groups["libgdbm-devel"])
        self.assertIn("usr/share/locale/de/LC_MESSAGES/gdbm.mo", groups["gdbm"])
        with self.assertRaises(ContractError):
            split_files({"unexpected": {"sha256": "a" * 64, "size": 1}})

    def test_canonical_build_metadata_has_no_fake_provider(self):
        entries = metadata("libgdbm-devel", {}, 1000)
        self.assertIn(b"builddir = /usr/src/packages/gdbm\n", entries[".BUILDINFO"])
        self.assertNotIn(b"provides", entries[".PKGINFO"])
        self.assertIn(b"depend = libgdbm=1.26\n", entries[".PKGINFO"])

    def test_real_archive_and_mtree_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / "stage"
            (stage / "usr/include").mkdir(parents=True)
            (stage / "usr/include/gdbm.h").write_bytes(b"unit fixture\n")
            files = inventory(stage)
            result = create_archive(stage, root, "libgdbm-devel", files, 1000)
            self.assertTrue(result["archive_and_mtree_readback_complete"])
            self.assertFalse(result["provider_admitted"])
            self.assertEqual(result["files"], files)

    def test_stale_buildinfo_mtree_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / "stage"
            (stage / "usr/include").mkdir(parents=True)
            (stage / "usr/include/gdbm.h").write_bytes(b"unit fixture\n")
            files = inventory(stage)
            original = create_archive(stage, root, "libgdbm-devel", files, 1000)
            damaged = root / "damaged.pkg.tar.zst"
            with tarfile.open(original["path"], "r:zst") as source, tarfile.open(damaged, "x:zst") as output:
                for member in source:
                    data = source.extractfile(member).read()
                    if member.name == ".MTREE":
                        text = gzip.decompress(data).replace(b"./.BUILDINFO ", b"./.BUILDINFO.extra ")
                        data = gzip.compress(text, mtime=0)
                    member.size = len(data)
                    output.addfile(member, io.BytesIO(data))
            with self.assertRaisesRegex(ContractError, "tuples"):
                readback(damaged, "libgdbm-devel", files, metadata("libgdbm-devel", files, 1000))

    def test_duplicate_archive_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "duplicate.pkg.tar.zst"
            with tarfile.open(path, "x:zst") as archive:
                for _ in range(2):
                    member = tarfile.TarInfo(".PKGINFO")
                    member.mode, member.size = 0o644, 1
                    archive.addfile(member, io.BytesIO(b"x"))
            with self.assertRaises(ContractError):
                readback(path, "libgdbm-devel", {}, metadata("libgdbm-devel", {}, 1000))


if __name__ == "__main__":
    unittest.main()
