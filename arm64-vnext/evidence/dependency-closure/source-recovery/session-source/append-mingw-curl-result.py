"""Preserve sealed revisions and add the peer's separate standalone curl result."""
import hashlib
import json
from pathlib import Path
import shutil


root = Path(r"C:\ap16-accd-mingw-closure-01")
old = root / "delivery-02"
new = root / "delivery-03"
peer_path = Path(r"C:\ag-tcl-e138-01\independent replay 20260911-01\report-01\report.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path):
    return {"path": str(path), "sha256": digest(path), "size": path.stat().st_size}


def verify(descriptor):
    path = Path(descriptor["path"])
    if digest(path) != descriptor["sha256"] or path.stat().st_size != descriptor["size"]:
        raise ValueError(f"Reference mismatch: {path}")


assert digest(old / "handoff.json") == "58d02d74c48618bfefe8847bcea8dd11ce3b9975bee393440c9f9b63f6350195"
assert digest(peer_path) == "c44fb3f8238980bea3545938362e7e84ea5cb806780ea58b354261e3d3447c9b"
peer = load(peer_path)
curl = peer["evidence"]["standalone_curl"]
for key in ("request", "output", "observation"):
    verify(curl[key])
observation = load(Path(curl["observation"]["path"]))
generation = curl["generation"]
matches = [item for item in observation["processes"] if item["pid"] == generation["pid"]
           and item["creation_filetime"] == generation["creation_filetime"]]
assert len(matches) == 1 and matches[0]["sha256"] == generation["sha256"]
assert matches[0]["raw_exit"] == 77 and observation["parent_raw_exit"] == 77
assert digest(Path(generation["image"])) == generation["sha256"]
assert not observation["missing_process_events"]
for module in curl["sampled_tls"]:
    assert module in observation["module_snapshots"]
    assert module["pid"] == generation["pid"] and module["creation_filetime"] == generation["creation_filetime"]
    assert digest(Path(module["path"])) == module["sha256"]
request = load(Path(curl["request"]["path"]))
assert not any(name.upper() in ("GIT_SSL_CAINFO", "SSL_CERT_FILE", "CURL_CA_BUNDLE", "GIT_SSL_NO_VERIFY")
               for name in request["environment"])
assert "--insecure" not in request["argv"] and "-k" not in request["argv"]
assert "curl: (77) error adding trust anchors from file: C:/mingwarm64/etc/ssl/certs/ca-bundle.crt" in Path(curl["output"]["path"]).read_text()
new.mkdir()
exports = []


def copy(source, relative):
    target = new.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("Duplicate revision output")
    before = digest(source)
    shutil.copyfile(source, target)
    assert digest(target) == before and digest(source) == before
    exports.append({"original_path": str(source), "path": str(target),
                    "relative_path": relative, "sha256": before})
    return ref(target)


for item in load(old / "export-inventory.json"):
    assert digest(Path(item["path"])) == item["sha256"]
    if item["relative_path"] != "report.md":
        copy(Path(item["path"]), item["relative_path"])
copy(old / "report.md", "previous-revision-02/report.md")
copy(old / "handoff.json", "previous-revision-02/handoff.json")
copy(old / "export-inventory.json", "previous-revision-02/export-inventory.json")
peer_ref = copy(peer_path, "live-tls/independent-full-mixed-report.json")
for key in ("request", "output", "observation"):
    copy(Path(curl[key]["path"]), "live-tls/standalone-curl/" + Path(curl[key]["path"]).name)
copy(Path(__file__), "analysis-source/append-mingw-curl-result.py")
record = {"schema": 1, "status": "standalone-shipped-curl-CA-failure-confirmed-read-only",
          "peer_report": peer_ref, "curl_evidence": curl, "command": request["argv"],
          "scope": "Same named ZIP as the successful Git HTTPS clone, but a separate curl.exe command. Git's shipped prefix-relative sslCAInfo does not configure standalone curl.",
          "no_new_execution_or_repairs_by_this_author": True}
(new / "standalone-curl-confirmation.json").write_text(json.dumps(record, indent=2) + "\n")
exports.append({"path": str(new / "standalone-curl-confirmation.json"), "relative_path": "standalone-curl-confirmation.json",
                "sha256": digest(new / "standalone-curl-confirmation.json")})
text = (old / "report.md").read_text(encoding="utf-8")
section = """
## Revision 3: standalone shipped curl still fails in the named ZIP

The independent verifier subsequently supplied a separate result for the **shipped `curl.exe`**, not Git's HTTPS helper: **raw exit 77**, with `error adding trust anchors from file: C:/mingwarm64/etc/ssl/certs/ca-bundle.crt`. The bundle is present inside the moved named ZIP. Git's shipped prefix-relative `sslCAInfo` fixes Git's CA selection but does **not** configure standalone curl.

| Artifact / operation | Raw result | Interpretation |
|---|---:|---|
| Candidate-01, Git public HTTPS clone | **128 - FAIL** | Compiled CA default lookup defeats this generation's relocation. |
| Named ZIP, Git public HTTPS clone | **0 - PASS for this operation** | Shipped prefix-relative Git CA configuration works; superseded TLS still loaded. |
| Same named ZIP, standalone shipped curl HTTPS HEAD | **77 - FAIL** | Standalone curl still consults the compiled CA default; no verifier override or repair. |

The standalone process was PID **2644**, creation FILETIME **134335842597890221**, image SHA-256 `6ddfbcd7c5fcd015112d7e002727b20abc70b7e2c7f643b029cd8d70e9e196be`. Its exact generation also sampled `libcurl-4.dll` `d060e2d1...`, old `libssl-3-arm64.dll` `819faab1...`, and old `libcrypto-3-arm64.dll` `0d35dfe5...` (full hashes in the preceding TLS module table).

Citation: independent mixed report SHA-256 `c44fb3f8238980bea3545938362e7e84ea5cb806780ea58b354261e3d3447c9b`, copied to `live-tls/independent-full-mixed-report.json`. Exact request, output and raw process/module observation are copied under `live-tls/standalone-curl/`; their hashes are respectively `b223ee40180e726fa4160dbd1ea862f600b3c778188b92da5738fabf58aa778c`, `6629743422516870f9cdacb999280888ece4af9a77467dfe217795b662c2ed4d`, and `ec6c6145d29855437f2f242daed0175277b92c2384d5c6931dbeedafe5132e1b`.

These are distinct outcomes, not a single “HTTPS passed/failed” headline. CA lookup behavior and crypto-provider admission remain separate defects. The independent module samples establish actual use, not exhaustive load-event coverage. The original static report, its counts and the conditional 81/22/59 arithmetic remain unchanged.

"""
anchor = "## Counts\n"
assert text.count(anchor) == 1
text = text.replace(anchor, section + anchor)
(new / "report.md").write_text(text, encoding="utf-8")
exports.append({"path": str(new / "report.md"), "relative_path": "report.md", "sha256": digest(new / "report.md")})
(new / "export-inventory.json").write_text(json.dumps(exports, indent=2) + "\n")
old_handoff = load(old / "handoff.json")
handoff = {
    "schema": 3, "status": "static-closure-amended-with-live-TLS-and-generation-specific-CA-results",
    "previous_revision": ref(old / "handoff.json"), "original_revision": ref(root / "delivery-01/handoff.json"),
    "previous_reports_and_evidence_unchanged": True,
    "report": ref(new / "report.md"), "TLS_confirmation": ref(new / "live-tls-confirmation.json"),
    "standalone_curl_confirmation": ref(new / "standalone-curl-confirmation.json"),
    "peer_TLS_evidence": old_handoff["peer_evidence"], "peer_full_report": peer_ref,
    "static_counts_unchanged": old_handoff["static_counts_unchanged"],
    "admission_counts_unchanged": old_handoff["admission_counts_unchanged"],
    "full_release_blocker_rows": 81, "gettext_related_rows": 22, "other_rows": 59,
    "live_raw_results": {"candidate01_Git_HTTPS": 128, "named_ZIP_Git_HTTPS": 0, "named_ZIP_curl_HTTPS": 77},
    "exports": ref(new / "export-inventory.json"),
    "no_new_payload_execution_substitution_or_admission": True,
    "scope": "Both observed generations really loaded superseded crypto on HTTPS. Candidate01 Git and named curl have CA failures; named Git succeeds via shipped config. None implies admitted TLS or a complete dynamic closure."
}
(new / "handoff.json").write_text(json.dumps(handoff, indent=2) + "\n")
for item in exports:
    assert digest(Path(item["path"])) == item["sha256"]
assert digest(old / "handoff.json") == "58d02d74c48618bfefe8847bcea8dd11ce3b9975bee393440c9f9b63f6350195"
assert digest(root / "delivery-01/handoff.json") == "723462dad11535c8c76ca724bdec7c5fd4333e0aed15c0e7c308716c8021d3e4"
print(json.dumps({"handoff": ref(new / "handoff.json"), "report": ref(new / "report.md"),
                  "exports": len(exports), "live_raw_results": handoff["live_raw_results"]}, indent=2))
