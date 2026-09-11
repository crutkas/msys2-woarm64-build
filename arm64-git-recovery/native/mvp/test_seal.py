import copy
import json
from pathlib import Path
import tempfile
import unittest

from artifact import ArtifactError, sha256
from seal import bind_evidence, bind_plan, require_evidence


class SealControls(unittest.TestCase):
    def test_evidence_must_describe_the_actual_payload_and_complete_replay(self):
        files = {"usr/bin/msys-2.0.dll": {"sha256": "runtime"}, "usr/bin/ssh.exe": {"sha256": "client"}}
        cases = [[str(index), "PASS"] for index in range(12)]
        checkpoint = {"native_process": {"Passed": True}, "modules": [{
            "location": "payload", "payload_path": "usr/bin/msys-2.0.dll",
            "machine": "0xAA64", "sha256": "runtime"}]}
        results = {
            "observer": {"source_manifest": {name: row["sha256"] for name, row in files.items()},
                         "observer_passed": True, "created_processes": 2, "observed_processes": 2, "cases": cases},
            "behavior": {"runtime_sha256": "runtime", "cases": cases},
            "ssh": {"client_sha256": "client"},
            "independent_replay": {"candidate_manifest_sha256": "manifest", "original_candidate_unchanged": True,
                                   "private_candidate_unchanged": True, "owned_jobs_drained": True},
            "entrypoints": {"cases": [{"name": name, **copy.deepcopy(checkpoint)}
                                     for name in ("bash", "git", "https-helper", "python")]}}
        bind_evidence(results, files, "manifest")
        changes = [("observer", "source_manifest", {}), ("observer", "observed_processes", 1),
                   ("behavior", "runtime_sha256", "old"), ("behavior", "cases", cases[:-1]),
                   ("ssh", "client_sha256", "other"), ("independent_replay", "owned_jobs_drained", False),
                   ("independent_replay", "candidate_manifest_sha256", "other"),
                   ("entrypoints", "cases", [])]
        for section, key, value in changes:
            changed = copy.deepcopy(results)
            changed[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ArtifactError):
                bind_evidence(changed, files, "manifest")
        changed = copy.deepcopy(results)
        changed["entrypoints"]["cases"][0]["modules"][0]["sha256"] = "different"
        with self.assertRaises(ArtifactError):
            bind_evidence(changed, files, "manifest")

    def test_plan_binding_preserves_receipts_and_rejects_changed_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "receipt.json"
            receipt.write_text(json.dumps({"verdict": "ADMITTED", "limits": ["C locale only"]}))
            item = {"path": str(receipt), "sha256": sha256(receipt)}
            provenance = {"source": {"commit": "example"}, "admission_receipt_sha256": item["sha256"]}
            plan = {"top_source": {"commit": "recipe"}, "limitations": ["C locale only"],
                    "components": [{"id": "utility", "provenance": provenance, "receipts": [item]}]}
            assembly = {"top_source": plan["top_source"], "limitations": plan["limitations"],
                        "files": {"usr/bin/tool.exe": {"components": ["utility"], "provenance": provenance}}}
            records, components = bind_plan(assembly, plan)
            self.assertEqual(records[item["sha256"]]["limits"], ["C locale only"])
            self.assertEqual(components, {"utility": provenance})
            for changed in ({"components": []}, {"components": ["unknown"]},
                            {"provenance": {"source": {"commit": "different"}}}):
                row = {**assembly["files"]["usr/bin/tool.exe"], **changed}
                with self.subTest(changed=changed), self.assertRaises(ArtifactError):
                    bind_plan({**assembly, "files": {"usr/bin/tool.exe": row}}, plan)
            with self.assertRaises(ArtifactError):
                bind_plan(assembly, {**plan, "components": plan["components"] * 2})
            with self.assertRaises(ArtifactError):
                bind_plan({**assembly, "limitations": []}, plan)
            receipt.write_text(json.dumps({"verdict": "REVOKED"}))
            with self.assertRaises(ArtifactError):
                bind_plan(assembly, plan)

    def test_missing_failed_or_unauthorized_evidence_cannot_emit_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof = root / "proof.json"
            proof.write_text(json.dumps({"passed": True}))
            item = {"path": str(proof), "sha256": sha256(proof)}
            spec = {"publication_authorized": True, "evidence": {
                name: item for name in ("behavior", "observer", "ssh", "entrypoints", "independent_replay")}}
            self.assertEqual(len(require_evidence(spec)), 5)
            spec["publication_authorized"] = False
            with self.assertRaises(ArtifactError):
                require_evidence(spec)
            spec["publication_authorized"] = True
            del spec["evidence"]["observer"]
            with self.assertRaises(ArtifactError):
                require_evidence(spec)
            spec["evidence"]["observer"] = item
            proof.write_text(json.dumps({"passed": False}))
            item["sha256"] = sha256(proof)
            with self.assertRaises(ArtifactError):
                require_evidence(spec)


if __name__ == "__main__":
    unittest.main()
