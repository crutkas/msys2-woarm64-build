import copy
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from artifact import ArtifactError
from hook_contract import (CASE, HOOK_BYTES, PHASE_SHA256, check_causality, check_inputs,
                           locked_inputs, make_binding, require_exact_delta)


class HookFixtureControls(unittest.TestCase):
    def test_only_the_exact_phase_may_gain_protection(self):
        class Matcher:
            @staticmethod
            def unprotected_native_exits(records, relays, contracts):
                return [] if CASE in contracts else records

        phase = {"pid": 2, "created": 102}
        contract = {CASE: {}}
        require_exact_delta(Matcher, [phase], {}, contract, (2, 102))
        with self.assertRaises(ArtifactError):
            require_exact_delta(Matcher, [phase, {"pid": 3, "created": 103}], {}, contract, (2, 102))

    def fixture(self, directory):
        root = directory / "root"
        for name in ("usr/bin", "mingwarm64/bin", "etc"):
            (root / name).mkdir(parents=True, exist_ok=True)
        for name in ("usr/bin/msys-exit-contract.exe", "usr/bin/bash.exe", "usr/bin/sh.exe",
                     "usr/bin/msys-2.0.dll", "mingwarm64/bin/git.exe"):
            (root / name).write_bytes(b"unit-test data, never executed")
        sources = Path(__file__).parent
        shutil.copyfile(sources / "payload/etc/fstab", root / "etc/fstab")
        phase = directory / "phase.sh"
        shutil.copyfile(sources / "negative_hook_phase.sh", phase)
        behavior = directory / "behavior.sh"
        shutil.copyfile(sources / "behavior.sh", behavior)
        return make_binding(root, phase, behavior, directory / "work", "f" * 64)

    def test_phase_source_and_asset_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            binding = self.fixture(directory)
            self.assertEqual(binding["contracts"][CASE]["probe_source_sha256"], PHASE_SHA256)
            self.assertEqual(binding["contracts"][CASE]["raw_exit"], 256)
            self.assertEqual(binding["fixture"]["helper_source_sha256"], "f" * 64)
            check_inputs(binding)
            Path(binding["fixture"]["assets"]["git"]["path"]).write_bytes(b"changed")
            with self.assertRaises(ArtifactError):
                check_inputs(binding)
            phase = directory / "phase.sh"
            phase.write_bytes(b"exit 1\n")
            with self.assertRaises(ArtifactError):
                make_binding(directory / "root", phase, directory / "behavior.sh", directory / "work", "f" * 64)

    def test_causal_graph_requires_real_hook_status_marker_and_unchanged_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            binding = self.fixture(Path(temporary))
            assets = binding["fixture"]["assets"]
            helper = {"pid": 1, "created": 101, "raw_exit": 0, "executable": assets["helper"]["path"]}
            phase = {"pid": 2, "created": 102, "parent_pid": 1, "parent_created": 101,
                     "raw_exit": 256, "executable": assets["bash"]["path"],
                     "portable_exit": 1, "expected_exit_contract": CASE}
            git = {"pid": 3, "created": 103, "parent_pid": 2, "parent_created": 102,
                   "raw_exit": 1, "executable": assets["git"]["path"]}
            hook = {"pid": 4, "created": 104, "parent_pid": 3, "parent_created": 103,
                    "raw_exit": 73, "executable": assets["sh"]["path"]}
            observed = {"expected_probe_exits": [phase], "native_target_exits": [helper, phase, git, hook]}
            proof = ["1" * 40, "1" * 40, "negative-hook-executed"]
            hook_sha = hashlib.sha256(HOOK_BYTES).hexdigest()
            check_causality(observed, binding, binding["fixture"]["argv"], proof, hook_sha)
            for index, key, value in ((0, "raw_exit", 1), (2, "raw_exit", 0), (3, "raw_exit", 0),
                                      (3, "parent_created", 999)):
                changed = copy.deepcopy(observed)
                changed["native_target_exits"][index][key] = value
                with self.subTest(index=index, key=key), self.assertRaises(ArtifactError):
                    check_causality(changed, binding, binding["fixture"]["argv"], proof, hook_sha)
            with self.assertRaises(ArtifactError):
                check_causality(observed, binding, ["wrong"], proof, hook_sha)
            with self.assertRaises(ArtifactError):
                check_causality(observed, binding, binding["fixture"]["argv"], [proof[0], "2" * 40, proof[2]], hook_sha)

    @unittest.skipUnless(os.name == "nt", "Windows sharing contract")
    def test_read_lock_prevents_source_replacement_during_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.sh"
            path.write_bytes(b"original")
            with locked_inputs([path]):
                self.assertEqual(path.read_bytes(), b"original")
                with self.assertRaises(OSError):
                    path.write_bytes(b"changed")
            self.assertEqual(path.read_bytes(), b"original")
            path.write_bytes(b"changed")


if __name__ == "__main__":
    unittest.main()
