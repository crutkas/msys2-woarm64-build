import json
from pathlib import Path
import tempfile
import unittest

from artifact import ArtifactError, sha256
from limited_plan import add_projection


class LimitedAdmissionControls(unittest.TestCase):
    def test_status_cannot_override_a_negative_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = {"status": "admitted-limited-mvp-only-final",
                      "verdict": {"limitedGitMvp": "NOT_ADMITTED"}}
            path = root / "export.json"
            path.write_text(json.dumps(record))
            with self.assertRaises(ArtifactError):
                add_projection({"components": [], "limitations": []}, {"path": str(path), "sha256": sha256(path)})

    def test_exact_admitted_bytes_and_limitations_are_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload/usr/data"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"fixture")
            record = {"status": "admitted-limited-mvp-only-final", "exportRole": "fixture",
                      "verdict": {"limitedGitMvp": "ADMITTED"}, "exportRoot": str(root),
                      "limitations": ["Not a full provider"],
                      "payload": {"files": [{"path": "payload/usr/data", "sha256": sha256(payload), "bytes": 7}]}}
            path = root / "export.json"
            path.write_text(json.dumps(record))
            plan = {"components": [], "limitations": []}
            item = {"path": str(path), "sha256": sha256(path)}
            add_projection(plan, item)
            self.assertEqual(plan["components"][0]["destination"], "usr/data")
            self.assertEqual(plan["limitations"], ["Not a full provider"])
            payload.write_bytes(b"changed")
            with self.assertRaises(ArtifactError):
                add_projection({"components": [], "limitations": []}, item)


if __name__ == "__main__":
    unittest.main()
