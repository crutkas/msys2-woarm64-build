import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "arm64-git-recovery"
    / "scripts"
    / "verify-openssl-admission.py"
)
SPEC = importlib.util.spec_from_file_location("openssl_admission_verifier", SCRIPT)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def minimal_pe(machine=0xAA64, optional_magic=0x20B):
    data = bytearray(0x200)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, machine, 0, 0, 0, 0, 0xF0, 0)
    struct.pack_into("<H", data, 0x98, optional_magic)
    return bytes(data)


class OpenSSLAdmissionVerifierTests(unittest.TestCase):
    def test_archive_path_rejects_traversal(self):
        with self.assertRaisesRegex(VERIFIER.AdmissionError, "Unsafe"):
            VERIFIER.archive_path("../openssl.exe")

    def test_pe_identity_requires_arm64_receipt_values(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "openssl.exe"
            path.write_bytes(minimal_pe())
            self.assertEqual(("0xAA64", "0x20B"), VERIFIER.pe_identity(path))

    def test_parse_pkginfo_requires_identity(self):
        with self.assertRaisesRegex(VERIFIER.AdmissionError, "incomplete"):
            VERIFIER.parse_pkginfo(b"arch = any\n")

    def test_archive_manifest_detects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            archive = root / "openssl.pkg.tar.zst"
            with tarfile.open(archive, "w:zst") as stream:
                data = b"pkgname = openssl\npkgver = 1-1\n"
                member = tarfile.TarInfo(".PKGINFO")
                member.size = len(data)
                stream.addfile(member, io.BytesIO(data))
            manifest = root / "files.json"
            manifest.write_text(
                '[{"Path":".PKGINFO","Length":1,"SHA256":"' + "0" * 64 + '"}]\n',
                encoding="utf-8",
            )
            admission = {
                "Package": {
                    "Name": "openssl",
                    "Version": "1-1",
                    "PayloadFiles": 1,
                    "Archive": {
                        "Path": str(archive),
                        "SHA256": VERIFIER.digest(archive),
                        "Length": archive.stat().st_size,
                    },
                    "Manifest": {
                        "Path": str(manifest),
                        "SHA256": VERIFIER.digest(manifest),
                    },
                }
            }
            with self.assertRaisesRegex(VERIFIER.AdmissionError, "manifest mismatch"):
                VERIFIER.verify_archive(admission)

    def test_package_extracts_to_new_root_only(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            archive = root / "openssl.pkg.tar.zst"
            data = b"native payload"
            with tarfile.open(archive, "w:zst") as stream:
                member = tarfile.TarInfo("mingwarm64/bin/openssl.exe")
                member.size = len(data)
                stream.addfile(member, io.BytesIO(data))
            admission = {
                "Package": {"Archive": {"Path": str(archive)}}
            }
            expected = {
                "mingwarm64/bin/openssl.exe": {
                    "length": len(data),
                    "sha256": VERIFIER.digest_bytes(data),
                }
            }
            destination = root / "fresh"
            VERIFIER.extract_package(admission, destination, expected)
            self.assertEqual(
                data,
                (destination / "mingwarm64" / "bin" / "openssl.exe").read_bytes(),
            )
            with self.assertRaisesRegex(
                VERIFIER.AdmissionError, "already exists"
            ):
                VERIFIER.extract_package(admission, destination, expected)

    def test_source_archive_is_resolved_by_hash(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            admission_dir = root / "admission-01"
            source_dir = root / "sources"
            admission_dir.mkdir()
            source_dir.mkdir()
            source = source_dir / "openssl.tar.gz"
            source.write_bytes(b"signed source")
            signature = source_dir / "openssl.tar.gz.asc"
            signature.write_bytes(b"signature")
            admission = {
                "_path": str(admission_dir / "admission.json"),
                "Source": {"ArchiveSHA256": VERIFIER.digest(source)},
            }
            self.assertEqual(source, VERIFIER.resolve_source_archive(admission))

    def test_git_gpgv_uses_posix_drive_paths(self):
        if VERIFIER.os.name != "nt":
            self.skipTest("Windows-only Git gpgv path conversion")
        self.assertEqual(
            "/c/private/openssl.tar.gz",
            VERIFIER.gpg_argument_path(
                Path(r"C:\private\openssl.tar.gz"),
                Path(r"C:\Program Files\Git\usr\bin\gpgv.exe"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
