import copy
import ctypes
import sys
import unittest

from prepare import ROOT, digest
from report import load, validate_raw_record

sys.path.insert(0, str(ROOT / "support"))


class EvidenceTests(unittest.TestCase):
    def test_exact_same_binary_diverges_without_context_reads(self):
        pair = load(ROOT / "cases/cpp-exception-no-context-parity.json")
        self.assertTrue(pair["ordinary"]["full_observation"])
        self.assertTrue(pair["debug"]["full_observation"])
        self.assertEqual(pair["ordinary"]["raw_exits"], [0])
        self.assertEqual(pair["debug"]["raw_exits"], [0xC00000FF])
        self.assertFalse(pair["behavioral_exit_parity"])
        debug = load(ROOT / "cases/cpp-exception-no-context-debug/debug/result.json")
        self.assertFalse(debug["context_reads_enabled"])
        self.assertFalse(debug["memory_writes"])
        self.assertFalse(debug["register_writes"])
        self.assertEqual(debug["processes"][0]["image"]["mapped_file_sha256"],
                         digest(ROOT / "runtime/usr/bin/exception-fixture.exe"))

    def test_colliding_same_topologies_are_not_decoded(self):
        for name, expected in (("msys-fork-one", [0, 256]), ("winapi-fork-256", [0, 256]),
                               ("msys-fork-six", [0, 1536]), ("winapi-fork-1536", [0, 1536])):
            debug = load(ROOT / "cases" / f"{name}-r2-debug" / "debug/result.json")
            self.assertFalse(debug["qualified"])
            self.assertFalse(debug["exit_decoding_enabled"])
            self.assertEqual(sorted(validate_raw_record(row) for row in debug["processes"]), expected)

    def test_high_overlay_target_survives_zero_helper(self):
        for code in (256, 1536):
            debug = load(ROOT / "cases" / f"overlay-{code}-r2-debug" / "debug/result.json")
            self.assertEqual(sorted(validate_raw_record(row) for row in debug["processes"]), [0, 0, code])

    def test_forged_strace_is_untrusted(self):
        debug = load(ROOT / "cases/forged-fork-256-r2-debug/debug/result.json")
        strings = [row["debug_string"] for row in debug["events"] if row["event"] == 8]
        self.assertTrue(any(b"Calling ExitProcess" in bytes.fromhex(row["bytes"]) for row in strings))
        self.assertTrue(all(row["trusted_exit_evidence"] is False for row in strings))
        for record in debug["processes"]:
            validate_raw_record(record)

    def test_unqualified_domain_and_lossy_status_rejected(self):
        original = load(ROOT / "cases/msys-fork-one-r2-debug/debug/result.json")["processes"][1]
        for key, value in (("encoding", "registeredMSYS"), ("role", "exec-relay"), ("decoded_status", 1),
                           ("terminal_evidence", {"forged": True}), ("raw_exit", -1),
                           ("raw_exit", 2 ** 32), ("created", 0), ("pid", True),
                           ("event_matches_handle_exit", False)):
            record = copy.deepcopy(original)
            record[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_raw_record(record)

    def test_process_local_error_mode_restores(self):
        from native_job_runner import noninteractive_error_mode
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetErrorMode.restype = ctypes.c_uint
        before = kernel.GetErrorMode()
        with noninteractive_error_mode():
            self.assertEqual(kernel.GetErrorMode() & 0x8003, 0x8003)
        self.assertEqual(kernel.GetErrorMode(), before)

    def test_result_is_blocked_and_every_sealed_identity_matches(self):
        result = load(ROOT / "result.json")
        self.assertTrue(result["status"].startswith("BLOCKED-"))
        self.assertFalse(result["qualified"])
        self.assertFalse(result["promoted"])
        self.assertFalse(result["exit_decoding_enabled"])
        self.assertEqual(result["drain"]["created"], result["drain"]["observed"])
        self.assertEqual(result["drain"]["active_owned_jobs"], 0)
        identities = load(result["before_after_identities"]["path"])
        self.assertTrue(identities["all_unchanged"])
        self.assertTrue(all(row["before"] == row["after"] for row in identities["files"].values()))
        self.assertEqual(digest(result["before_after_identities"]["path"]),
                         result["before_after_identities"]["sha256"])
        self.assertGreater(len(result["unqualified_required_matrix_rows"]), 0)


if __name__ == "__main__":
    unittest.main()
