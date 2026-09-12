import io
import gzip
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

from db_package import create_package, pe_metadata, readback_package, split_for, split_inventory
from sources import ContractError, digest, inventory


class DbPackageControls(unittest.TestCase):
    def image(self, machine=0xAA64):
        data = bytearray(1024)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<HH", data, 0x84, machine, 1)
        struct.pack_into("<HH", data, 0x94, 240, 0x2022)
        struct.pack_into("<H", data, 0x98, 0x20B)
        struct.pack_into("<I", data, 0x98 + 108, 2)
        struct.pack_into("<IIII", data, 0x188 + 8, 0x200, 0x1000, 0x200, 0x200)
        return data

    def test_actual_ordinary_arm64_only(self):
        self.assertEqual(pe_metadata(self.image())["machine"], "0xAA64")
        for machine in (0x8664, 0xA641, 0x14C):
            with self.subTest(machine=machine), self.assertRaises(ContractError):
                pe_metadata(self.image(machine))
        with self.assertRaises(ContractError):
            pe_metadata(self.image()[:64])

    def test_split_preserves_libraries_headers_docs_and_license(self):
        self.assertEqual(split_for("usr/bin/db_dump.exe"), "db")
        self.assertEqual(split_for("usr/bin/msys-db_cxx-6.2.dll"), "libdb")
        self.assertEqual(split_for("usr/share/licenses/db/LICENSE"), "libdb")
        self.assertEqual(split_for("usr/include/db_185.h"), "libdb-devel")
        self.assertEqual(split_for("usr/lib/libdb_cxx.a"), "libdb-devel")
        self.assertEqual(split_for("usr/share/doc/db/html/index.html"), "db-docs")
        with self.assertRaises(ContractError):
            split_for("unowned/file")
        with self.assertRaises(ContractError):
            split_inventory({"usr/bin/db_dump.exe": {"sha256": "a" * 64, "size": 1}})

    def test_real_zstd_archive_complete_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / "stage"
            (stage / "usr/bin").mkdir(parents=True)
            (stage / "usr/bin/msys-db-6.2.dll").write_bytes(self.image())
            files = inventory(stage)
            path = root / "libdb.pkg.tar.zst"
            result = create_package(stage, path, "libdb", files, 1000, "a" * 64, "/build/db")
            self.assertTrue(result["archive_readback_complete"])
            self.assertEqual(result["pe_images"][0]["machine"], "0xAA64")
            self.assertEqual(result["files"], files)
            with self.assertRaises(ContractError):
                readback_package(path, "db", files)
            with self.assertRaises(ContractError):
                readback_package(path, "libdb", {})

    def test_x64_payload_and_duplicate_members_cannot_pass_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / "stage"
            (stage / "usr/bin").mkdir(parents=True)
            (stage / "usr/bin/msys-db-6.2.dll").write_bytes(self.image(0x8664))
            with self.assertRaises(ContractError):
                create_package(stage, root / "x64.pkg.tar.zst", "libdb", inventory(stage), 1000, "a" * 64, "/build")
            duplicate = root / "duplicate.pkg.tar.zst"
            with tarfile.open(duplicate, "x:zst") as archive:
                info = tarfile.TarInfo(".PKGINFO")
                info.size = 1
                archive.addfile(info, io.BytesIO(b"a"))
                archive.addfile(info, io.BytesIO(b"b"))
            with self.assertRaises(ContractError):
                readback_package(duplicate, "libdb", {})

    def rewrite_metadata(self, original, output, transform):
        with tarfile.open(original, "r:zst") as source, tarfile.open(output, "x:zst") as dest:
            for entry in source:
                data = source.extractfile(entry).read()
                data = transform(entry.name, data)
                entry.size = len(data)
                dest.addfile(entry, io.BytesIO(data))

    def test_wrong_version_dependencies_and_invalid_buildinfo_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / "stage"
            (stage / "usr/bin").mkdir(parents=True)
            (stage / "usr/bin/msys-db-6.2.dll").write_bytes(self.image())
            files = inventory(stage)
            archive = root / "original.pkg.tar.zst"
            create_package(stage, archive, "libdb", files, 1000, "a" * 64, "/build")
            changes = [
                lambda name, data: data.replace(b"pkgver = 6.2.32-6", b"pkgver = 0.0-1") if name == ".PKGINFO" else data,
                lambda name, data: data.replace(b"depend = gcc-libs\n", b"") if name == ".PKGINFO" else data,
                lambda name, data: b"not build metadata\n" if name == ".BUILDINFO" else data,
            ]
            for index, change in enumerate(changes):
                bad = root / f"bad-{index}.pkg.tar.zst"
                self.rewrite_metadata(archive, bad, change)
                with self.subTest(change=index), self.assertRaises(ContractError):
                    readback_package(bad, "libdb", files, "a" * 64)

    def test_mtree_hashes_must_belong_to_the_correct_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage = root / "stage"
            (stage / "usr/share/doc").mkdir(parents=True)
            (stage / "usr/share/doc/a.txt").write_bytes(b"a")
            (stage / "usr/share/doc/b.txt").write_bytes(b"b")
            files = inventory(stage)
            original = root / "original.pkg.tar.zst"
            create_package(stage, original, "db-docs", files, 1000, "a" * 64, "/build")
            a, b = [row["sha256"].encode() for row in files.values()]
            def swap(name, data):
                if name != ".MTREE":
                    return data
                text = gzip.decompress(data).replace(a, b"placeholder").replace(b, a).replace(b"placeholder", b)
                return gzip.compress(text, mtime=0)
            bad = root / "swapped.pkg.tar.zst"
            self.rewrite_metadata(original, bad, swap)
            with self.assertRaisesRegex(ContractError, "tuples"):
                readback_package(bad, "db-docs", files)

    def test_successful_proof_for_different_inputs_cannot_package(self):
        from db_combined_release import COMBINED_SHA, RUNTIME_SHA, require_package_proof
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prepare.json"
            prepared = {"combined_handoff": {"sha256": COMBINED_SHA}, "combined_runtime": {"runtime": {"sha256": RUNTIME_SHA}}}
            path.write_text(json.dumps(prepared))
            good = {"status": "native-db-combined907-api-cli-and-modules-passed", "inputs_unchanged": True,
                    "prepare": {"sha256": digest(path)}, "runtime_sha256": RUNTIME_SHA}
            require_package_proof(path, prepared, good)
            for bad in ({**good, "prepare": {"sha256": "a" * 64}}, {**good, "runtime_sha256": "b" * 64},
                        {**good, "inputs_unchanged": False}):
                with self.assertRaises(ContractError):
                    require_package_proof(path, prepared, bad)

    def test_continuation_rejects_unrecorded_or_changed_runtime(self):
        from db_combined_release import require_continuation_runtime
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "db_upgrade.exe").write_bytes(self.image())
            base = inventory(runtime)
            manifest = root / "runtime.json"
            manifest.write_text(json.dumps({"files": base}))
            for name in ("c", "cpp", "185", "process"):
                (runtime / (name + ".exe")).write_bytes(self.image())
            full = inventory(runtime)
            previous = {"proof_executable_files": {name: row for name, row in full.items() if name not in base},
                        "input_identities": {str(manifest.resolve()): digest(manifest)}}
            self.assertEqual(require_continuation_runtime(runtime, manifest, previous), full)
            with self.assertRaisesRegex(ContractError, "recorded"):
                require_continuation_runtime(runtime, manifest, {"input_identities": previous["input_identities"]})
            (runtime / "db_upgrade.exe").write_bytes(self.image(0x8664))
            with self.assertRaisesRegex(ContractError, "changed between"):
                require_continuation_runtime(runtime, manifest, previous)
            manifest.write_text(json.dumps({"files": {"db_upgrade.exe": inventory(runtime)["db_upgrade.exe"]}}))
            with self.assertRaisesRegex(ContractError, "original receipt-bound"):
                require_continuation_runtime(runtime, manifest, previous)


if __name__ == "__main__":
    unittest.main()
