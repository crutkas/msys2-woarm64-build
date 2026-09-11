import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "patch-libtool-native-tests.py"
SPEC = importlib.util.spec_from_file_location("patch_libtool_native_tests", SCRIPT)
PATCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCHER)


class LibtoolNativeInstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.source = self.output / "build" / "libtool"
        (self.source / "tests").mkdir(parents=True)
        self.texts = {
            "testsuite.at": '. "$abs_top_srcdir/build-aux/extract-trace"\n'
                            'AT_CHECK([if "$lt_exe" $5; then expected_assertion; fi], [1])\n',
            "demo.at": "./hell$EXEEXT\n" * 2 + "LT_AT_CHECK([./hell], [1])\n" * 2,
            "depdemo.at": "./depdemo$EXEEXT\n" * 4 + "LT_AT_CHECK([./depdemo], [1])\n",
        }
        self.pins = {}
        for name, text in self.texts.items():
            data = text.encode("utf-8")
            (self.source / "tests" / name).write_bytes(data)
            self.pins[name] = hashlib.sha256(data).hexdigest()

    def run_patch(self, source=None):
        with patch.object(PATCHER, "PINS", self.pins), \
             patch.dict(os.environ, {"WOARM64_OUTPUT_ROOT": str(self.output)}), \
             patch.object(sys, "argv", [str(SCRIPT), str(source or self.source)]):
            PATCHER.main()

    def test_calls_are_relayed_without_changing_expected_assertions(self):
        self.run_patch()
        suite = (self.source / "tests" / "testsuite.at").read_text()
        self.assertIn('AT_CHECK([if lt_at_native_exec "$lt_exe" $5; then expected_assertion; fi], [1])', suite)
        self.assertIn('"$CONFIG_SHELL" "$WOARM64_NATIVE_EXEC" "$lt_at_native_file" "[$]@"', suite)
        self.assertNotIn("MSYS2_ARG_CONV_EXCL", suite)
        for name, command, count in (("demo.at", "./hell", 4), ("depdemo.at", "./depdemo", 5)):
            text = (self.source / "tests" / name).read_text()
            self.assertEqual(text.count("lt_at_native_exec " + command), count)
            self.assertEqual(text.count("[1]"), self.texts[name].count("[1]"))

    def test_changed_pin_rejects_before_any_source_write(self):
        path = self.source / "tests" / "depdemo.at"
        path.write_bytes(path.read_bytes() + b"changed\n")
        before = {p.name: p.read_bytes() for p in (self.source / "tests").iterdir()}
        with self.assertRaisesRegex(SystemExit, "Pinned libtool test source changed"):
            self.run_patch()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.source / "tests").iterdir()})

    def test_changed_anchor_rejects_before_any_source_write(self):
        path = self.source / "tests" / "depdemo.at"
        data = path.read_bytes().replace(b"LT_AT_CHECK", b"CHANGED_CHECK")
        path.write_bytes(data)
        self.pins[path.name] = hashlib.sha256(data).hexdigest()
        before = {p.name: p.read_bytes() for p in (self.source / "tests").iterdir()}
        with self.assertRaisesRegex(ValueError, "anchor count changed"):
            self.run_patch()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.source / "tests").iterdir()})

    def test_repeated_instrumentation_is_rejected(self):
        self.run_patch()
        with self.assertRaisesRegex(SystemExit, "Pinned libtool test source changed"):
            self.run_patch()

    def test_source_outside_invocation_build_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "fresh invocation"):
            self.run_patch(self.output)


if __name__ == "__main__":
    unittest.main()
