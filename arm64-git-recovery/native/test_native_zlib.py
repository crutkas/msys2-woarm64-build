"""Synthetic recipe/archive controls; not native build or execution proof."""

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

from sources import ContractError


spec = importlib.util.spec_from_file_location(
    "native_zlib_builder", Path(__file__).with_name("build-native-zlib.py"))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class NativeZlibControls(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="zlib-recipe-control-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def recipe(self, objects="adler32.o compress.o", flags="$(LOC) -O3 -Wall", assembly=""):
        (self.root / "win32").mkdir(exist_ok=True)
        (self.root / "win32/Makefile.gcc").write_text(
            f"OBJS = {objects}\nOBJA = {assembly}\nCFLAGS = {flags}\nARFLAGS = rcs\n")
        (self.root / "adler32.c").write_text("synthetic source")
        (self.root / "compress.c").write_text("synthetic source")

    def test_upstream_recipe_shape(self):
        self.recipe()
        self.assertEqual(builder.recipe_objects(self.root), ["adler32.o", "compress.o"])

    def test_unknown_flags_require_review(self):
        self.recipe(flags="$(LOC) -O0")
        with self.assertRaisesRegex(ContractError, "compiler flags changed"):
            builder.recipe_objects(self.root)

    def test_assembly_objects_not_silently_omitted(self):
        self.recipe(assembly="assembly.o")
        with self.assertRaisesRegex(ContractError, "object recipe"):
            builder.recipe_objects(self.root)

    def test_duplicate_objects_rejected(self):
        self.recipe(objects="adler32.o adler32.o")
        with self.assertRaisesRegex(ContractError, "duplicate"):
            builder.recipe_objects(self.root)

    def test_object_traversal_rejected(self):
        self.recipe(objects="../adler32.o")
        with self.assertRaisesRegex(ContractError, "Invalid"):
            builder.recipe_objects(self.root)

    def archive(self, machine=0xaa64, duplicate=False, truncate=False):
        obj = self.root / "adler32.o"
        obj.write_bytes(struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, 0, 0) + b"fixture")
        data = obj.read_bytes()
        name = "adler32.o/".ljust(16)
        header = f"{name}{0:<12}{0:<6}{0:<6}{644:<8}{len(data):<10}`\n".encode()
        member = header + data + (b"\n" if len(data) % 2 else b"")
        archive = self.root / "libz.a"
        encoded = b"!<arch>\n" + member * (2 if duplicate else 1)
        archive.write_bytes(encoded[:-3] if truncate else encoded)
        return archive, {"adler32.o": obj}

    def test_exact_arm64_archive_member(self):
        path, objects = self.archive()
        self.assertEqual(set(builder.verify_archive(path, objects)), {"adler32.o"})

    def test_foreign_coff_rejected(self):
        path, objects = self.archive(machine=0x8664)
        with self.assertRaisesRegex(ContractError, "not an ARM64 COFF"):
            builder.verify_archive(path, objects)

    def test_arm64ec_rejected(self):
        path, objects = self.archive(machine=0xa641)
        with self.assertRaisesRegex(ContractError, "not an ARM64 COFF"):
            builder.verify_archive(path, objects)

    def test_archive_member_mutation_rejected(self):
        path, objects = self.archive()
        objects["adler32.o"].write_bytes(b"changed object")
        with self.assertRaisesRegex(ContractError, "differs from its compiled object"):
            builder.verify_archive(path, objects)

    def test_duplicate_archive_member_rejected(self):
        path, objects = self.archive(duplicate=True)
        with self.assertRaisesRegex(ContractError, "duplicate archive"):
            builder.verify_archive(path, objects)

    def test_truncated_archive_rejected(self):
        path, objects = self.archive(truncate=True)
        with self.assertRaisesRegex(ContractError, "beyond the archive"):
            builder.verify_archive(path, objects)

    def test_incomplete_archive_rejected(self):
        path, objects = self.archive()
        objects["compress.o"] = objects["adler32.o"]
        with self.assertRaisesRegex(ContractError, "Incomplete"):
            builder.verify_archive(path, objects)


if __name__ == "__main__":
    unittest.main()
