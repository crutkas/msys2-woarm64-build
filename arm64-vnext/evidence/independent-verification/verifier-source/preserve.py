"""Copy irreplaceable verifier evidence without rewriting any source bytes."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


SOURCE = Path(r"C:\ag-tcl-e138-01\independent replay 20260911-01")
DESTINATION = Path(__file__).resolve().parents[2] / "arm64-vnext/evidence/independent-verification"
LIMIT = 50 * 1024 * 1024
SEALS = {
    SOURCE / "independent-tls-evidence-01.json":
        "94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc",
    SOURCE / "report-01/report.json":
        "c44fb3f8238980bea3545938362e7e84ea5cb806780ea58b354261e3d3447c9b",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def purpose(relative):
    name = relative.name
    value = relative.as_posix()
    if name == "independent-tls-evidence-01.json":
        return "Sealed independent live TLS findings, both artifact generations, CA lookup and authoritative provider identities."
    if name == "report.json":
        return "Sealed mixed independent verdict, findings, limitations, custody and reproducibility references."
    if name == "observation.json":
        return "Raw Windows exits, process generations, actual sampled modules and observer coverage/drain; no status decoder."
    if name == "request.json":
        return "Exact execution argv, working directory, all supplied environment values and observer identity."
    if name == "launch.json":
        return "Actual process PID, creation FILETIME, argv and transcript path."
    if name == "output.log":
        return "Unmodified execution transcript, including errors and failure text."
    if name == "static-audit.json":
        return "Independent actual PE architecture/import audit and embedded-path candidates; not live resolution proof."
    if "path-triage" in name:
        return "Debug/source/test strings distinguished from demonstrated operational CA-path failures."
    if name == "intake.json":
        return "Full measured custody inventory and source/extraction identities."
    if name == "manifest-readback.json":
        return "Independent named-ZIP manifest reconciliation with no differing files."
    if name == "environment-policy.json":
        return "Explicit environment isolation and assistance disclosure; no CA or exec-path repairs."
    if name == "drain.json":
        return "Verifier-owned jobs and recorded process generations drained; three-job allocation return."
    if name.endswith(".py"):
        return "Exact verifier or producer script snapshot retained as evidence/replay context, not an artifact binary."
    if name == "continuation.json":
        return "Transparent harness corrections and subsequent separately recorded cases."
    if name == "recreation.json":
        return "Fresh shipped-recipe ZIP repackaging identity; not package build reproducibility."
    if "fixture" in name:
        return "Verifier-owned test fixture intent and identities; not shipped application content."
    return "Original evidence metadata preserved with its absolute source path and exact bytes."


def main():
    for path, expected in SEALS.items():
        if digest(path) != expected:
            raise ValueError(f"Sealed evidence changed: {path}")
    selection = {}
    for path in SOURCE.iterdir():
        if path.is_file() and path.suffix == ".json":
            selection[Path("records") / path.relative_to(SOURCE)] = (path, purpose(path.relative_to(SOURCE)))
    groups = [
        "candidate-01 custody", "named ZIP custody", "candidate-01 baseline", "named ZIP baseline",
        "named ZIP standalone curl baseline", "shipped recreation baseline", "observer-control", "report-01",
    ]
    for group in groups:
        root = SOURCE / group
        for path in root.iterdir():
            if path.is_file() and path.suffix in (".json", ".log", ".py", ".stdout", ".stderr"):
                selection[Path("records") / path.relative_to(SOURCE)] = (path, purpose(path.relative_to(SOURCE)))
            elif path.is_dir() and (path / "observation.json").is_file():
                for evidence in path.iterdir():
                    if evidence.is_file() and evidence.suffix in (".json", ".log", ".py", ".stdout", ".stderr"):
                        relative = evidence.relative_to(SOURCE)
                        selection[Path("records") / relative] = (evidence, purpose(relative))

    refs = {
        "candidate-01/producer-manifest.json": Path(r"C:\ag-mvp-f6-20260911\candidate-01.manifest.json"),
        "candidate-01/disposition.json": Path(r"C:\ag-mvp-f6-20260911\candidate-01.disposition.json"),
        "named-zip/artifact-receipt.json": Path(r"C:\ag-mvp-f6-20260911\first-artifact-901256b\artifact-receipt.json"),
        "diagnostic-reproduction/result.json": Path(r"C:\ag-mvp-f6-20260911\deterministic-diagnostic-01\result.json"),
        "provider/openssl-superseded-export.json": Path(r"C:\ap09-ca5f\curl-packages-v2\export-12\export.json"),
        "provider/openssl-current-producer-export.json": Path(r"C:\ap11-native-provider-intake\openssl-qualified-v2\export.json"),
        "provider/openssl-current-admission.json": Path(r"C:\ap11-native-provider-intake\openssl-mingwarm64-admitted-v1\export.json"),
        "provider/current-input-v18.json": Path(r"C:\ap11-native-provider-intake\input-v18-revoked-free.json"),
        "observer/native-job-structure-source.py": Path(r"C:\ag-tcl-e138-01\observer\native-job.py"),
    }
    for generation, folder in (("candidate-01", "candidate-01 custody"), ("named-zip", "named ZIP custody")):
        root = SOURCE / folder / "relocated at a different depth/candidate with spaces"
        for name in ("Git-Bash-Native.cmd", "etc/profile", "etc/gitconfig", "etc/fstab",
                     "README-HANDOFF.md", "manifest.json", "provenance.json", "recreate.ps1",
                     "recreation/artifact.py"):
            path = root / name
            if path.is_file():
                refs[generation + "/shipped-metadata/" + name] = path
    for relative, path in refs.items():
        selection[Path("references") / relative] = (
            path, "Exact referenced producer/observer/shipped metadata; historical claims are not verifier approval.")
    for path in Path(__file__).parent.glob("*.py"):
        selection[Path("verifier-source") / path.name] = (
            path, "Verifier source at preservation time; sealed report-01 scripts remain separately preserved.")

    DESTINATION.mkdir(parents=True, exist_ok=True)
    rows, omitted = [], []
    for relative, (source, description) in sorted(selection.items(), key=lambda item: item[0].as_posix()):
        size = source.stat().st_size
        expected = digest(source)
        if size > LIMIT:
            omitted.append({"original_path": str(source), "bytes": size, "sha256": expected,
                            "reason": "Larger than the 50 MiB per-file Git evidence threshold; urgent external preservation needed."})
            continue
        target = DESTINATION / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError(f"Refusing to replace preserved evidence: {target}")
        shutil.copyfile(source, target)
        if digest(target) != expected or digest(source) != expected:
            raise ValueError(f"Evidence byte identity changed while copying: {source}")
        rows.append({"file": relative.as_posix(), "bytes": size, "sha256": expected,
                     "original_path": str(source), "proves": description})

    index = {"schema": 1, "preserved_utc": datetime.now(timezone.utc).isoformat(),
             "source_root": str(SOURCE), "copied_files": rows, "omitted_large_evidence": omitted,
             "copy_method": "shutil.copyfile, no decoding/formatting/line-ending changes; before/copy/after SHA-256 equal",
             "new_execution": False}
    (DESTINATION / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = [
        "# Independent ARM64 Git Bash verification: preserved evidence", "",
        "**Mixed results. Not MVP acceptance or current provider admission.**", "",
        "This evidence was copied byte-for-byte before the originating machine was scheduled for reformatting. "
        "The absolute paths below are historical provenance; after reformatting use the repository-relative "
        "copies and `index.json`, not those paths. Original JSON references were intentionally NOT rewritten.", "",
        "## Rehydration state", "",
        "- No verifier jobs were in flight. All 41 recorded job scopes completed cleanup; 69 recorded process "
        "generations were inactive. The fresh three-job allocation was returned; cap is 0.",
        "- **Admitted-TLS replay is OUTSTANDING.** Obtain a NEW frozen candidate and full archive/receipt hashes "
        "from assembler session `f6ea7713-2cec-41d5-b3f9-b4373e60fa33`, built with admitted OpenSSL archive "
        "`02f2e786dcf78a3b47d62a18cb0d1d9078cfcb69486a891bc4b901ad21b8e5ab` under admission "
        "`4c3a57be0859f70a355a6d133604cf278cd06fc8406f734344bf15331ebf1a62`. Do not infer that a mutable "
        "producer tree or this historical artifact was repaired.",
        "- Candidate-01 and the named ZIP are DISTINCT generations. Candidate-01 Git HTTPS failed raw 128 "
        "because libcurl's compiled `/mingwarm64/etc/ssl/certs/ca-bundle.crt` resolved to "
        "`C:/mingwarm64/...`; bundles were present inside the copied artifact.",
        "- The named ZIP's Git HTTPS clone succeeded raw 0 using its SHIPPED "
        "`http.sslCAInfo=%(prefix)/etc/ssl/certs/ca-bundle.crt`. It checked out public "
        "`octocat/Hello-World` commit `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`, with clean status/fsck. "
        "Live helper PID 19536 loaded superseded crypto; this is NOT proof of the admitted replacement TLS stack.",
        "- Named ZIP standalone `curl.exe` HTTPS failed raw 77 with the compiled absolute CA default. "
        "Git's configuration does not repair curl CLI. No verifier CA, exec-path, artifact or PATH repair was applied.",
        "- Both generations shipped and actually loaded `libssl-3-arm64.dll` "
        "`819faab1f9b057302009d35fda49853aea8ccaadc29d2189420237ae8528da48` and `libcrypto-3-arm64.dll` "
        "`0d35dfe504cfc03e49c2d6c989ff3838216c658aa5c23559de2756e46fd6561a`, from superseded archive "
        "`256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3`. The named ZIP README did not "
        "disclose this supersession at verification time. Peer candidate-02 findings are NOT relabelled as our own replay.",
        "- Tcl and Tk were EXCLUDED from the independent functional verdict for conflict-of-interest reasons "
        "(1,020 component files in each generation). The verifier owned separate native MSYS Tcl, whereas these "
        "artifacts contained MinGW Tcl/Tk; the exclusion was deliberately conservative.",
        "- The initial CMD quoting raw-1 attempt and `QueryFullProcessImageName` WinError 31 were HARNESS issues, "
        "not artifact defects. Their raw incomplete/failure evidence is preserved alongside transparent corrected "
        "transport/observer attempts. Do not erase them or count them as product failures.",
        "- Module snapshots are best-effort ordinary-process samples, NOT exhaustive DLL load-event traces. "
        "Raw exits were not decoded or normalized. Unknown identities remain coverage limitations.",
        "- Architecture audits found 333 / 327 AA64 PEs and no unresolved static imports. Core local Git operations, "
        "hooks, dynamically launched native sh, and bare clones worked at deep paths with spaces.",
        "- Five named ZIP copies, including an independent execution of the shipped recreation recipe from a "
        "fresh moved extraction, matched `7a4e99306da86abfc5591b96056ef06279bb8c4ca7353a7572a0e266abcdc854` "
        "(186,366,963 bytes). This proves ARCHIVE REPACKAGING determinism, not source/binary build reproduction.",
        "- Historical receipt `publication_authorized: true` is preserved verbatim. Later coordinator denial "
        "superseded it; a producer-side additive named-ZIP disposition was requested. Candidate-01's sibling "
        "disposition applies only to candidate-01. No claim of fraud or retrospective receipt rewriting is made.",
        "- Next step: restore a new candidate from trusted producer archives, re-hash its complete manifest, "
        "replay the same isolated Git/Bash/HTTPS cases with actual TLS module sampling, then reassess the "
        "disclosure/standalone-curl gaps. Obtain a new bounded job allocation; do not reuse returned grants.", "",
        "## What is deliberately absent", "",
        "No artifact ZIPs, binaries, extracted payload/repository trees, private user homes, credentials, "
        "build output, or CA bundle copies are committed. Their measured identities and transcripts remain. "
        "Producer-supplied JSON may refer to additional historical local artifacts that are not in this evidence "
        "packet; references are not claims that those binary artifacts survive.", "",
        "## Integrity", "",
        "`.gitattributes` disables Git text conversion for this evidence subtree. Verify each `index.json` entry "
        "by SHA-256 after checkout. The two primary seals are:", "",
        "- `records/independent-tls-evidence-01.json`: "
        "`94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc`.",
        "- `records/report-01/report.json`: "
        "`c44fb3f8238980bea3545938362e7e84ea5cb806780ea58b354261e3d3447c9b`.", "",
        "The table below lists EVERY copied evidence file, its purpose, full original SHA-256, size, and absolute "
        "origin. README and index are newly generated preservation metadata, not historical evidence.", "",
        "| Preserved file | What it proves | Bytes | SHA-256 | Absolute original path |",
        "|---|---|---:|---|---|",
    ]
    for row in rows:
        lines.append(f"| `{row['file']}` | {row['proves']} | {row['bytes']} | `{row['sha256']}` | `{row['original_path']}` |")
    if omitted:
        lines += ["", "## Large irreplaceable evidence not committed", ""]
        for row in omitted:
            lines.append(f"- `{row['original_path']}`: {row['bytes']} bytes; SHA-256 `{row['sha256']}`.")
    (DESTINATION / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"destination": str(DESTINATION), "copied_files": len(rows),
                      "copied_bytes": sum(row["bytes"] for row in rows), "omitted_large_evidence": omitted,
                      "primary_seals_verified": True}, indent=2))


if __name__ == "__main__":
    main()
