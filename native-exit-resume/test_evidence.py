import copy
import unittest

from evidence import check_alias, check_case, check_matrix, generation_join
from resume import ROOT, digest, load, verify_inputs


class ResumedEvidenceTests(unittest.TestCase):
    def test_unchanged_binary_and_runtime_substitution_still_fail_debug(self):
        for name, expected in (("baseline-ordinary-01", 0), ("baseline-debug-01", 0xC00000FF),
                               ("baseline-no-context-01", 0xC00000FF), ("d70-ordinary-01", 0),
                               ("d70-debug-01", 0xC00000FF)):
            with self.subTest(name=name):
                _, native = check_case(name)
                self.assertEqual([row["raw_exit"] for row in native["native_target_exits"]], [expected])

    def test_saved_frame_alias_confirmed_in_both_runtime_cohorts(self):
        for name in ("baseline-probe-02", "d70-probe-01"):
            with self.subTest(name=name):
                self.assertTrue(check_alias(name)["all_instructions_restored"])

    def test_invalid_first_probe_is_not_reclassified(self):
        _, native = check_case("baseline-probe-01")
        self.assertEqual([row["raw_exit"] for row in native["native_target_exits"]], [0xC000001D])
        with self.assertRaises(ValueError):
            check_alias("baseline-probe-01")

    def test_matched_relinks_and_exact_source_delta(self):
        for cohort in ("relink", "scratch", "source-control", "source-fixed"):
            for mode in ("ordinary", "debug"):
                name = f"{cohort}-{mode}-01"
                expected = 0xC00000FF if mode == "debug" and cohort in ("relink", "source-control") else 0
                with self.subTest(name=name):
                    _, native = check_case(name)
                    self.assertEqual([row["raw_exit"] for row in native["native_target_exits"]], [expected])

    def test_no_context_read_is_not_a_fix_or_a_prerequisite(self):
        for name, expected in (("baseline-no-context-01", 0xC00000FF), ("scratch-no-context-01", 0),
                               ("source-fixed-no-context-01", 0)):
            _, native = check_case(name)
            debug = load(ROOT / "cases" / name / "debug/result.json")
            self.assertFalse(debug["context_reads_enabled"])
            self.assertEqual([row["raw_exit"] for row in native["native_target_exits"]], [expected])
            self.assertTrue(all(not row["context"]["requested"] for row in debug["events"] if "context" in row))

    def test_both_complete_matrices_keep_genuine_failures(self):
        for name in ("matrix-result.json", "source-matrix-result.json"):
            with self.subTest(name=name):
                self.assertEqual(len(check_matrix(ROOT / name)["controls"]), 30)

    def test_generation_join_rejects_stale_duplicate_and_swapped_records(self):
        native = load(ROOT / "cases/matrix-scratch-cleanup-fork-debug-01/native-job.json")
        debug = load(ROOT / "cases/matrix-scratch-cleanup-fork-debug-01/debug/result.json")
        generation_join(native, debug)
        for mutate in ("stale", "duplicate", "raw", "domain", "bool"):
            candidate = copy.deepcopy(debug)
            if mutate == "stale":
                candidate["processes"][0]["created"] += 1
            elif mutate == "duplicate":
                candidate["processes"].append(copy.deepcopy(candidate["processes"][0]))
            elif mutate == "raw":
                candidate["processes"][0]["raw_exit"] = 256
            elif mutate == "domain":
                candidate["processes"][0]["encoding"] = "registeredMSYS"
            else:
                candidate["processes"][0]["pid"] = True
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                generation_join(native, candidate)

    def test_original_inputs_and_old_blocker_are_immutable(self):
        verify_inputs()
        old = load(ROOT.parent / "result.json")
        self.assertEqual(old["status"], "BLOCKED-debugger-launch-semantic-divergence")
        self.assertFalse(old["qualified"])

    def test_exact_source_change_is_arm64_local_scratch_only(self):
        original = ROOT / "source-build/closure/source/libgcc/unwind-seh.c"
        patched = ROOT / "source-build/patched/libgcc/unwind-seh.c"
        addition = (
            "#if defined (__aarch64__)\n"
            "  /* RtlUnwindEx writes its context argument.  On ARM64 the incoming context\n"
            "     can be the saved dispatcher frame that phase 2 must still restore.  */\n"
            "  CONTEXT ms_unwind_context = *ms_orig_context;\n"
            "  ms_orig_context = &ms_unwind_context;\n"
            "#endif\n\n"
        )
        text = patched.read_text()
        self.assertEqual(text.count(addition), 1)
        self.assertEqual(text.replace(addition, "", 1), original.read_text())
        built = load(ROOT / "source-build/result.json")
        self.assertEqual(digest(original), built["source_before_sha256"])
        self.assertEqual(digest(patched), built["source_after_sha256"])
        self.assertFalse(built["producer_sdk_libraries_modified"])


if __name__ == "__main__":
    unittest.main()
