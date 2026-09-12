"""Bind a producer-fixed verifier separately from the unchanged901256b final artifact."""

import argparse
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(r"C:\ag-mvp-independent-sqlite-20260911")
CONTROLLER = ROOT / "final_zip_replay.py"
CONTROLLER_SHA = "2692d1a32033afefa0fde351fbdb2f6dbcf2796666c33b3ea637481c13fee0ec"
OLD = ROOT / "final-901256b-01"
FAILURES = {
    OLD / "result.json": "73693c7738c354b20b9b65d7d1445b593ac19d28ac019f7fb26460b1418a8d62",
    OLD / "final ZIP verification/result.json": "4cfb61cad7d87e1ac87d69d56f7217c0db97ab0363fbd2fdc3910cd67dfccc85",
    OLD / "failure-input-readback.json": "dca75df104fb780e19c4623a09b2e74247a1db5f12a15ce72b7dfe0073d7b35a",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--packet-sha256")
    parser.add_argument("--controller-commit")
    parser.add_argument("--controller-tree")
    parser.add_argument("--pwsh", type=Path)
    parser.add_argument("--binding-sha256")
    args = parser.parse_args()
    import hashlib
    with CONTROLLER.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != CONTROLLER_SHA:
            raise ValueError("Original independent controller changed")
    spec = importlib.util.spec_from_file_location("final_zip_replay", CONTROLLER)
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    work = args.work.resolve()
    if not work.is_relative_to(ROOT) or work == OLD or work == ROOT:
        raise ValueError("A distinct fresh independent retry directory is required")
    for path, expected in FAILURES.items():
        replay.sealed(path, expected)
    if args.phase == "prepare":
        if args.packet is None or args.pwsh is None:
            parser.error("Preparation requires the new sealed packet and native PowerShell")
        for value, length in ((args.packet_sha256, 64), (args.controller_commit, 40), (args.controller_tree, 40)):
            if not isinstance(value, str) or not re.fullmatch(f"[0-9a-f]{{{length}}}", value):
                raise ValueError("Full producer-provided controller identities required")
        replay.sealed(args.packet, args.packet_sha256)
        replay.SOURCES["packet"] = (args.packet.resolve(), args.packet_sha256)
        # Artifact COMMIT/TREE stay901256b/1f0bd4. New controller provenance is
        # recorded separately, not used to relabel the sealed artifact source.
        replay.prepare(work, args.pwsh.resolve())
        binding = {
            "schema": 1,
            "scope": "Producer-fixed verifier replay on the same immutable901256b artifact; earlier fixture failure retained",
            "artifact_source": {"commit": replay.COMMIT, "tree": replay.TREE},
            "controller_source": {"commit": args.controller_commit, "tree": args.controller_tree,
                                  "identity_authority": "Exact producer handoff; independently checked source packet hash"},
            "packet": {"path": str(args.packet.resolve()), "sha256": args.packet_sha256},
            "prepare_sha256": replay.sha(work / "prepare.json"),
            "prior_failure_receipts": {str(path): expected for path, expected in FAILURES.items()},
            "independent_controller_sha256": CONTROLLER_SHA,
            "retry_controller_sha256": replay.sha(__file__),
            "evidence_output": str(work / "final ZIP verification"),
            "extracted_root": str(work / "final ZIP verification/fresh moved Git Bash extraction"),
            "both_evidence_and_payload_paths_contain_spaces": True,
        }
        replay.write(work / "controller-binding.json", binding)
        print(json.dumps({"binding": str(work / "controller-binding.json"),
                          "sha256": replay.sha(work / "controller-binding.json")}), flush=True)
    else:
        if args.binding_sha256 is None:
            parser.error("Execution requires the sealed independent controller binding")
        replay.sealed(work / "controller-binding.json", args.binding_sha256)
        binding = json.loads((work / "controller-binding.json").read_text())
        replay.sealed(__file__, binding["retry_controller_sha256"])
        replay.SOURCES["packet"] = (Path(binding["packet"]["path"]), binding["packet"]["sha256"])
        replay.verify(work, binding["prepare_sha256"])
        for path, expected in FAILURES.items():
            replay.sealed(path, expected)
        report = json.loads((work / "result.json").read_text())
        handoff = {
            "schema": 1, "passed": report["passed"], "binding_sha256": args.binding_sha256,
            "artifact_source": binding["artifact_source"], "controller_source": binding["controller_source"],
            "independent_result": {"path": str(work / "result.json"), "sha256": replay.sha(work / "result.json")},
            "committed_verifier_result": report["verifier_result"],
            "prior_failure_receipts": binding["prior_failure_receipts"], "prior_failures_unchanged": True,
            "scope": binding["scope"], "owned_jobs_drained": report["owned_jobs_drained"],
            "both_evidence_and_payload_paths_contain_spaces": True,
        }
        replay.write(work / "handoff.json", handoff)
        print(json.dumps({"passed": handoff["passed"], "handoff": str(work / "handoff.json"),
                          "sha256": replay.sha(work / "handoff.json")}), flush=True)


if __name__ == "__main__":
    main()
