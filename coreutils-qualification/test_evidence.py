import unittest

from evidence import check_package, check_positive
from qualify import ROOT, CORE_NAMES, EXTRA_NAMES, load
from pe_closure import Image, PeError


class UtilityEvidenceTests(unittest.TestCase):
    def test_every_named_candidate_is_real_arm64(self):
        inputs = load(ROOT / "inputs.json")
        self.assertEqual(inputs["missing"], [])
        self.assertEqual(len(inputs["programs"]), 40)
        for record in inputs["programs"]:
            image = Image(record["path"])
            self.assertEqual(image.machine, 0xAA64)
            self.assertEqual(image.magic, 0x20B)
            self.assertEqual(image.sha256, record["sha256"])
            self.assertFalse(image.characteristics & 0x2000)
            self.assertTrue(any(row["module"] == "msys-2.0.dll" for row in image.imports()))

    def test_all_projection_commands_pass_in_both_locations(self):
        names = [name for name in CORE_NAMES if name not in ("chmod", "stty", "false")] + EXTRA_NAMES
        self.assertEqual(len(names), 37)
        for name in names + ["pipeline"]:
            for prefix, suffix in (("private", "03"), ("moved", "01")):
                with self.subTest(utility=name, root=prefix):
                    check_positive(f"{prefix}-{name}-{suffix}")

    def test_genuine_failures_and_mode_limitations_are_not_hidden(self):
        false = load(ROOT / "cases/private-false-03/result.json")
        self.assertEqual(false["status"], "failed")
        self.assertTrue(any(row["raw_exit"] == 1 for row in false["raw_generation_exits"]))
        chmod = load(ROOT / "cases/private-chmod-03/result.json")
        self.assertEqual(chmod["status"], "failed")
        self.assertEqual(chmod["stdout"], "644\n")
        self.assertTrue(all(row["raw_exit"] == 0 for row in chmod["raw_generation_exits"]))
        check_positive("private-chmod-basic-03")
        stty = load(ROOT / "cases/private-stty-03/result.json")
        self.assertEqual(stty["status"], "failed")
        self.assertIn("Inappropriate ioctl", stty["stderr"])
        pty = load(ROOT / "cases/private-stty-pty-03/result.json")
        self.assertEqual(pty["status"], "failed")
        self.assertEqual(pty["stdout"], "24 80\n")
        self.assertTrue(pty["mapped_failures"])
        with self.assertRaises(ValueError):
            check_positive("private-stty-pty-03")

    def test_archives_are_exact_limited_projections(self):
        core = load(ROOT / "package/candidate.json")
        records = [core, *load(ROOT / "extra-candidates.json")]
        self.assertEqual(len(core["commands"]), 34)
        self.assertEqual(set(core["held_out"]), {"chmod", "stty", "false"})
        for record in records:
            inventory = check_package(record)
            self.assertEqual(sorted(PathName(name) for name in inventory if name.endswith(".exe")),
                             sorted(record["commands"]))
            self.assertTrue(any("/COPYING" in name for name in inventory))

    def test_required_closure_and_optional_os_boundaries_stay_distinct(self):
        required = load(ROOT / "closure-04-required.json")
        self.assertTrue(required["complete"])
        self.assertFalse(required["failures"])
        self.assertTrue(required["deferred_system_imports"])
        self.assertTrue(all(row["machine"] == "0xAA64" for row in required["images"]))
        expanded = load(ROOT / "closure-02.json")
        self.assertFalse(expanded["complete"])
        self.assertTrue(expanded["failures"])
        for utility in ("sed", "find", "xargs"):
            self.assertTrue(any(row["classification"] == "operational-path-review"
                                for row in required["path_scan"][utility]))

    def test_pe_bounds_fail_closed_and_long_debug_names_resolve(self):
        image = Image.__new__(Image)
        image.data = b"abc"
        with self.assertRaises(PeError):
            image.unpack("<Q", 0)
        actual = Image(ROOT / "private/usr/bin/cat.exe")
        self.assertTrue(any(section["name"].startswith(".debug") for section in actual.sections))

    def test_all_recorded_job_trees_are_drained(self):
        for path in (ROOT / "cases").glob("*/result.json"):
            record = load(path)
            self.assertFalse(record["launch"]["timed_out"])
            self.assertEqual(record["launch"]["active_at_boundary"], 0)


def PathName(name):
    return name.rsplit("/", 1)[-1][:-4]


if __name__ == "__main__":
    unittest.main()
