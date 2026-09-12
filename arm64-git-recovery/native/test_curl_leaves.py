import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import unittest
from unittest.mock import patch
import uuid

from sources import ContractError, load_lock


spec = importlib.util.spec_from_file_location("curl_leaves", Path(__file__).with_name("build-curl-leaves.py"))
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class CurlLeafControls(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / "fixtures" / f"curl-leaves-controls-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)

    def test_pinned_sources_and_patch_digests(self):
        lock = load_lock(Path(__file__).with_name("curl-leaves.lock.json"))
        self.assertEqual({row["id"]: row["version"] for row in lock["sources"]},
                         {name: value["version"] for name, value in recipe.RECIPES.items()})
        for row in lock["sources"]:
            self.assertRegex(row["recipe_sha256"], "^[0-9a-f]{64}$")
            for source_patch in row["patches"]:
                self.assertRegex(source_patch["sha256"], "^[0-9a-f]{64}$")
        self.assertEqual(len(lock["sources"][2]["patches"]), 1)
        self.assertEqual(len(lock["sources"][3]["patches"]), 2)

    def test_exact_patch_and_manifest(self):
        target = self.root / "source.c"
        target.write_text("before\nold\nafter\n")
        changes = recipe.apply_upstream_patch(self.root,
            "--- a/source.c\n+++ b/source.c\n@@ -8,3 +8,3 @@\n before\n-old\n+new\n after\n")
        self.assertEqual(target.read_text(), "before\nnew\nafter\n")
        self.assertNotEqual(changes[0]["before_sha256"], changes[0]["after_sha256"])

    def test_patch_fuzzy_context_rejected(self):
        (self.root / "source.c").write_text("changed context\nold\n")
        with self.assertRaises(ContractError):
            recipe.apply_upstream_patch(self.root,
                "--- a/source.c\n+++ b/source.c\n@@ -1,2 +1,2 @@\n before\n-old\n+new\n")

    def test_duplicate_patch_context_rejected(self):
        (self.root / "source.c").write_text("old\nold\n")
        with self.assertRaises(ContractError):
            recipe.apply_upstream_patch(self.root,
                "--- a/source.c\n+++ b/source.c\n@@ -1 +1 @@\n-old\n+new\n")

    def test_patch_count_mismatch_rejected(self):
        (self.root / "source.c").write_text("old\n")
        with self.assertRaises(ContractError):
            recipe.apply_upstream_patch(self.root,
                "--- a/source.c\n+++ b/source.c\n@@ -1,2 +1 @@\n-old\n+new\n")

    def test_patch_traversal_rejected(self):
        with self.assertRaises(ContractError):
            recipe.apply_upstream_patch(self.root,
                "--- a/source.c\n+++ b/../source.c\n@@ -1 +1 @@\n-old\n+new\n")

    def test_empty_patch_rejected(self):
        with self.assertRaises(ContractError):
            recipe.apply_upstream_patch(self.root, "")

    def ctest(self, body):
        path = self.root / "ctest.xml"
        path.write_text(body)
        return recipe.ctest_results(path)

    def test_ctest_nonempty_pass(self):
        self.assertEqual(self.ctest('<testsuite><testcase name="real"/></testsuite>'), ["real"])

    def test_empty_ctest_rejected(self):
        with self.assertRaises(ContractError):
            self.ctest("<testsuite/>")

    def test_ctest_failure_error_and_skip_rejected(self):
        for tag in ("failure", "error", "skipped"):
            with self.subTest(tag=tag), self.assertRaises(ContractError):
                self.ctest(f'<testsuite><testcase name="bad"><{tag}/></testcase></testsuite>')

    def api_output(self, module):
        selected = recipe.RECIPES["zstd"]
        text = "".join(f"CASE\t{name}\n" for name in selected["tests"])
        text += "".join(f"BINDING\t{name}\t{module}\n" for name in selected["symbols"])
        return text + "READY\nPASS\n"

    def test_static_binding_to_fixture_required(self):
        executable = self.root / "fixture.exe"
        executable.write_bytes(b"control")
        parsed = recipe.validate_api_output(self.api_output(executable), recipe.RECIPES["zstd"],
                                             "static", executable, self.root)
        self.assertEqual(len(parsed["cases"]), 3)

    def test_shared_binding_to_installed_dll_required(self):
        (self.root / "bin").mkdir()
        dll = self.root / "bin" / "libzstd.dll"
        dll.write_bytes(b"control")
        parsed = recipe.validate_api_output(self.api_output(dll), recipe.RECIPES["zstd"],
                                             "shared", self.root / "fixture.exe", self.root)
        self.assertEqual(len(parsed["bindings"]), 2)

    def test_shared_api_cannot_be_static_fixture(self):
        executable = self.root / "fixture.exe"
        executable.write_bytes(b"control")
        with self.assertRaises(ContractError):
            recipe.validate_api_output(self.api_output(executable), recipe.RECIPES["zstd"],
                                       "shared", executable, self.root)

    def test_banner_or_missing_case_does_not_qualify(self):
        executable = self.root / "fixture.exe"
        executable.write_bytes(b"control")
        for text in ("zstd 1.5.7\nPASS\n", self.api_output(executable).replace("CASE\tcompression-roundtrip-bytes\n", "")):
            with self.subTest(text=text), self.assertRaises(ContractError):
                recipe.validate_api_output(text, recipe.RECIPES["zstd"], "static", executable, self.root)

    def test_scoped_environment_and_job_budget(self):
        with patch.dict(os.environ, {"CC": "clang", "CFLAGS": "-O0", "MSYSTEM": "CLANGARM64",
                                     "LIBRARY_PATH": "foreign", "SystemRoot": str(self.root)}, clear=True):
            env = recipe.clean_environment(self.root, self.root / "cmake.exe",
                                           self.root / "ninja.exe", self.root / "scratch", 4)
            for key in ("CC", "CFLAGS", "MSYSTEM", "LIBRARY_PATH"):
                self.assertNotIn(key, env)
            self.assertEqual(env["CMAKE_BUILD_PARALLEL_LEVEL"], "4")
            self.assertEqual(len(env["PATH"].split(os.pathsep)), 4)
            for jobs in (0, 5, 8):
                with self.assertRaises(ContractError):
                    recipe.clean_environment(self.root, self.root / "cmake.exe",
                                             self.root / "ninja.exe", self.root / "scratch", jobs)

    def archive(self, machine):
        member = struct.pack("<HH", machine, 1) + bytes(16)
        header = b"test.o/         " + b"0           " + b"0     " + b"0     " + b"100644  "
        header += str(len(member)).encode().ljust(10) + b"`\n"
        path = self.root / "libtest.a"
        path.write_bytes(b"!<arch>\n" + header + member)
        return path

    def test_arm64_archive_members(self):
        self.assertEqual(recipe.static_archive(self.archive(0xAA64))["arm64_coff_members"], 1)

    def test_non_arm64_archive_rejected(self):
        for machine in (0x8664, 0xA641, 0x14c):
            with self.subTest(machine=machine), self.assertRaises(ContractError):
                recipe.static_archive(self.archive(machine))

    def test_empty_archive_rejected(self):
        path = self.root / "empty.a"
        path.write_bytes(b"!<arch>\n")
        with self.assertRaises(ContractError):
            recipe.static_archive(path)


if __name__ == "__main__":
    unittest.main()
