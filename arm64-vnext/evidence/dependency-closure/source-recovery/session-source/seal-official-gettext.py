import hashlib
import json
from pathlib import Path
import re
import shutil


root = Path(r"C:\ap11-accd-gettext01")
delivery = root / "delivery-02"
delivery.mkdir()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path):
    return {"path": str(path), "sha256": digest(path)}


files = []


def export(path, relative):
    destination = delivery.joinpath(*relative.split("/"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError(f"Duplicate delivery member {relative}")
    shutil.copyfile(path, destination)
    if digest(path) != digest(destination):
        raise ValueError(f"Export mismatch {path}")
    files.append({"original_path": str(path), "path": str(destination), "relative_path": relative,
                  "sha256": digest(destination)})
    return ref(destination)


official = [
    ("mingw-w64-clang-aarch64-gettext-runtime-1.0-1-any.pkg.tar.zst",
     "b5364a7c78cc4b73273a4a28e07e3c6d9cc8ec0ce269527409d944ab1c8f5a70"),
    ("mingw-w64-clang-aarch64-libiconv-1.19-1-any.pkg.tar.zst",
     "955499bc5cb73d86ea2850ece9bbdbbfd66b213e272e032f28147ecd42897e21"),
]
package_records = []
projection_records = []
projection_images = []
prefix = root / "projection-moved-c"
for name, expected in official:
    archive = root / "downloads" / name
    assert digest(archive) == expected
    audit_path = root / "evidence" / ("archive-" + name + ".json")
    audit = load(audit_path)
    assert audit["status"] == "all-archive-members-and-aa64-images-verified-not-runtime-admission"
    package_records.append({"archive": export(archive, "original-archives/" + name),
                            "signature": export(archive.with_name(name + ".sig"), "original-archives/" + name + ".sig"),
                            "content": ref(audit_path), "members": len(audit["members"]),
                            "PEs": len(audit["pe"]), "package_provenance": "Official signed binary package and its original metadata; no independent source rebuild or PCRE2 proof borrowed"})
    extracted = root / "extracted" / name
    for member in audit["members"]:
        path = extracted.joinpath(*member["path"].split("/"))
        assert digest(path) == member["sha256"]
        if member["path"] in (".PKGINFO", ".BUILDINFO", ".MTREE"):
            export(path, "package-metadata/" + name + "/" + member["path"])
        relative = member["path"]
        selected = relative in ("clangarm64/bin/libintl-8.dll", "clangarm64/bin/libiconv-2.dll")
        license_file = relative.startswith("clangarm64/share/licenses/") and "/libasprintf/" not in relative
        if not (selected or license_file):
            continue
        projected = "mingwarm64/" + relative[len("clangarm64/"):]
        target = export(path, "runtime-projection/" + projected)
        projection_records.append({"original_archive_sha256": expected, "archive_member": relative,
                                   "projected_member": projected, "sha256": target["sha256"],
                                   "role": "runtime-dll" if selected else "license",
                                   "unchanged": True, "name_changed": False})
        if selected:
            image = next(item for item in audit["pe"] if item["path"] == relative)
            projection_images.append(image)
            assert digest(prefix.joinpath(*projected.split("/"))) == target["sha256"]
assert len(projection_images) == 2

symbol_path = root / "evidence/projection-and-symbols.json"
symbols = load(symbol_path)
assert len(symbols["libintl_consumers"]) == 21
assert all(not item["missing_symbols"] for item in symbols["libintl_consumers"])
behaviors_path = root / "consumer-behaviors-03/result.json"
behaviors = load(behaviors_path)
assert behaviors["consumer_count"] == 21 and behaviors["passed_count"] == 21
all_module_records = []
for run in behaviors["runs"]:
    if not run["name"].startswith("setup"):
        assert sum(item["name"].lower() == "libintl-8.dll" for item in run["modules"]) == 1
    all_module_records.extend(run["modules"])
all_module_records.extend(behaviors["api"]["modules"])
module_evidence = []
system_root = Path(r"C:\Windows")
python_root = Path(r"C:\Program Files\Python314-arm64")
for module in all_module_records:
    path = Path(module["path"])
    if module["name"].lower().startswith("msys-"):
        raise ValueError("MSYS module in MinGW qualification")
    if path.is_relative_to(prefix):
        relative = path.relative_to(prefix).as_posix()
        if relative not in symbols["images"] or symbols["images"][relative]["sha256"] != module["sha256"]:
            raise ValueError(f"Unknown or changed projected image: {path}")
        classification = "bound-private-AA64-image"
    elif path.is_relative_to(system_root / "System32") or path.is_relative_to(system_root / "WinSxS"):
        classification = "Windows-system-module"
    elif path.is_relative_to(python_root):
        classification = "native-Python-ctypes-test-driver-only-not-payload"
    else:
        raise ValueError(f"Unexpected loaded module: {path}")
    if digest(path) != module["sha256"]:
        raise ValueError(f"Observed module changed: {path}")
    module_evidence.append({**module, "classification": classification})

map_files = symbols["files"]
for item in map_files:
    if digest(prefix.joinpath(*item["projected_path"].split("/"))) != item["sha256"]:
        raise ValueError("Moved projection bytes no longer match original map")
assert not (root / "projection-a").exists() and not (root / "projection-moved-b").exists()
clones = load(root / "clone-baseline-comparison/result.json")
assert clones["all_projection_bytes_restored"]
assert [item["raw_exit"] for item in clones["runs"][:3]] == [3221225477] * 3
scan = []
for image in projection_images:
    path = prefix / "mingwarm64/bin" / Path(image["path"]).name
    data = path.read_bytes()
    for encoding in ("latin1", "utf-16-le"):
        text = data.decode(encoding, errors="replace")
        for pattern, classification in (
            (r"/clangarm64[^\x00\r\n]{0,100}", "compiled-default-locale-limitation"),
            (r"(?i)(?:[\\/]session-state[\\/]|[\\/]copilot-worktrees[\\/]|[a-z]:[\\/]Users[\\/])", "private-path"),
        ):
            for match in re.finditer(pattern, text):
                scan.append({"file": path.name, "encoding": encoding, "offset": match.start(),
                             "value": match.group(), "classification": classification})
assert not any(item["classification"] == "private-path" for item in scan)

for directory in ("evidence", "consumer-behaviors-01", "consumer-behaviors-02", "consumer-behaviors-03",
                  "clone-baseline-comparison"):
    for path in (root / directory).iterdir():
        if directory == "evidence" and path.name.startswith("seal-component-evidence-02"):
            continue
        if path.is_file():
            export(path, "evidence/" + directory + "/" + path.name)
for name in ("official-gettext-command.ps1", "inspect-native-archive.py", "stage-official-gettext.py",
             "qualify-official-nls.py", "exercise-libintl-consumers.py", "compare-clone-libintl.py",
             "seal-official-gettext.py"):
    export(Path(__file__).with_name(name), "qualification-source/" + name)
export(root / "downloads/git-imap-send-32c4f768.c", "source-oracles/git-imap-send-32c4f768.c")
export(root / "downloads/msys2-public.gpg", "signature-keys/msys2-public.gpg")
export(root / "downloads/msys2-public-binary.gpg", "signature-keys/msys2-public-binary.gpg")

record = {
    "schema": 1, "status": "component-qualified-limited-MVP-candidate-awaiting-intake-verdict",
    "admission_owner": "a2dd0a44-30ad-4164-89bb-f2d7aaa0e5e5",
    "requested_projection_role": "official-clangarm64-libintl-runtime-only-limited-mvp",
    "original_packages": package_records, "projection_map": projection_records, "projected_images": projection_images,
    "package_provider_claim": False, "GNU_lineage_claim": False, "new_package_or_provides": False,
    "runtime_contract": "Actual Windows ARM64/UCRT C consumers and their imported private AA64 dependencies plus System32/API sets; no MSYS runtime import, injection or 907 capture claim. Emulated x64 GPG was used only for detached-signature verification.",
    "symbol_coverage": {"consumers": 21, "missing_symbols": 0, "evidence": ref(symbol_path)},
    "behavior": {"consumers": 21, "local_contracts_passed": 21, "positive_roles": 18,
                 "expected_negative_roles": {"git-http-fetch": 129, "git-http-push": 129, "git-imap-send": 1},
                 "evidence": ref(behaviors_path), "remote_service_tests_claimed": False,
                 "scope": "Reference advertisements, actual archive protocol, restricted Git shell, inetd Git protocol, smart HTTP CGI, remote-helper capabilities, envsubst, private Scalar config, native repository/French status, IDNA conversion, typed regex capture/nonmatch; missing-argument/configuration paths are negative tests, not successful network operations."},
    "live_module_records": module_evidence,
    "movement": {"A": str(root / "projection-a"), "B": str(root / "projection-moved-b"), "final": str(prefix),
                 "A_and_B_absent": True, "all_original_projected_bytes_identical": True,
                 "original_map": ref(symbol_path), "actual_missing_template_data_added": ref(root / "evidence/projection-template-data-delta.json")},
    "NLS": {"French_requested_explicitly": True, "official_CLI_default": "FAILED both before and after moving: English msgid despite existing French MO and valid locale",
            "unbound_default": "/clangarm64/share/locale",
            "normal_public_application_binding": "Exact French result before and after move, bound only to that application's actual moved root",
            "Git_actual_binding": "Both git.exe copies return package-catalog French 'Sur la branche main' from moved git.mo, without locale-path environment override",
            "Git_catalog": behaviors["git_catalog"], "IDNA_and_TRE_semantics_passed": True,
            "libidn2_and_libtre_translated_diagnostics": "NOT ADMITTED; English fallback only",
            "before": ref(root / "evidence/nls-progression-a.json"), "after": ref(root / "evidence/nls-progression-b.json")},
    "path_scan": scan,
    "progression": [
        "Initial signature verification failed raw2 because gpgv interpreted a Windows keyring path as a URL; preserved. Correct MSYS keyring path independently verified both vendor signatures raw0.",
        "135 members of the two official archives matched decompression byte-for-byte; all9 contained PE images are ordinary0xAA64. The excluded libasprintf C++ DLL imports libc++.dll; it is not part of the C projection.",
        "CLI/default-domain NLS failed with French explicitly requested, before/after actual move. Correct public application binding and actual Git binding succeeded; no binary/configuration rewriting.",
        "An invalid ctypes diagnostic treated internal data as the wrong pointer type and crashed raw0xC0000005; discarded as invalid, preserved, never attributed to the candidate. Public APIs used thereafter.",
        "First consumer fixture: six Git setup operations passed then bare clone crashed raw0xC0000005.",
        "Next21-role attempt had18 valid assertions and3 test-expectation failures. Exact catalog key 'On branch ' and pinned IMAP source return1 corrected those expectations; complete new21-role attempt passed.",
        "Bare clone A/B/A with only libintl changed: official/explicitly revoked diagnostic baseline/restored official all crashed raw0xC0000005. Official --bare --no-local also crashed. This independent Git/fixture blocker is not fixed or waived."
    ],
    "clone_baseline_failure": {"evidence": ref(root / "clone-baseline-comparison/result.json"),
                               "raw_exits": [item["raw_exit"] for item in clones["runs"]],
                               "revoked_baseline_never_distributed": True, "non_gettext_inputs_identical": True,
                               "official_projection_restored": True},
    "excluded": ["official gettext CLI/tools", "C++ libasprintf and libc++ closure", "docs/devel from runtime projection",
                 "unbound gettext-domain relocation", "universal locale diagnostics", "strict full-release GNU MINGWARM64 package admission",
                 "full Git MVP/end-to-end acceptance", "revoked gettext bytes"],
    "seal_control_scope": "Current sealer stdout/stderr are open while exporting and are not included in their own snapshot; earlier failed sealing attempt is preserved separately.",
}
record["export_inventory"] = {"path": str(delivery / "export-inventory.json")}
(delivery / "export-inventory.json").write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
record["export_inventory"]["sha256"] = digest(delivery / "export-inventory.json")
(delivery / "qualification.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
for item in files:
    assert digest(Path(item["path"])) == item["sha256"]
print(json.dumps({"receipt": str(delivery / "qualification.json"), "sha256": digest(delivery / "qualification.json"),
                  "projected_files": len(projection_records), "exported_files": len(files)}))
