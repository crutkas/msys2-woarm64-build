"""Issue a new report revision from immutable independent TLS observations."""
import hashlib
import json
from pathlib import Path
import shutil
import struct


ROOT = Path(r"C:\ap16-accd-mingw-closure-01")
OLD = ROOT / "delivery-01"
NEW = ROOT / "delivery-02"
PEER = Path(r"C:\ag-tcl-e138-01\independent replay 20260911-01\independent-tls-evidence-01.json")
INTAKE = Path(r"C:\ap11-native-provider-intake\audit-v18-static-closure-supplement-v1.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path):
    return {"path": str(path), "sha256": digest(path), "size": path.stat().st_size}


def require(path, expected, size=None):
    if digest(path) != expected or (size is not None and path.stat().st_size != size):
        raise ValueError(f"Evidence binding mismatch: {path}")


require(OLD / "handoff.json", "723462dad11535c8c76ca724bdec7c5fd4333e0aed15c0e7c308716c8021d3e4")
require(OLD / "report.md", "22b79d6d71afc5103a36efae48753debd02062de572ed9f7c97767a25bb517df")
require(PEER, "94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc", 13094)
require(INTAKE, "0938eb27b5a0fa8ac85f43c5b9d6a08cf67cf739f8364049f0b148fa9956fa74")
peer = load(PEER)
old_handoff = load(OLD / "handoff.json")
graph = load(OLD / "static-graph.json")
descriptors = {}


def validate_descriptors(value):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and "sha256" in value:
            path = Path(value["path"])
            require(path, value["sha256"], value.get("size"))
            descriptors[str(path)] = ref(path)
        for child in value.values():
            validate_descriptors(child)
    elif isinstance(value, list):
        for child in value:
            validate_descriptors(child)


validate_descriptors(peer)
case_details = {}
for name, case in peer["cases"].items():
    custody = load(Path(case["custody"]["path"]))
    if name == "candidate-01":
        require(Path(custody["producer_manifest"]["path"]), custody["producer_manifest"]["sha256"])
        if custody["copy_byte_identical"] is not True or custody["source_unchanged"] is not True or custody["manifest_mismatches"]:
            raise ValueError("Candidate custody is incomplete")
        identity = custody["producer_manifest"]
        files = len(custody["files"])
        expected_exit = 128
    else:
        validate_descriptors({"archive": custody["archive"], "producer_receipt": custody["producer_receipt"]})
        identity = custody["archive"]
        files = len(custody["files"])
        expected_exit = 0
    observation = load(Path(case["raw_observation"]["path"]))
    generation = case["helper_generation"]
    require(Path(generation["image"]), generation["sha256"])
    if generation["sha256"] != graph["nodes"]["mingwarm64/libexec/git-core/git-remote-https.exe"]["sha256"]:
        raise ValueError("Live helper differs from the static helper; cannot silently combine identities")
    match = [process for process in observation["processes"]
             if process["pid"] == generation["pid"] and process["creation_filetime"] == generation["creation_filetime"]]
    if len(match) != 1 or match[0]["sha256"] != generation["sha256"] or match[0]["raw_exit"] != expected_exit:
        raise ValueError("Live helper generation binding is incomplete")
    if observation["parent_raw_exit"] != expected_exit or case["parent_raw_exit"] != expected_exit:
        raise ValueError("Parent raw exit differs from peer summary")
    if observation["missing_process_events"] or observation["created_processes"] != observation["observed_processes"]:
        raise ValueError("Process-count evidence incomplete")
    for module in case["sampled_tls_modules"]:
        if module["pid"] != generation["pid"] or module["creation_filetime"] != generation["creation_filetime"]:
            raise ValueError("TLS module belongs to another process generation")
        if module not in observation["module_snapshots"]:
            raise ValueError("Summarized TLS module is absent from the raw module observations")
    literal = case["libcurl_ca_literal"]
    data = Path(literal["image"]["path"]).read_bytes()
    begin = literal["offset"]
    value = literal["value"].encode("ascii")
    if data[begin:begin + len(value) + 1] != value + b"\0":
        raise ValueError("Compiled CA literal does not match the asserted file offset")
    pe_offset = struct.unpack_from("<I", data, 60)[0]
    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    section_table = pe_offset + 24 + struct.unpack_from("<H", data, pe_offset + 20)[0]
    found_section = None
    for index in range(section_count):
        entry = section_table + index * 40
        size, offset = struct.unpack_from("<II", data, entry + 16)
        if offset <= begin and begin + len(value) < offset + size:
            found_section = data[entry:entry + 8].rstrip(b"\0").decode("ascii")
    if found_section != ".rdata":
        raise ValueError("CA literal is not in the reported .rdata section")
    request = load(Path(case["command_environment"]["path"]))
    if any(key.upper() in ("GIT_SSL_CAINFO", "SSL_CERT_FILE", "CURL_CA_BUNDLE", "GIT_SSL_NO_VERIFY")
           for key in request["environment"]):
        raise ValueError("Unexpected certificate environment override")
    if case["artifact_repairs"] or case["tls_verification_disabled"]:
        raise ValueError("Peer repaired the candidate or disabled verification")
    config = Path(case["shipped_git_system_config"]["file"]["path"]).read_text(encoding="utf-8")
    if config != case["shipped_git_system_config"]["text"]:
        raise ValueError("Shipped config content differs")
    output = Path(case["raw_output"]["path"]).read_text(encoding="utf-8")
    if name == "candidate-01":
        if "error adding trust anchors from file: C:/mingwarm64/etc/ssl/certs/ca-bundle.crt" not in output:
            raise ValueError("Expected actual candidate CA failure diagnostic missing")
        if "sslCAInfo" in config:
            raise ValueError("Candidate unexpectedly has an explicit shipped CA binding")
    elif "sslCAInfo = %(prefix)/etc/ssl/certs/ca-bundle.crt" not in config:
        raise ValueError("Named ZIP shipped prefix-relative CA configuration missing")
    case_details[name] = {
        "identity": identity, "custody_files": files, "root": case["root"],
        "command": request["argv"], "raw_exit": expected_exit, "helper_generation": generation,
        "actual_tls_modules": case["sampled_tls_modules"], "relative_bundles_present": case["relative_ca_bundles"],
        "compiled_literal": literal, "shipped_CA_config": case["shipped_git_system_config"],
        "created_processes": observation["created_processes"], "observed_processes": observation["observed_processes"],
        "module_coverage": observation["module_coverage"], "cause_scope": case["cause_scope"],
    }

NEW.mkdir()
exports = []


def copy_evidence(source, relative):
    target = NEW.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("Duplicate export")
    before = digest(source)
    shutil.copyfile(source, target)
    require(target, before)
    require(source, before)
    exports.append({"original_path": str(source), "path": str(target), "relative_path": relative, "sha256": before})
    return ref(target)


for item in load(OLD / "export-inventory.json"):
    require(Path(item["Path"]), item["SHA256"])
    relative = item["RelativePath"].replace("\\", "/")
    if relative == "report.md":
        continue
    copy_evidence(Path(item["Path"]), relative)
copy_evidence(OLD / "report.md", "previous-report/report.md")
copy_evidence(OLD / "handoff.json", "previous-report/handoff.json")
copy_evidence(OLD / "export-inventory.json", "previous-report/export-inventory.json")
peer_reference = copy_evidence(PEER, "live-tls/independent-tls-evidence-01.json")
intake_reference = copy_evidence(INTAKE, "previous-report/intake-acceptance.json")
for index, (path, descriptor) in enumerate(descriptors.items()):
    source = Path(path)
    if source.suffix.lower() in (".dll", ".exe", ".zst", ".zip"):
        continue
    copy_evidence(source, f"live-tls/references/{index:03d}-" + descriptor["sha256"] + "-" + source.name)
copy_evidence(Path(__file__), "analysis-source/amend-mingw-live-tls.py")
supplement = {
    "schema": 1, "status": "independent-live-HTTPS-TLS-confirmation-verified-read-only",
    "peer_evidence": peer_reference, "cases": case_details,
    "all_verified_reference_files": list(descriptors.values()),
    "static_helper_SHA256": graph["nodes"]["mingwarm64/libexec/git-core/git-remote-https.exe"]["sha256"],
    "relationship": "The same git-remote-https PE hash lacks static libcurl/OpenSSL import edges, yet live samples show those DLLs loaded. The static graph was complete for its declared imports, not a bound on process/runtime TLS exposure.",
    "conclusions": [
        "Superseded SSL819faab1 and crypto0d35dfe5 were actually used by the public HTTPS clone helper in BOTH independently preserved artifact generations.",
        "Candidate-01 clone failed raw128 from trust-anchor path lookup. Relative bundles existed; libcurl's ASCII .rdata default at offset1117512 points to /mingwarm64/etc/ssl/certs/ca-bundle.crt. This immediate cause is separate from crypto admission.",
        "The named ZIP clone passed raw0 using its already-shipped %(prefix) CA configuration, without verifier repairs. The candidate-01 CA failure must not be carried to that generation.",
        "The named ZIP's successful HTTPS operation still loaded the superseded pair; functional success does not admit those crypto bytes.",
        "Ordinary module sampling proves named modules were loaded in exact PID/birth generations, not exhaustive load-event coverage.",
        "The original29staticDLL rows,21seed graph counts and81/22/59 blocker arithmetic remain unchanged. No payload was swapped or re-executed by this report author.",
    ],
}
(NEW / "live-tls-confirmation.json").write_text(json.dumps(supplement, indent=2) + "\n", encoding="utf-8")
exports.append({"path": str(NEW / "live-tls-confirmation.json"), "relative_path": "live-tls-confirmation.json",
                "sha256": digest(NEW / "live-tls-confirmation.json")})

old_text = (OLD / "report.md").read_text(encoding="utf-8")
insertion = """
## Revision 2: live HTTPS use of superseded TLS is confirmed

**The old OpenSSL pair is not confined to IMAP: independent live module samples prove that public HTTPS clones loaded it.** The original static scope was deliberately narrower. This revision preserves the original report and adds the exact peer observations; no payload was replaced or rerun here.

Independent evidence: `live-tls/independent-tls-evidence-01.json`, SHA-256 `94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc`, produced by `b1b1deaf-f47e-4ecf-a9d7-8ff7a75fe4d9`. Its referenced requests, environments, raw observations, outputs, custody records, shipped configuration and binary literal were re-read and hash-verified for this amendment.

| Independently preserved generation | Public HTTPS clone result | Live helper identity | CA result | TLS admission result |
|---|---|---|---|---|
| Candidate-01; manifest `a2052594e723bbc0f419cc546c19252b804af51d2440e64a29c847056bb316c3`; 12,376 copied files | **FAIL, raw 128** | PID 20464; creation FILETIME 134335839054013820 | Failed trust-anchor loading from `C:/mingwarm64/etc/ssl/certs/ca-bundle.crt`, despite bundles present inside the moved artifact | **Superseded/unadmitted pair actually loaded** |
| Named ZIP `7a4e99306da86abfc5591b96056ef06279bb8c4ca7353a7572a0e266abcdc854`; 12,392 extracted files | **PASS, raw 0, for this clone** | PID 19536; creation FILETIME 134335841375272335 | Already-shipped `sslCAInfo = %(prefix)/etc/ssl/certs/ca-bundle.crt` resolved the bundle; no verifier repair | **Same superseded/unadmitted pair actually loaded** |

Both helpers have SHA-256 `23f0ed83d9f815765f7bccd8a301e217d245c87ef1be36cf9239e30c077e8a6a`, also the helper hash in the static graph. Both live generations loaded:

| Module | Full SHA-256 |
|---|---|
| `libcurl-4.dll` | `d060e2d1127b52b49f7956d5eee59681ae160cd79bdac2156a45c05fbdd46669` |
| `libssl-3-arm64.dll` | `819faab1f9b057302009d35fda49853aea8ccaadc29d2189420237ae8528da48` |
| `libcrypto-3-arm64.dll` | `0d35dfe504cfc03e49c2d6c989ff3838216c658aa5c23559de2756e46fd6561a` |

The libcurl image contains the NUL-terminated ASCII literal `/mingwarm64/etc/ssl/certs/ca-bundle.crt` at **file offset 1,117,512**, in **`.rdata`**, in both copies. Each copy contains a real relative CA bundle at `mingwarm64/etc/ssl/certs/ca-bundle.crt` (and `mingwarm64/ssl/certs/ca-bundle.crt`), SHA-256 `8b347435463fdfb8400da4599d2e1af448ae8426ca7546c417aa289cb1c61bfa`. Candidate-01's shipped configuration did not override the default. The named ZIP's shipped prefix-relative configuration did.

**Two defects must remain separate:** candidate-01's immediate raw-128 failure was CA lookup relocation; superseded TLS provenance remained a defect in **both** generations. Do not attribute the CA failure to old OpenSSL, do not carry the candidate failure into the successful named ZIP result, and do not treat the named ZIP's functional success as crypto admission.

The clones used the genuine shipped helper and public URL `https://github.com/octocat/Hello-World.git`. No CA/environment/exec-path repair or TLS-verification disablement was made by the verifier. These are ordinary, generation-bound module samples, **not exhaustive load-event coverage**. Full reference hashes and copied raw records are in `live-tls-confirmation.json` and `live-tls/references/`.

The static closure counts and conditional **81 total / 22 gettext-related / 59 other** blocker-row breakdown below are unchanged. Zero unresolved static imports does not establish whole-program runtime correctness, full dynamic closure, relocation correctness, or current provider admission.

"""
anchor = "## Counts\n"
if old_text.count(anchor) != 1:
    raise ValueError("Original report anchor changed")
new_text = old_text.replace(anchor, insertion + anchor)
new_text = new_text.replace(
    "Both inspected TLS DLLs are reachable from `git-imap-send.exe` only within these 21 seeds' static import graph. That does **not** limit total TLS exposure:",
    "**Static-edge statement only, now supplemented by live HTTPS confirmation above:** both inspected TLS DLLs are reachable from `git-imap-send.exe` only within these 21 seeds' static import graph. They were nevertheless actually loaded by `git-remote-https` in both peer captures. Static reachability does **not** limit total TLS exposure:"
)
(NEW / "report.md").write_text(new_text, encoding="utf-8")
exports.append({"path": str(NEW / "report.md"), "relative_path": "report.md", "sha256": digest(NEW / "report.md")})
(NEW / "export-inventory.json").write_text(json.dumps(exports, indent=2) + "\n", encoding="utf-8")
handoff = {
    "schema": 2, "status": "static-closure-report-amended-with-independent-live-HTTPS-evidence",
    "previous_handoff": ref(OLD / "handoff.json"), "previous_report": ref(OLD / "report.md"),
    "previous_evidence_unchanged": True,
    "original_static_audit_accepted_by_intake_not_admission": intake_reference,
    "report": ref(NEW / "report.md"), "supplement": ref(NEW / "live-tls-confirmation.json"),
    "peer_evidence": peer_reference, "inventory": ref(NEW / "export-inventory.json"),
    "static_counts_unchanged": old_handoff["Counts"],
    "admission_counts_unchanged": old_handoff["AdmissionCounts"],
    "full_release_blocker_rows": 81, "gettext_related_rows": 22, "other_rows": 59,
    "live_case_raw_exits": {name: case["raw_exit"] for name, case in case_details.items()},
    "no_new_payload_execution_or_substitution": True,
    "scope": "Read-only reconciliation of two separately bound peer generations. HTTPS exposure confirmed in both; CA failure candidate-only; named clone success is not crypto admission."
}
(NEW / "handoff.json").write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
for item in exports:
    require(Path(item["path"]), item["sha256"])
require(OLD / "handoff.json", "723462dad11535c8c76ca724bdec7c5fd4333e0aed15c0e7c308716c8021d3e4")
require(OLD / "report.md", "22b79d6d71afc5103a36efae48753debd02062de572ed9f7c97767a25bb517df")
print(json.dumps({"handoff": ref(NEW / "handoff.json"), "report": ref(NEW / "report.md"),
                  "supplement": ref(NEW / "live-tls-confirmation.json"), "exports": len(exports),
                  "verified_peer_references": len(descriptors), "live_cases": handoff["live_case_raw_exits"]}, indent=2))
