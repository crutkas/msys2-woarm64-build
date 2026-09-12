"""Attach exact admission/member provenance to an independently computed PE graph."""
from compression import zstd
import collections
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile


ROOT = Path(r"C:\ap16-accd-mingw-closure-01")
spec = importlib.util.spec_from_file_location("pe_audit", Path(__file__).with_name("inspect-native-archive.py"))
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def reference(path):
    return {"path": str(path), "sha256": sha(path)}


graph = load(ROOT / "static-graph.json")
intake = Path(r"C:\ap11-native-provider-intake")
network_path = intake / "revoked-free-closures-v2/network-export.json"
python_path = intake / "revoked-free-closures-v2/python-export.json"
network = load(network_path)
python = load(python_path)
audit = load(intake / "audit-v18-qualified-openssl.json")
selected = {item["name"]: item for item in audit["selected_packages"]}
archive_refs = {}
for export_path, data in ((network_path, network), (python_path, python)):
    for item in data["packages"]:
        path = Path(item["path"])
        if not path.is_absolute():
            # Preserve the export's original-root declaration where present; no search-path guessing.
            source_root = data.get("packageRoot") or data.get("exportRoot")
            if source_root:
                path = Path(source_root) / path
            else:
                path = export_path.parent / path
        name = item.get("name") or item.get("packageName")
        if name in selected and selected[name]["sha256"] == item["sha256"]:
            archive_refs.setdefault(name, {"path": str(path), "sha256": item["sha256"],
                                          "receipt": reference(export_path)})
original_export = Path(r"C:\ap09-ca5f\curl-packages-v2\export-12\export.json")
old = load(original_export)
old_archives = {item["sha256"]: item for item in old["packages"]}
private_nodes = sorted((value for value in graph["nodes"].values() if value["is_dll"]), key=lambda item: item["path"])
needed = {
    "libcrypto-3-arm64.dll": "mingw-w64-aarch64-openssl",
    "libssl-3-arm64.dll": "mingw-w64-aarch64-openssl",
    "libexpat-1.dll": "mingw-w64-aarch64-expat",
    "libidn2-0.dll": "mingw-w64-aarch64-libidn2",
    "libtre-5.dll": "mingw-w64-aarch64-libtre",
    "libunistring-5.dll": "mingw-w64-aarch64-libunistring",
    "libz.dll": "mingw-w64-aarch64-zlib",
    "libpcre2-8.dll": "mingw-w64-aarch64-pcre2",
    "libiconv-2.dll": "mingw-w64-aarch64-libiconv",
}
archives = {}


def members(descriptor, wanted):
    archive = Path(descriptor["path"])
    if sha(archive) != descriptor["sha256"]:
        raise ValueError(f"Package archive changed: {archive}")
    result = {}
    with zstd.open(archive, "rb") as compressed, tarfile.open(fileobj=compressed, mode="r|") as package:
        for entry in package:
            name = entry.name.removeprefix("./")
            if not entry.isfile() or name not in wanted:
                continue
            data = package.extractfile(entry).read()
            result[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                            "PE": parser.pe(data)}
    return result


for package in sorted(set(needed.values())):
    descriptor = archive_refs[package]
    wanted = {"mingwarm64/bin/" + dll for dll, owner in needed.items() if owner == package}
    package_members = members(descriptor, wanted)
    archives[package] = {**descriptor, "members": package_members}
    if not package_members:
        raise ValueError(f"No expected runtime in current package: {package}")

official_path = intake / "official-clangarm64-libintl-limited-mvp-v1/export.json"
pcre_path = intake / "pcre2-current-byte-limited-mvp-v1/export.json"
limited = {}
for export_path in (official_path, pcre_path):
    data = load(export_path)
    if data["status"] != "admitted-limited-mvp-only-final":
        raise ValueError("Expected a final limited-role verdict")
    for item in data["payload"]["files"]:
        relative = item["path"].removeprefix("payload/")
        path = export_path.parent / item["path"]
        if sha(path) != item["sha256"]:
            raise ValueError("Limited admitted payload changed")
        limited[(relative, item["sha256"])] = {"receipt": reference(export_path), "payload": str(path)}

old_tls = old_archives["256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3"]
old_tls_members = members(old_tls, {"mingwarm64/bin/libcrypto-3-arm64.dll", "mingwarm64/bin/libssl-3-arm64.dll"})
rows = []
for node in private_nodes:
    name = Path(node["path"]).name
    package = needed.get(name)
    current = archives[package] if package else None
    current_member = current["members"].get(node["path"]) if current else None
    limited_binding = limited.get((node["path"], node["sha256"]))
    if limited_binding:
        category = "admitted-limited-role"
        receipt = limited_binding["receipt"]
        note = "Artifact role only; not a strict package-provider transaction."
        if name == "libpcre2-8.dll":
            note += " Same archive remains selected in strict audit, with source/repro/full-suite limits."
        if name in ("libintl-8.dll", "libiconv-2.dll"):
            note += " Official CLANGARM64 C projection; strict GNU gettext is not admitted."
    elif name in ("libssl-3-arm64.dll", "libcrypto-3-arm64.dll"):
        category = "unadmitted-superseded-bytes"
        receipt = reference(intake / "openssl-mingwarm64-admitted-v1/export.json")
        if old_tls_members[node["path"]]["sha256"] != node["sha256"]:
            raise ValueError("Candidate TLS does not match the documented old archive")
        if current_member and current_member["sha256"] == node["sha256"]:
            raise ValueError("Old and new TLS unexpectedly identical; classification needs review")
        note = "Old archive256c superseded by admitted02f2. Intake explicitly rejects these old bytes as current limited authority. No substitution made."
    elif current_member and current_member["sha256"] == node["sha256"]:
        category = "admitted-selected-package"
        receipt = current["receipt"]
        note = "Exact current selected package member; dependency completeness and full-release qualification remain separate."
    else:
        category = "unadmitted-no-exact-binding"
        receipt = None
        note = "No matching current package or limited projection receipt for these bytes."
    depends = sorted({edge["target"] for edge in graph["edges"] if edge["source"] == node["path"] and edge["kind"] == "private"})
    if name == "libintl-8.dll":
        strict_status = "MISSING / required GNU gettext package not admitted"
    elif current_member:
        strict_status = "Current strict selection exists" + ("; different DLL bytes" if current_member["sha256"] != node["sha256"] else "; same DLL bytes")
    else:
        strict_status = "No exact current strict package member"
    provider_label = package or "mingw-w64-clang-aarch64-gettext-runtime 1.0-1 (C projection)"
    if name == "libiconv-2.dll" and limited_binding:
        provider_label = "mingw-w64-clang-aarch64-libiconv 1.19-1 (C projection)"
    rows.append({"DLL": name, "side": "MinGW/Windows-UCRT", "category": category, "SHA256": node["sha256"],
                 "path": node["absolute_path"], "provider": provider_label,
                 "receipt": receipt, "private_dependencies": depends,
                 "seed_consumers_reaching": len(node["reachable_from_consumers"]), "reachable_from": node["reachable_from_consumers"],
                 "strict_status": strict_status,
                 "strict_package": None if not current else {"path": current["path"], "sha256": current["sha256"], "receipt": current["receipt"]},
                 "strict_member": None if not current_member else {"sha256": current_member["sha256"], "path": node["path"]},
                 "notes": note})

for name, item in sorted(graph["windows_leaves"].items()):
    if item["class"] == "Windows API-set contract":
        if not item["hosts"] or not all(host["present"] for host in item["hosts"] if host["host"]):
            raise ValueError(f"API-set host missing: {name}")
        receipt = item["schema"]
        notes = "OS contract in the actual API-set schema; host(s): " + ", ".join(sorted({host["host"] for host in item["hosts"]}))
        file_hash = None
        path = item["schema"]["path"]
    else:
        receipt = {"path": item["path"], "sha256": item["sha256"]}
        file_hash = item["sha256"]
        notes = "Windows-supplied System32 leaf, not a package-provider claim."
        path = item["path"]
    rows.append({"DLL": name, "side": "Windows system boundary", "category": "Windows-satisfied",
                 "SHA256": file_hash, "path": path, "provider": item["class"], "receipt": receipt,
                 "private_dependencies": [], "seed_consumers_reaching": None,
                 "strict_status": "Windows boundary satisfied", "notes": notes})

# Compute the separate strict selected-package view, never overlaying it onto the actual candidate.
strict_nodes = {name: value for name, value in graph["nodes"].items() if name in graph["seeds"]}
strict_available = {path: member for package in archives.values() for path, member in package["members"].items()}
queue = collections.deque(graph["seeds"])
seen = set()
strict_missing = {}
strict_edges = []
while queue:
    name = queue.popleft()
    if name in seen:
        continue
    seen.add(name)
    image = strict_available[name]["PE"] if name in strict_available else strict_nodes[name]
    for imported in image["imports"] + image["delay_imports"]:
        dll = imported["dll"].lower()
        if dll in graph["windows_leaves"]:
            strict_edges.append({"source": name, "DLL": dll, "class": "Windows boundary"})
            continue
        found = next((path for path in strict_available if Path(path).name.lower() == dll), None)
        if found:
            strict_edges.append({"source": name, "DLL": dll, "class": "current package", "target": found})
            queue.append(found)
        else:
            strict_missing.setdefault(dll, []).append(name)
            strict_edges.append({"source": name, "DLL": dll, "class": "missing"})

gettext_rows = [value for value in audit["blockers"] if value.endswith(":libintl-8.dll") or value == "provider-not-supplied:mingw-w64-aarch64-gettext"]
other_rows = [value for value in audit["blockers"] if value not in gettext_rows]
categories = collections.Counter(value.split(":")[0] for value in audit["blockers"])
counts = collections.Counter(item["category"] for item in rows)
report = {
    "status": "read-only-static-closure-and-current-admission-reconciled",
    "scope": graph["scope"], "graph": reference(ROOT / "static-graph.json"), "counts": dict(counts),
    "rows": rows, "current_package_member_proofs": archives,
    "old_TLS_member_proof": {"archive": old_tls, "members": old_tls_members},
    "strict_selected_view": {"scope": "Separate computation from current v18 selected package bytes; not a modified candidate or an admission experiment",
                              "missing_DLL_identities": strict_missing, "edges": strict_edges},
    "global_audit": {"path": str(intake / "audit-v18-qualified-openssl.json"),
                     "sha256": sha(intake / "audit-v18-qualified-openssl.json"),
                     "total_blocker_rows": len(audit["blockers"]), "categories": dict(categories),
                     "gettext_related_rows": gettext_rows, "gettext_related_count": len(gettext_rows),
                     "other_rows": other_rows, "other_count": len(other_rows),
                     "interpretation": "81 heterogeneous blocker rows, not81unique DLLs. Only21missing import rows reference one DLL identity libintl-8.dll, plus one required gettext package identity. Limited-role admissions do not clear these strict transaction gates. The arithmetic59 is a hypothetical remainder after genuinely satisfying all22 gettext gates, not a revised audit verdict."},
    "static_scope_exclusions": graph["dynamic_dependencies_not_claimed_closed"],
    "known_dynamic_shell": reference(Path(r"C:\ap11-accd-gettext01\clarifications\native-sh-clone-01\clarification.json")),
    "no_new_alias_or_rebuild_or_payload_mutation": True,
}
(ROOT / "admission-table.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
columns = ["DLL", "side", "category", "SHA256", "path", "provider", "receipt_path", "receipt_SHA256",
           "private_dependencies", "seed_consumers_reaching", "strict_status", "notes"]
with (ROOT / "dll-admission-table.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for item in rows:
        writer.writerow({**{key: item.get(key, "") for key in columns if key not in ("receipt_path", "receipt_SHA256", "private_dependencies")},
                         "receipt_path": item["receipt"]["path"] if item["receipt"] else "",
                         "receipt_SHA256": item["receipt"]["sha256"] if item["receipt"] else "",
                         "private_dependencies": ";".join(item["private_dependencies"])})
print(json.dumps({"counts": dict(counts), "strict_missing": strict_missing,
                  "global": {"total": len(audit["blockers"]), "gettext": len(gettext_rows), "other": len(other_rows)},
                  "table": str(ROOT / "dll-admission-table.csv")}, indent=2))
