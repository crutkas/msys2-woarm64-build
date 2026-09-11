import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from artifact import ArtifactError, assemble, deterministic_zip, package_entries, safe_path, sha256


class ArtifactControls(unittest.TestCase):
    def test_unsafe_paths_rejected(self):
        for path in ("../x", "/root", "a/../b", r"c:\x", "a//b"):
            with self.subTest(path=path), self.assertRaises(ArtifactError):
                safe_path(path)

    def test_archive_bytes_identical_after_moving_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("first", "moved root"):
                (root / name).mkdir()
                (root / name / "payload.txt").write_bytes(b"exact content")
            first = deterministic_zip(root / "first", root / "a.zip")
            second = deterministic_zip(root / "moved root", root / "b.zip")
            self.assertEqual(first, second)

    def package(self, root, link_type):
        archive = root / "package.tar"
        with tarfile.open(archive, "w") as output:
            item = tarfile.TarInfo("usr/bin/actual")
            item.size = 4
            output.addfile(item, io.BytesIO(b"real"))
            alias = tarfile.TarInfo("usr/bin/alias")
            alias.type = link_type
            alias.linkname = "actual" if link_type == tarfile.SYMTYPE else "usr/bin/actual"
            output.addfile(alias)
        return {"path": str(archive), "sha256": sha256(archive)}

    def test_package_hardlinks_preserve_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            component = self.package(Path(temporary), tarfile.LNKTYPE)
            rows = list(package_entries(component))
            self.assertEqual(rows[0][1], rows[1][1])
            self.assertEqual(rows[1][2]["type"], "hardlink")

    def test_package_symlinks_require_explicit_materialization(self):
        with tempfile.TemporaryDirectory() as temporary:
            component = self.package(Path(temporary), tarfile.SYMTYPE)
            with self.assertRaises(ArtifactError):
                list(package_entries(component))
            component["materialize_symlinks"] = ["usr/bin/alias"]
            self.assertEqual(list(package_entries(component))[1][1], b"real")

    def test_payload_conflict_does_not_silently_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("a", "b"):
                (root / name).write_text(name)
            plan = {"top_source": {}, "components": [
                {"kind": "file", "id": name, "path": str(root / name), "sha256": sha256(root / name),
                 "destination": "usr/data", "provenance": {"source": {"commit": "fixture"}}}
                for name in ("a", "b")]}
            with self.assertRaises(ArtifactError):
                assemble(plan, root / "output")

    def test_archive_cannot_include_itself(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "payload").write_bytes(b"data")
            with self.assertRaises(ArtifactError):
                deterministic_zip(root, root / "archive.zip")


if __name__ == "__main__":
    unittest.main()
