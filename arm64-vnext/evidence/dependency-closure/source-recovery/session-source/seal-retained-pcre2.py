import hashlib
import json
from pathlib import Path
import shutil


root = Path(r"C:\ap11-accd-pcre2-mvp01")
output = root / "delivery-01"
output.mkdir()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path):
    return {"path": str(path), "sha256": digest(path)}


exports = []


def export(path, relative):
    target = output.joinpath(*relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError("Output collision")
    shutil.copyfile(path, target)
    assert digest(path) == digest(target)
    exports.append({"original": str(path), "path": str(target), "relative_path": relative, "sha256": digest(target)})
    return ref(target)


archive = root / "inputs/mingw-w64-aarch64-pcre2-10.48-1-any.pkg.tar.zst"
assert digest(archive) == "63ca004e570269889a30d4046a77946f09ddc6179a8be9b567e90cc9f4e3d7ec"
inspection = load(root / "evidence/archive-inspection.json")
assert inspection["status"] == "all-archive-members-and-aa64-images-verified-not-runtime-admission"
for member in inspection["members"]:
    assert digest(root.joinpath("extracted", *member["path"].split("/"))) == member["sha256"]
api_a = load(root / "evidence/api-a.json")
api_b = load(root / "evidence/api-b.json")
for result in (api_a, api_b):
    assert result["status"] == "fresh-retained-PCRE2-API-JIT-Unicode-POSIX-passed"
    assert len(result["runs"]) == 21 and all(item["passed"] for item in result["runs"])
    assert result["posix"]["passed"]
grep = load(root / "evidence/git-grep-02.json")
assert grep["status"] == "passed" and len(grep["runs"]) == 5
map_path = Path(r"C:\ap11-accd-gettext01\evidence\projection-and-symbols.json")
candidate = load(map_path)
provider = next(item for item in inspection["pe"] if item["path"] == "mingwarm64/bin/libpcre2-8.dll")
provided_names = {item["name"] for item in provider["exports"]}
provided_ordinals = {item["ordinal"] for item in provider["exports"]}
consumers = []
for path, image in candidate["images"].items():
    imports = [item for item in image["imports"] + image["delay_imports"] if item["dll"].lower() == "libpcre2-8.dll"]
    if not imports:
        continue
    symbols = [symbol for item in imports for symbol in item["symbols"]]
    missing = [symbol for symbol in symbols if symbol.get("name") not in provided_names and symbol.get("ordinal") not in provided_ordinals]
    assert not missing
    consumers.append({"path": path, "sha256": image["sha256"], "symbols": symbols, "missing": missing})
assert len(consumers) >= 19

package_ref = export(archive, "original-package/" + archive.name)
minimal_map = []
for relative in ("mingwarm64/bin/libpcre2-8.dll", "mingwarm64/share/licenses/pcre2/LICENCE.md"):
    source = root.joinpath("extracted", *relative.split("/"))
    target = export(source, "runtime-projection/" + relative)
    minimal_map.append({"archive_sha256": digest(archive), "archive_member": relative,
                        "projected_member": relative, "sha256": target["sha256"], "unchanged": True})
for file in (root / "evidence").iterdir():
    if file.is_file():
        export(file, "evidence/" + file.name)
for name in (".PKGINFO", ".BUILDINFO", ".MTREE"):
    export(root / "extracted" / name, "original-metadata/" + name)
for name in ("qualify-retained-pcre2.py", "probe-retained-pcre2-git.py", "inspect-native-archive.py",
             "qualify-official-nls.py", "seal-retained-pcre2.py"):
    export(Path(__file__).with_name(name), "qualification-source/" + name)
export(root / "grep-fixture.txt", "qualification-source/grep-fixture.txt")
selected = Path(r"C:\ap11-native-provider-intake\revoked-free-closures-v1\network-export.json")
assert digest(selected) == "3faec2f42d87e28236dcc451ab6f48c63b67bd54aee746e1ebdf9debf3f1f30f"
record = {
    "schema": 1, "status": "selected-compatible-retained-PCRE2-fresh-byte-qualification-complete",
    "package": {"identity": "mingw-w64-aarch64-pcre2", "version": "10.48-1", "original_archive": package_ref,
                "new_package_created": False, "metadata_rewritten": False, "declared_dependency": "mingw-w64-aarch64-gcc",
                "selection": ref(selected)},
    "source_provenance_limit": "The original export/receipt binds package bytes and overarching source/recipe context; no PCRE2-specific signed source archive, CMake command or independently reproducible build receipt is available. This fresh qualification does not invent it or borrow the different10.48-3 proof.",
    "target": "ordinary ARM64 Windows/UCRT; no MSYS runtime import or forced907 load",
    "archive_content": {"members": len(inspection["members"]), "payload_files": len(inspection["members"]) - 3,
                         "PEs": len(inspection["pe"]), "all_members_match_decompression": True,
                         "all_PE_machine_0xaa64": True, "private_path_hits": inspection["private_path_hits"],
                         "inspection": ref(root / "evidence/archive-inspection.json")},
    "PEs": inspection["pe"], "runtime_projection": minimal_map,
    "runtime_scope": "Package-owned unchanged libpcre2-8.dll plus BSD license; it imports only KERNEL32/UCRT API sets. Other widths/POSIX/CLIs were tested from the original package but are not included in the minimal Git role.",
    "basename_contract": {"required": "libpcre2-8.dll", "shipped": "libpcre2-8.dll", "matching_consumers": consumers,
                           "missing_import_symbols": 0, "current_Git_rebuilt": False,
                           "newer_10_48_3": "Unchanged archive7460d0 with libpcre2-8-0.dll is a different qualified candidate and remains non-plug-compatible with this pinned Git; no alias or renamed DLL used."},
    "fresh_API_qualification": {"before": ref(root / "evidence/api-a.json"), "after": ref(root / "evidence/api-b.json"),
                                "old_root_absent": not (root / "qualification-a").exists(),
                                "cases_per_root": 21, "case_passes_total": 42, "POSIX_capture_nonmatch_sets": 2,
                                "coverage": "8/16/32-bit actual interpreter via NO_JIT, direct JIT, Unicode property matching, lookahead, nonmatch, invalid pattern, POSIX capture offsets/nonmatch, exact live DLL path/hash.",
                                "original_full_upstream_suite_rerun": False,
                                "CLI_profile_limit": "Retained pcre2test reports neither readline nor editline; no full ordinary10.48-3 CLI feature claim."},
    "actual_Git_grep": {"evidence": ref(root / "evidence/git-grep-02.json"), "checks": 5,
                        "positive": 3, "expected_negative": {"nonmatch": 1, "invalid_pattern": 128},
                        "live_module_capture": "Recorded per run; exact selected unversioned DLL hash where captured"},
    "preserved_failed_grep_attempt": {"evidence": ref(root / "evidence/git-grep.json"),
                                     "cause": "The diagnostic supplied a Windows absolute path as a no-index pathspec, rejected as outside the directory tree. No regex was exercised. Rerun used the actual relative fixture name in its directory.",
                                     "five_raw_exits": [128] * 5,
                                     "initial_invalid_pattern_predicate": "Too broad and invalid as a positive; corrected to require the specific PCRE2 missing-closing-parenthesis error."},
    "independent_Git_clone_failure": {"evidence": ref(Path(r"C:\ap11-accd-gettext01\clone-baseline-comparison\result.json")),
                                      "scope": "Official/revoked/restored libintl all crashed in this isolated clone fixture. f6 owns full-root attribution; not a PCRE2 failure attribution or a waived MVP blocker."},
    "admission": "Intake owner a2dd decides; retain original selected identity, no new package or full-MVP claim.",
}
(output / "export-inventory.json").write_text(json.dumps(exports, indent=2) + "\n", encoding="utf-8")
record["export_inventory"] = ref(output / "export-inventory.json")
(output / "qualification.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
for item in exports:
    assert digest(Path(item["path"])) == item["sha256"]
print(json.dumps({"receipt": str(output / "qualification.json"), "sha256": digest(output / "qualification.json"),
                  "files": len(exports), "IAT_consumers": len(consumers), "missing_symbols": 0}))
