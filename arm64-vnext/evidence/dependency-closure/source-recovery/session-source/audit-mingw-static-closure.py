"""Read-only fixed-point application DLL audit; Windows contracts are explicit leaves."""
import collections
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import struct


ROOT = Path(r"C:\ag-mvp-f6-20260911\limited-candidate-02")
MANIFEST = ROOT.with_name("limited-candidate-02.manifest.json")
BOUNDARY = ROOT.with_name("libintl-consumer-boundary-01.json")
OUTPUT = Path(r"C:\ap16-accd-mingw-closure-01")
SYSTEM = Path(r"C:\Windows\System32")
spec = importlib.util.spec_from_file_location("pe_audit", Path(__file__).with_name("inspect-native-archive.py"))
pe_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe_audit)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def bound(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"Input hash mismatch: {path}")
    return {"path": str(path), "sha256": actual}


def apisets():
    path = SYSTEM / "apisetschema.dll"
    data = path.read_bytes()
    coff = struct.unpack_from("<I", data, 60)[0] + 4
    count = struct.unpack_from("<H", data, coff + 2)[0]
    table = coff + 20 + struct.unpack_from("<H", data, coff + 16)[0]
    for index in range(count):
        entry = table + index * 40
        if data[entry:entry + 8].rstrip(b"\0") == b".apiset":
            size, offset = struct.unpack_from("<II", data, entry + 16)
            section = data[offset:offset + size]
            break
    else:
        raise ValueError("Windows API-set schema section not found")
    version, size, _, count, entries, _, _ = struct.unpack_from("<7I", section)
    if version != 6 or size > len(section):
        raise ValueError("Unsupported Windows API-set schema")
    result = {}
    for index in range(count):
        _, name_offset, name_length, _, values_offset, values_count = struct.unpack_from("<6I", section, entries + index * 24)
        name = section[name_offset:name_offset + name_length].decode("utf-16-le").lower()
        values = []
        for value_index in range(values_count):
            _, alias_offset, alias_length, host_offset, host_length = struct.unpack_from("<5I", section, values_offset + value_index * 20)
            values.append({"importer_alias": section[alias_offset:alias_offset + alias_length].decode("utf-16-le"),
                           "host": section[host_offset:host_offset + host_length].decode("utf-16-le").lower()})
        result[name + ".dll"] = values
    return result, {"path": str(path), "sha256": sha(path), "schema_version": version, "contracts": len(result)}


def main():
    OUTPUT.mkdir()
    inputs = [
        bound(MANIFEST, "708394d8b303874307db541d278b9891d2b1fde1a9948e5266a3a992555e33f1"),
        bound(BOUNDARY, "ecaa96a91879c81ec43ea3f51b359994881f08510ce58fb74d45fd6c56d88718"),
    ]
    manifest = load(MANIFEST)
    boundary = load(BOUNDARY)
    contracts, schema = apisets()
    by_lower = {name.lower(): name for name in manifest["files"]}
    seeds = []
    for consumer in boundary["consumers"]:
        path = consumer["payload_path"]
        if manifest["files"][path]["sha256"] != consumer["sha256"]:
            raise ValueError(f"Current candidate changed a bound consumer: {path}")
        seeds.append(path)
    if len(seeds) != 21:
        raise ValueError("Expected exactly 21 bound consumers")
    nodes = {}
    edges = []
    pending = collections.deque(seeds)
    os_leaves = {}
    missing = {}

    def resolve(dll, importer):
        dll = dll.lower()
        if dll in contracts:
            values = contracts[dll]
            hosts = []
            for value in values:
                host = SYSTEM / value["host"]
                hosts.append({**value, "present": host.is_file(), "sha256": sha(host) if host.is_file() else None})
            os_leaves[dll] = {"name": dll, "class": "Windows API-set contract", "schema": schema, "hosts": hosts}
            return {"kind": "windows", "target": dll}
        if (SYSTEM / dll).is_file():
            path = SYSTEM / dll
            os_leaves[dll] = {"name": dll, "class": "Windows System32 DLL", "path": str(path), "sha256": sha(path)}
            return {"kind": "windows", "target": dll}
        directory = Path(importer).parent.as_posix()
        candidates = []
        for name in (directory + "/" + dll, "mingwarm64/bin/" + dll):
            actual = by_lower.get(name.lower())
            if actual and actual not in candidates:
                candidates.append(actual)
        if candidates:
            hashes = {manifest["files"][item]["sha256"] for item in candidates}
            if len(hashes) != 1:
                raise ValueError(f"Ambiguous private DLL search for {dll}: {candidates}")
            return {"kind": "private", "target": candidates[0], "same_byte_locations": candidates}
        missing[dll] = {"name": dll, "class": "missing", "importers": sorted(set(missing.get(dll, {}).get("importers", []) + [importer]))}
        return {"kind": "missing", "target": dll}

    while pending:
        relative = pending.popleft()
        if relative in nodes:
            continue
        path = ROOT.joinpath(*relative.split("/"))
        metadata = manifest["files"][relative]
        digest = sha(path)
        if digest != metadata["sha256"]:
            raise ValueError(f"Candidate member changed: {relative}")
        image = pe_audit.pe(path.read_bytes())
        if not image["ordinary_arm64"]:
            raise ValueError(f"Application-side PE is not ordinary AA64: {relative}")
        names = sorted({item["dll"].lower() for item in image["imports"]})
        delayed_names = sorted({item["dll"].lower() for item in image["delay_imports"]})
        if names != sorted(metadata["imports"]) or delayed_names != sorted(metadata["delay_imports"]):
            raise ValueError(f"Manifest versus actual PE imports differ: {relative}")
        nodes[relative] = {"path": relative, "absolute_path": str(path), "sha256": digest,
                           "machine": image["machine"], "is_seed": relative in seeds,
                           "is_dll": relative.lower().endswith(".dll"), "provenance": metadata["provenance"],
                           "components": metadata["components"], "existing_alias_metadata": metadata.get("alias"),
                           "imports": image["imports"], "delay_imports": image["delay_imports"], "exports": image["exports"]}
        for kind, imports in (("import", image["imports"]), ("delay-import", image["delay_imports"])):
            for imported in imports:
                result = resolve(imported["dll"], relative)
                edges.append({"source": relative, "dll": imported["dll"].lower(), "type": kind,
                              "symbols": imported["symbols"], **result})
                if result["kind"] == "private" and result["target"] not in nodes:
                    pending.append(result["target"])

    unresolved_symbols = []
    for edge in edges:
        if edge["kind"] != "private":
            continue
        target = nodes[edge["target"]]
        named = {entry["name"] for entry in target["exports"]}
        ordinal = {entry["ordinal"] for entry in target["exports"]}
        absent = [entry for entry in edge["symbols"]
                  if entry.get("name") not in named and entry.get("ordinal") not in ordinal]
        if absent:
            unresolved_symbols.append({"source": edge["source"], "target": edge["target"], "symbols": absent})

    reach = {}
    for seed in seeds:
        seen = set()
        queue = collections.deque([seed])
        while queue:
            current = queue.popleft()
            for edge in edges:
                if edge["source"] != current:
                    continue
                seen.add(edge["target"])
                if edge["kind"] == "private" and edge["target"] not in reach.get(seed, set()):
                    reach.setdefault(seed, set()).add(edge["target"])
                    queue.append(edge["target"])
        reach[seed] = seen
    for name, node in nodes.items():
        node["reachable_from_consumers"] = [seed for seed in seeds if name == seed or name in reach[seed]]
    dlls = [node for node in nodes.values() if node["is_dll"]]
    report = {
        "status": "static-fixed-point-computed-admission-reconciliation-pending",
        "scope": "All ordinary/delay imports transitively across package-owned DLLs; Windows System32/API-set contracts are explicitly satisfied terminal boundaries, not redistributable packages or a recursive audit of the OS itself.",
        "resolution_model": "Windows API-set and System32 boundaries; otherwise importing directory then private mingwarm64/bin. No host PATH, CWD, renamed alias or alternative provider fallback. Existing alias metadata is disclosed, never created.",
        "inputs": inputs, "root": str(ROOT), "api_set_schema": schema, "seeds": seeds,
        "nodes": nodes, "edges": edges, "windows_leaves": os_leaves, "missing": missing,
        "unresolved_private_import_symbols": unresolved_symbols,
        "counts": {"seed_consumers": len(seeds), "package_PE_nodes": len(nodes), "distinct_private_DLL_files": len(dlls),
                   "normal_import_edges": sum(item["type"] == "import" for item in edges),
                   "delay_import_edges": sum(item["type"] == "delay-import" for item in edges),
                   "distinct_windows_leaves": len(os_leaves),
                   "missing_DLL_names": len(missing), "private_symbol_failures": len(unresolved_symbols),
                   "MSYS_imports": sum(item["dll"].startswith("msys-") for item in edges)},
        "dynamic_dependencies_not_claimed_closed": ["Known Git clone transport launches native sh.exe, then git-upload-pack.exe; shell/import closure is MSYS-side and separate.", "Credential helpers, pagers, hooks, SSH, remote helpers, CA/certificate data and dynamically loaded plugins are command/configuration-dependent, not proven by this static graph."],
    }
    (OUTPUT / "static-graph.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "DLLs": [
        {"name": Path(node["path"]).name, "hash": node["sha256"],
         "receipt": node["provenance"].get("admission_receipt_sha256"),
         "package": node["provenance"].get("package"), "role": node["provenance"].get("admission_role"),
         "alias": node["existing_alias_metadata"]} for node in sorted(dlls, key=lambda node: node["path"])]}, indent=2))


if __name__ == "__main__":
    main()
