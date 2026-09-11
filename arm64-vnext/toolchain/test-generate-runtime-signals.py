#!/usr/bin/env python3
"""Run signal-generation guard regressions without compilers or runtime writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("generate-runtime-signals.py")
SPEC = importlib.util.spec_from_file_location("signal_generation", SCRIPT)
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)

FIELDS = {"start_offset": -256, "initialized": -16, "stack": -56, "stackptr": -64,
          "stacklock": -72, "incyg": -76, "current_sig": -80, "errno_addr": -88,
          "saved_errno": -96, "context": -240}
PUBLIC = {"_sigfe_test", "_sigbe", "sigdelayed", "_sigdelayed_end",
          "sigsetjmp", "siglongjmp", "setjmp", "longjmp"}
INTERNAL = {"_sigfe", "_sigfe_maybe", "stabilize_sig_stack"}
ASSEMBLY = "\n".join(f".global {name}\n{name}:\n  ret" for name in sorted(PUBLIC))
ASSEMBLY += "\n" + "\n".join(name + ":\n  ret" for name in sorted(INTERNAL)) + "\n"
EXPORTS = "LIBRARY test\nEXPORTS\ntest = _sigfe_test\n"


def offsets(fields=None):
    values = FIELDS if fields is None else fields
    rows = []
    for name, value in values.items():
        rows.append(f".equ _cygtls.{name}, {value}")
        if name != "start_offset":
            rows.append(f".equ _cygtls.{name}_p, {value - values['start_offset']}")
    return "\n".join(rows) + "\n"


class ValidationTests(unittest.TestCase):
    def test_valid_offsets(self):
        actual = GEN.validate_offsets(offsets())
        self.assertEqual(actual["_cygtls.stackptr_p"], 192)

    def test_zero_offsets_rejected(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            GEN.validate_offsets(offsets({name: 0 for name in FIELDS}))

    def test_malformed_row_rejected(self):
        with self.assertRaisesRegex(ValueError, "Malformed"):
            GEN.validate_offsets(offsets() + ".equ _cygtls.extra, nope\n")

    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            GEN.validate_offsets(offsets() + ".equ _cygtls.stackptr, -64\n")

    def test_inconsistent_pair_rejected(self):
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            GEN.validate_offsets(offsets().replace("stackptr_p, 192", "stackptr_p, 191"))

    def test_missing_pair_rejected(self):
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            GEN.validate_offsets(offsets().replace(".equ _cygtls.incyg_p, 180\n", ""))

    def test_orphan_pair_rejected(self):
        with self.assertRaisesRegex(ValueError, "no field"):
            GEN.validate_offsets(offsets() + ".equ _cygtls.extra_p, 12\n")

    def test_misaligned_context_rejected(self):
        with self.assertRaisesRegex(ValueError, "Misaligned"):
            GEN.validate_offsets(offsets({**FIELDS, "context": -239}))

    def test_invalid_stack_rejected(self):
        with self.assertRaisesRegex(ValueError, "signal-stack"):
            GEN.validate_offsets(offsets({**FIELDS, "stackptr": -80}))

    def test_missing_required_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "signal ABI"):
            GEN.validate_offsets(offsets({k: v for k, v in FIELDS.items() if k != "saved_errno"}))

    def test_valid_assembly(self):
        required, _ = GEN.validate_assembly(ASSEMBLY, EXPORTS)
        self.assertEqual(required, {"_sigfe_test"})

    def test_missing_export_label_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            GEN.validate_assembly(ASSEMBLY.replace("_sigfe_test:", "_wrong:"), EXPORTS)

    def test_missing_core_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            GEN.validate_assembly(ASSEMBLY.replace("_sigbe:", "_wrong:"), EXPORTS)

    def test_duplicate_label_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            GEN.validate_assembly(ASSEMBLY + "_sigbe:\n", EXPORTS)

    def test_unexported_label_rejected(self):
        with self.assertRaisesRegex(ValueError, "externally visible"):
            GEN.validate_assembly(ASSEMBLY.replace(".global _sigfe_test\n", ""), EXPORTS)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="signal-generation-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / "winsup/cygwin/scripts").mkdir(parents=True)
        self.generator = self.source / "winsup/cygwin/scripts/gendef"
        self.exports = self.source / "winsup/cygwin/cygwin.din"
        self.exports.write_text("test\n")
        self.offsets = self.root / "tlsoffsets"
        self.offsets.write_text(offsets())
        self.output = self.root / "generated"

    def run_generator(self, assembly=ASSEMBLY, exit_code=0, extra="", expected_hash=None):
        # Python stands in for the generator process only; its output is never
        # built or represented as runtime evidence.
        self.generator.write_text(
            "from pathlib import Path\nimport sys\n"
            "destination = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--output-def='))\n"
            f"Path(destination).write_text({EXPORTS!r})\n"
            f"Path('sigfe.s').write_text({assembly!r})\n"
            + extra + f"\nraise SystemExit({exit_code})\n")
        command = [sys.executable, "-B", str(SCRIPT), "--source", str(self.source),
                   "--offsets", str(self.offsets), "--offsets-sha256",
                   expected_hash or hashlib.sha256(self.offsets.read_bytes()).hexdigest(),
                   "--output", str(self.output), "--perl", sys.executable]
        return subprocess.run(command, capture_output=True, text=True, timeout=15)

    def test_success_and_input_identity(self):
        original = self.offsets.read_bytes()
        result = self.run_generator()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.offsets.read_bytes(), original)
        report = json.loads((self.output / "result.json").read_text())
        self.assertEqual(report["export_trampolines"], 1)
        self.assertFalse(report["make_invoked"])

    def test_zero_exit_empty_assembly_rejected(self):
        result = self.run_generator(assembly="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no assembly", result.stderr)
        report = json.loads((self.output / "result.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["commands"][0]["exit"], 0)

    def test_nonzero_generator_rejected(self):
        result = self.run_generator(exit_code=19)
        self.assertNotEqual(result.returncode, 0)
        report = json.loads((self.output / "result.json").read_text())
        self.assertEqual(report["commands"][0]["exit"], 19)

    def test_working_offsets_drift_rejected(self):
        result = self.run_generator(extra="Path('tlsoffsets').write_text('corrupt')\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Working TLS offsets changed", result.stderr)
        self.assertEqual(self.offsets.read_text(), offsets())

    def test_source_offsets_drift_rejected(self):
        result = self.run_generator(extra=f"Path({str(self.offsets)!r}).write_text('drift')\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Source input changed", result.stderr)

    def test_existing_outputs_never_overwritten(self):
        self.output.mkdir()
        good = self.output / "tlsoffsets"
        good.write_bytes(b"preserved")
        result = self.run_generator()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(good.read_bytes(), b"preserved")
        self.assertFalse((self.output / "sigfe.s").exists())

    def test_wrong_input_hash_prevents_generation(self):
        result = self.run_generator(expected_hash="0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_missing_export_is_not_success(self):
        result = self.run_generator(assembly=ASSEMBLY.replace("_sigfe_test:", "_wrong:"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads((self.output / "result.json").read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
