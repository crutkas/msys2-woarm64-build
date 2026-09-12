"""Seal source-bound, raw independent TLS observations for read-only peer citation."""

from pathlib import Path
import json

from observe import save, sha


ROOT = Path(r"C:\ag-tcl-e138-01\independent replay 20260911-01")


def ref(path):
    return {"path": str(path), "sha256": sha(path), "size": path.stat().st_size}


def main():
    cases = {}
    for name in ("candidate-01", "named ZIP"):
        custody, replay = ROOT / (name + " custody"), ROOT / (name + " baseline")
        intake = json.loads((custody / "intake.json").read_text())
        artifact = Path(intake["extraction"])
        case = replay / "git-https-clone"
        observation = json.loads((case / "observation.json").read_text())
        helper = next(p for p in observation["processes"]
                      if p.get("image", "").lower().endswith("git-remote-https.exe"))
        modules = [m for m in observation["module_snapshots"]
                   if m["pid"] == helper["pid"] and m["creation_filetime"] == helper["creation_filetime"]
                   and Path(m["path"]).name.lower() in ("libcurl-4.dll", "libssl-3-arm64.dll", "libcrypto-3-arm64.dll")]
        if len(modules) != 3:
            raise ValueError("The actual HTTPS helper must have all three sampled TLS modules")
        curl = artifact / "mingwarm64/bin/libcurl-4.dll"
        literal = b"/mingwarm64/etc/ssl/certs/ca-bundle.crt"
        data = curl.read_bytes()
        offset = data.find(literal)
        if offset != 1117512:
            raise ValueError("The measured libcurl CA literal offset changed")
        if any(sha(m["path"]) != m["sha256"] for m in modules):
            raise ValueError("A actually sampled module changed on disk")
        cases[name] = {
            "classification": "Independent raw experimental generation; no publication/admission",
            "root": str(artifact), "custody": ref(custody / "intake.json"),
            "command_environment": ref(case / "request.json"), "launch": ref(case / "launch.json"),
            "raw_observation": ref(case / "observation.json"), "raw_output": ref(case / "output.log"),
            "parent_raw_exit": observation["parent_raw_exit"],
            "helper_generation": helper, "sampled_tls_modules": modules,
            "environment_policy": ref(replay / "environment-policy.json"),
            "libcurl_ca_literal": {"image": ref(curl), "offset": offset, "encoding": "ASCII",
                                  "value": literal.decode(), "section": ".rdata"},
            "relative_ca_bundles": [ref(artifact / p) for p in
                                    ("mingwarm64/etc/ssl/certs/ca-bundle.crt", "mingwarm64/ssl/certs/ca-bundle.crt")],
            "shipped_git_system_config": {"file": ref(artifact / "etc/gitconfig"),
                                          "text": (artifact / "etc/gitconfig").read_text()},
            "actual_git_system_config": ref(replay / "git-system-config/output.log"),
            "artifact_repairs": [], "tls_verification_disabled": False,
            "cause_scope": ("CA default relocation failure; not attributed to crypto provenance"
                           if name == "candidate-01" else
                           "Real HTTPS clone succeeded through shipped prefix-relative CA config, "
                           "but actually loaded the superseded crypto pair; NOT current admitted TLS evidence"),
        }
    authorities = [
        (r"C:\ap09-ca5f\curl-packages-v2\export-12\export.json",
         "546d8ca66282b89803d6423f36db1f562fadf759e8d4a7e11870cb485ea84dd8"),
        (r"C:\ap11-native-provider-intake\openssl-qualified-v2\export.json",
         "cc62db912148d55d70c2a869f1aff3b8a5aec6385bcbfb0ce26b8af78aeab8d0"),
        (r"C:\ap11-native-provider-intake\openssl-qualified-v2\packages\mingw-w64-aarch64-openssl-3.6.4-1-any.pkg.tar.zst",
         "02f2e786dcf78a3b47d62a18cb0d1d9078cfcb69486a891bc4b901ad21b8e5ab"),
        (r"C:\ap11-native-provider-intake\openssl-mingwarm64-admitted-v1\export.json",
         "4c3a57be0859f70a355a6d133604cf278cd06fc8406f734344bf15331ebf1a62"),
        (r"C:\ap11-native-provider-intake\input-v18-revoked-free.json",
         "3d129458c38268f2e6c845172f838e2cfeb803720528bc7278315ce3310e5c2e"),
    ]
    references = []
    for path, expected in authorities:
        actual = ref(Path(path))
        if actual["sha256"] != expected:
            raise ValueError("Provider disposition evidence identity mismatch")
        references.append(actual)
    record = {"schema": 1, "cases": cases, "provider_disposition_inputs": references,
              "authority": "Provider intake a2dd0a44 and General ece identify old256c archive as superseded/unadmitted",
              "independence": "No Tcl/Tk judgment; verifier produced no Git/Bash/HTTPS component in either generation",
              "live_module_scope": "Ordinary sampling proves the named TLS modules were loaded in these exact "
                                   "helper generations; it does not claim exhaustive load-event coverage"}
    path = ROOT / "independent-tls-evidence-01.json"
    save(path, record)
    print(json.dumps(ref(path)))


if __name__ == "__main__":
    main()
