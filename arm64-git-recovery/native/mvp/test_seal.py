import json
from pathlib import Path
import tempfile
import unittest

from artifact import ArtifactError, sha256
from seal import require_evidence


class SealControls(unittest.TestCase):
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
