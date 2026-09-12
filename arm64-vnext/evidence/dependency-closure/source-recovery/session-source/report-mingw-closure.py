"""Write the requested read-only per-DLL table and non-duplicative blocker breakdown."""
import collections
import csv
import hashlib
import json
from pathlib import Path


root = Path(r"C:\ap16-accd-mingw-closure-01")
report = json.loads((root / "admission-table.json").read_text())
graph = json.loads((root / "static-graph.json").read_text())
groups = collections.defaultdict(list)
coreutils = {"cat.exe", "cp.exe", "env.exe", "mkdir.exe", "rm.exe", "sort.exe", "uniq.exe"}
ssh = {"ssh.exe", "ssh-add.exe", "ssh-agent.exe", "ssh-keygen.exe"}
for blocker in report["global_audit"]["other_rows"]:
    kind, _, value = blocker.partition(":")
    basename = value.split("/")[-1]
    if kind == "missing-native-self-hosting-evidence":
        family = "Native self-hosting evidence"
    elif kind == "managed-admission-not-supplied" or value == "mingw-w64-aarch64-git-credential-manager" or basename in ("git-credential-manager.exe", "git-credential-helper-selector.exe"):
        family = "Credential-manager/selector integration"
    elif value == "perl" or value.startswith("perl-") or basename == "perl.exe":
        family = "Perl and eight Perl modules"
    elif value == "coreutils" or basename in coreutils:
        family = "Coreutils provider and seven required executables"
    elif value == "openssh" or basename in ssh:
        family = "MSYS OpenSSH provider and four executables"
    elif value == "findutils" or basename == "find.exe":
        family = "Findutils provider and find executable"
    elif value == "less" or basename == "less.exe":
        family = "MSYS less provider and executable"
    elif value == "sed" or basename == "sed.exe":
        family = "Sed provider and executable"
    elif value == "etc/profile":
        family = "MSYS shell profile"
    elif kind == "private-runtime-path" and "libcurl-4.dll" in value:
        family = "MinGW libcurl operational-path gate"
    elif kind == "private-runtime-path" and "tcl86.dll" in value:
        family = "MinGW Tcl operational-path gates"
    else:
        family = "Other 20 distinct package identities"
    groups[family].append(blocker)
assert sum(map(len, groups.values())) == 59
assert len(groups["Other 20 distinct package identities"]) == 20
remaining = {"status": "breakdown-not-new-admission", "original_audit": report["global_audit"],
             "non_gettext_family_rows": dict(groups),
             "important": "Families group overlapping provider/file/evidence requirements; neither59rows nor these12groups is an estimate of independent implementations or effort. Package identity without mingw prefix is MSYS-contract scope, not a claim that any existing similarly named Win32 program satisfies it."}
(root / "blocker-breakdown.json").write_text(json.dumps(remaining, indent=2) + "\n")
with (root / "remaining-59-blockers.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.writer(stream)
    writer.writerow(("Family", "Original blocker row"))
    for family, blockers in groups.items():
        for blocker in blockers:
            writer.writerow((family, blocker))

receipts = {}
for row in report["rows"]:
    descriptor = row.get("receipt")
    if descriptor and row["category"] != "Windows-satisfied":
        receipts.setdefault(descriptor["sha256"], {"id": f"R{len(receipts) + 1}", **descriptor})
label = {
    "admitted-selected-package": "Admitted selected package",
    "admitted-limited-role": "Admitted limited role only",
    "unadmitted-superseded-bytes": "**SUPERSEDED—UNADMITTED**",
    "unadmitted-no-exact-binding": "**UNADMITTED**",
    "Windows-satisfied": "Windows satisfied",
}
lines = [
    "# Static closure and current admission: 21 MinGW consumers",
    "",
    "**Result: no missing DLL files or private import symbols, but two present OpenSSL DLLs are superseded and unadmitted.**",
    "This is a read-only measurement of `limited-candidate-02` (manifest `708394d8b303874307db541d278b9891d2b1fde1a9948e5266a3a992555e33f1`), reconciled with the intake owner's current v18 authority. No binary was changed, renamed, loaded, or executed.",
    "",
    "## Counts",
    "",
    "| Measure | Count |",
    "|---|---:|",
    "| Exact consumer seeds | 21 |",
    "| Package-owned PE nodes (19 executables + 10 DLLs) | 29 |",
    "| Distinct private DLLs | 10 |",
    "| Admitted selected-package DLLs | 5 |",
    "| Admitted limited-role DLLs | 3 |",
    "| Superseded/unadmitted present DLLs | 2 |",
    "| Windows boundary leaves (6 System32 + 13 API sets) | 19 |",
    "| Normal import edges / delay-import edges | 516 / 0 |",
    "| Physically missing DLL names / missing private imported symbols | 0 / 0 |",
    "| MSYS imports in this static graph | 0 |",
    "",
    "## Per-DLL admission table",
    "",
    "Receipt IDs below refer to full paths and SHA-256 values in the following table. `dll-admission-table.csv` includes every full file hash and receipt hash; no filename match alone is treated as admission.",
    "",
    "| DLL | Runtime side | Current admission for inspected bytes | Provider / receipt | Consumer seeds reaching it |",
    "|---|---|---|---|---:|",
]
for row in report["rows"]:
    receipt = receipts.get(row["receipt"]["sha256"]) if row.get("receipt") else None
    provider = row["provider"] + (f" / {receipt['id']}" if receipt else "")
    if row["provider"] == "Windows API-set contract":
        provider += " → System32 ucrtbase.dll"
    reach = row.get("seed_consumers_reaching")
    lines.append(f"| `{row['DLL']}` | {row['side']} | {label[row['category']]} | {provider} | {reach if reach is not None else '—'} |")
lines += ["", "| Receipt | Full SHA-256 | Path |", "|---|---|---|"]
for receipt in receipts.values():
    lines.append(f"| {receipt['id']} | `{receipt['sha256']}` | `{receipt['path']}` |")
lines += [
    "",
    "**The two OpenSSL rows deliberately remain red.** The inspected DLLs are `libssl-3-arm64.dll` SHA `819faab1f9b057302009d35fda49853aea8ccaadc29d2189420237ae8528da48` and `libcrypto-3-arm64.dll` SHA `0d35dfe504cfc03e49c2d6c989ff3838216c658aa5c23559de2756e46fd6561a`, from superseded archive `256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3`.",
    "",
    "The current admitted OpenSSL archive is `02f2e786dcf78a3b47d62a18cb0d1d9078cfcb69486a891bc4b901ad21b8e5ab`, bound by receipt `4c3a57be0859f70a355a6d133604cf278cd06fc8406f734344bf15331ebf1a62`. Its independently read archive members have different hashes: SSL `c1220fb0a6faea975376bbdde558ec19f9ada0a5f5ab0a9b86db14ed0f896b61`, crypto `dd210957efceb1999e38f2b5f5165c370fb6da6a1d7eff1185dd6edf1bc33818`. They were **not substituted** into the candidate.",
    "",
    "Both inspected TLS DLLs are reachable from `git-imap-send.exe` only within these 21 seeds' static import graph. That does **not** limit total TLS exposure: process-launched HTTPS helpers, embedded/static code, dynamically loaded libraries and plugins are outside this graph. `libcurl-4.dll` has no import edge in this measured closure; that is not proof that the program contains or uses no curl/TLS code.",
    "",
    "## The 81 full-release blocker rows",
    "",
    "| Category | Total v18 rows | Gettext-related | Other rows |",
    "|---|---:|---:|---:|",
    "| Missing DLL import edges | 21 | 21 | 0 |",
    "| Missing package/provider identities | 36 | 1 | 35 |",
    "| Missing required payload files | 18 | 0 | 18 |",
    "| Private operational paths | 4 | 0 | 4 |",
    "| Managed-component admission | 1 | 0 | 1 |",
    "| Native self-hosting evidence | 1 | 0 | 1 |",
    "| **Total** | **81** | **22** | **59** |",
    "",
    "The 21 import-edge rows all name **one** DLL, `libintl-8.dll`; the additional row is the strict `mingw-w64-aarch64-gettext` package identity. Independent computation using the v18 **selected package bytes** (not the limited candidate) likewise finds exactly this one missing DLL identity across 21 consumers. Limited libintl/PCRE2 file-role admissions do not satisfy the strict GNU gettext identity/transaction gate. Therefore 81 remains the authoritative audit count; 59 is only the arithmetic remainder **if all 22 strict gettext gates were genuinely resolved**, not a new verdict.",
    "",
    "### Why 59 is not 59 independent implementations",
    "",
    "| Other blocker family | Rows |",
    "|---|---:|",
]
for family, blockers in groups.items():
    lines.append(f"| {family} | {len(blockers)} |")
lines += [
    "",
    "The other 20 package identities are: " + ", ".join(f"`{item.split(':', 1)[1]}`" for item in groups["Other 20 distinct package identities"]) + ".",
    "",
    "Coreutils, OpenSSH, Perl, less, findutils and sed each have package and/or required-file rows describing overlapping obligations. The three Tcl path rows concern one DLL; the fourth path row concerns libcurl. Package/evidence gates may require more than one implementation or qualification step, so neither the grouped count nor CPU availability establishes an effort estimate.",
    "",
    "## Boundaries and caveats",
    "",
    "- The fixed point expands **all package-owned normal and delay imports**. Windows DLLs and API-set contracts are legitimate terminal boundaries; this is not a recursive security/implementation audit of Windows itself. The actual host API-set schema and every System32 boundary file/host were read and hash-bound.",
    "- All 29 application-side PEs in the graph are genuine AA64. No MSYS runtime is imported. The separate native MSYS PCRE2 needed by less is **not** this MinGW PCRE2 provider.",
    "- Native `sh.exe` is a known **dynamic command dependency**: the earlier clone failure disappeared when the real native `usr\\bin` was supplied. The original A/B/A failures and append-only clarification are preserved. This graph does not count the MSYS shell or its runtime as MinGW-import leaves.",
    "- Credential helpers, pagers, hooks, SSH, remote helpers, certificate data and configured plugins require separate command/configuration and behavior coverage. Static symbol availability is not runtime or end-to-end acceptance.",
    "- “Admitted selected package” means an exact archive/member match in v18, not that all that package's dependencies or all full-release requirements have passed. The limited official gettext and PCRE2 limitations remain in force.",
    "- The blocker ledger v5's separate-producer MSYS-PCRE2 scheduling wording was subsequently superseded by the one-serial-job PCRE2→less assignment to d207; no dependency or audit count was altered here.",
    "",
    "## Machine-readable evidence",
    "",
    "- `static-graph.json`: fixed-point nodes, all edges/symbols, seed reachability, Windows API-set resolution and hashes.",
    "- `admission-table.json` / `dll-admission-table.csv`: every DLL's full hash, receipt, provider, status, strict-selection difference and member proof.",
    "- `blocker-breakdown.json` / `remaining-59-blockers.csv`: the complete unchanged blocker rows and family mapping.",
    "- `authority-inputs.json`: exact snapshotted current intake authorities.",
]
(root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"families": {key: len(value) for key, value in groups.items()}, "report": str(root / "report.md")}, indent=2))
