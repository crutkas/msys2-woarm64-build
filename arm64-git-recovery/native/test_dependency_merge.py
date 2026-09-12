import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sources import ContractError, digest, inventory


spec = importlib.util.spec_from_file_location("dependency_merge", Path(__file__).with_name("merge-library-stages.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DependencyMergeControls(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="native-dependency-control-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def stage(self, name, files):
        root = self.root / name
        root.mkdir()
        for rel, content in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return root

    def test_same_header_and_distinct_archives(self):
        a = self.stage("static", {"include/x.h": b"same", "lib/libx.a": b"static"})
        b = self.stage("shared", {"include/x.h": b"same", "lib/libx.dll.a": b"import", "bin/x.dll": b"shared"})
        self.assertEqual(module.merge([a, b], self.root / "out"), 4)

    def test_conflicting_binary_rejected(self):
        a = self.stage("a", {"bin/x.dll": b"one"})
        b = self.stage("b", {"bin/x.dll": b"two"})
        with self.assertRaisesRegex(ContractError, "Conflicting library payload"):
            module.merge([a, b], self.root / "out")

    def test_explicit_last_metadata_preserved(self):
        a = self.stage("static", {"lib/cmake/x.cmake": b"static metadata"})
        b = self.stage("shared", {"lib/cmake/x.cmake": b"shared metadata"})
        out = self.root / "out"
        module.merge([a, b], out)
        self.assertEqual((out / "lib/cmake/x.cmake").read_bytes(), b"shared metadata")
        self.assertIn("replaces_metadata_from", out.with_name("out.manifest.json").read_text())

    def test_existing_output_rejected(self):
        a = self.stage("a", {"include/x.h": b"x"})
        out = self.root / "out"
        out.mkdir()
        with self.assertRaises(ContractError):
            module.merge([a], out)

    def test_output_cannot_change_an_input_or_replace_old_evidence(self):
        source = self.stage("source", {"usr/include/x.h": b"header"})
        with self.assertRaises(ContractError):
            module.merge([source], source / "output")
        output = self.root / "out"
        output.with_name("out.manifest.json").write_text("preserved evidence")
        with self.assertRaises(ContractError):
            module.merge([source], output)
        self.assertFalse(output.exists())

    def bound_stage(self, stage, compiler, **changes):
        record = {"status": "native-msys-library-built-checked-bootstrap-driver",
                  "compiler_receipt_sha256": digest(compiler), "files": inventory(stage),
                  "limitations": ["NLS disabled"], "pending": ["Full native child-exit observation"]}
        record.update(changes)
        path = stage.with_name(stage.name + ".result.json")
        path.write_text(json.dumps(record))
        return path

    def test_cohort_binding_preserves_limits_without_new_execution_claim(self):
        source = self.stage("source", {"usr/include/x.h": b"header"})
        compiler = self.root / "compiler.json"
        compiler.write_text("explicit compiler input fixture")
        receipt = self.bound_stage(source, compiler)
        output = self.root / "output"
        module.merge([source], output, manifests=[receipt], compiler_receipt=compiler)
        report = json.loads(output.with_name("output.manifest.json").read_text())
        self.assertEqual(report["compiler_receipt_sha256"], digest(compiler))
        self.assertEqual(report["limitations"], ["NLS disabled"])
        self.assertEqual(report["input_manifests"][0]["pending"], ["Full native child-exit observation"])
        self.assertEqual(report["status"], "cohort-bound-build-dependencies-not-distribution")

    def test_failed_mismatched_or_incomplete_qualification_rejected(self):
        source = self.stage("source", {"usr/include/x.h": b"header"})
        compiler = self.root / "compiler.json"
        compiler.write_text("explicit compiler input fixture")
        receipt = self.bound_stage(source, compiler, status="failed")
        for manifests, producer in (([receipt], compiler), (None, compiler), ([receipt], None), ([], compiler)):
            with self.subTest(manifests=manifests, producer=producer), self.assertRaises(ContractError):
                module.merge([source], self.root / "out", manifests=manifests, compiler_receipt=producer)
        receipt = self.bound_stage(source, compiler, compiler_receipt_sha256="0" * 64)
        with self.assertRaises(ContractError):
            module.merge([source], self.root / "out", manifests=[receipt], compiler_receipt=compiler)
        self.assertFalse((self.root / "out").exists())

    def test_changed_stage_rejected_against_its_build_receipt(self):
        source = self.stage("source", {"usr/include/x.h": b"header"})
        compiler = self.root / "compiler.json"
        compiler.write_text("explicit compiler input fixture")
        receipt = self.bound_stage(source, compiler)
        (source / "usr/include/x.h").write_bytes(b"changed")
        with self.assertRaises(ContractError):
            module.merge([source], self.root / "out", manifests=[receipt], compiler_receipt=compiler)

    def test_required_empty_runtime_directories_survive(self):
        source = self.stage("source", {"usr/bin/sh.exe": b"fixture"})
        (source / "tmp").mkdir()
        (source / "var/tmp").mkdir(parents=True)
        output = self.root / "output"
        self.assertEqual(module.merge([source], output), 1)
        self.assertTrue((output / "tmp").is_dir())
        self.assertTrue((output / "var/tmp").is_dir())

    def test_info_collision_requires_explicit_generator(self):
        a = self.stage("a", {"share/info/dir": b"a", "share/info/a.info": b"a manual"})
        b = self.stage("b", {"share/info/dir": b"b", "share/info/b.info": b"b manual"})
        with self.assertRaises(ContractError):
            module.merge([a, b], self.root / "out")

    def test_info_index_is_regenerated_from_all_manuals(self):
        a = self.stage("a", {"share/info/dir": b"a", "share/info/a.info": b"a manual"})
        b = self.stage("b", {"share/info/dir": b"b", "share/info/b.info": b"b manual"})
        generator = self.root / "install-info-control"
        generator.write_bytes(b"unit-test fixture")
        output = self.root / "out"

        def generate(command, **kwargs):
            index = Path(command[1].removeprefix("--dir-file="))
            previous = index.read_text() if index.exists() else ""
            index.write_text(previous + Path(command[2]).name + "\n")
            return SimpleNamespace(stdout="", stderr="")

        with patch.object(module.subprocess, "run", side_effect=generate):
            self.assertEqual(module.merge([a, b], output, generator), 3)
        self.assertEqual((output / "share/info/dir").read_text(), "a.info\nb.info\n")


if __name__ == "__main__":
    unittest.main()
