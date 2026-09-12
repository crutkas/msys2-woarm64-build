import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
spec = importlib.util.spec_from_file_location("archive_audit", Path(__file__).with_name("inspect-native-archive.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
pe = audit.pe


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


root = Path(r"C:\ap11-accd-gettext01")
source = Path(r"C:\ag-mvp-f6-20260911\candidate-01")
manifest_path = source.with_name("candidate-01.manifest.json")
boundary_path = source.with_name("libintl-consumer-boundary-01.json")
assert digest(manifest_path) == "a2052594e723bbc0f419cc546c19252b804af51d2440e64a29c847056bb316c3"
assert digest(boundary_path) == "ecaa96a91879c81ec43ea3f51b359994881f08510ce58fb74d45fd6c56d88718"
manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
boundary = json.loads(boundary_path.read_text(encoding="utf-8-sig"))
projection = root / "projection-a"
projection.mkdir()
records = []


def copy_file(path, relative, provenance, role):
    destination = projection.joinpath(*relative.split("/"))
    before = digest(path)
    if destination.exists():
        if digest(destination) != before:
            raise ValueError(f"Projection collision: {relative}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    if digest(destination) != before or digest(path) != before:
        raise ValueError(f"File changed during copy: {path}")
    records.append({"original_path": str(path), "projected_path": relative, "sha256": before,
                    "provenance": provenance, "role": role})


for relative, member in manifest["files"].items():
    if not relative.startswith("mingwarm64/"):
        continue
    if not (relative.startswith(("mingwarm64/bin/", "mingwarm64/libexec/git-core/",
                                 "mingwarm64/share/locale/", "mingwarm64/share/licenses/",
                                 "mingwarm64/ssl/", "mingwarm64/etc/ssl/"))):
        continue
    path = source.joinpath(*relative.split("/"))
    if digest(path) != member["sha256"]:
        raise ValueError(f"Candidate member mismatch: {relative}")
    if member.get("machine") and member["machine"].lower() != "0xaa64":
        raise ValueError(f"Non-ARM64 candidate: {relative}")
    copy_file(path, relative, member["provenance"], "consumer-diagnostic-context-not-package-admission")

officials = [
    ("mingw-w64-clang-aarch64-gettext-runtime-1.0-1-any.pkg.tar.zst",
     "b5364a7c78cc4b73273a4a28e07e3c6d9cc8ec0ce269527409d944ab1c8f5a70"),
    ("mingw-w64-clang-aarch64-libiconv-1.19-1-any.pkg.tar.zst",
     "955499bc5cb73d86ea2850ece9bbdbbfd66b213e272e032f28147ecd42897e21"),
]
for archive, package_hash in officials:
    prefix = root / "extracted" / archive / "clangarm64"
    for path in prefix.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(prefix).as_posix()
        if not (relative.startswith(("share/locale/", "share/licenses/")) or
                relative in ("bin/libintl-8.dll", "bin/libiconv-2.dll", "bin/libcharset-1.dll",
                             "bin/gettext.exe", "bin/ngettext.exe", "bin/envsubst.exe",
                             "bin/printf_gettext.exe", "bin/printf_ngettext.exe")):
            continue
        role = "official-c-runtime-or-license" if relative.endswith(".dll") or relative.startswith("share/licenses/") else "NLS-qualification-data-or-tool"
        copy_file(path, "mingwarm64/" + relative, {"official_archive": archive, "sha256": package_hash}, role)

images = {}
for path in projection.rglob("*"):
    if not path.is_file():
        continue
    data = path.read_bytes()
    if data.startswith(b"MZ"):
        identity = pe(data)
        if not identity["ordinary_arm64"]:
            raise ValueError(f"Non-ARM64 projected PE: {path}")
        images[path.relative_to(projection).as_posix()] = {"sha256": digest(path), **identity}
intl = images["mingwarm64/bin/libintl-8.dll"]
intl_names = {entry["name"] for entry in intl["exports"]}
intl_ordinals = {entry["ordinal"] for entry in intl["exports"]}
consumers = []
for consumer in boundary["consumers"]:
    relative = consumer["payload_path"]
    image = images[relative]
    if image["sha256"] != consumer["sha256"]:
        raise ValueError(f"Consumer changed: {relative}")
    imports = [item for item in image["imports"] + image["delay_imports"]
               if item["dll"].lower() == "libintl-8.dll"]
    if not imports:
        raise ValueError(f"Consumer no longer imports libintl: {relative}")
    symbols = [symbol for item in imports for symbol in item["symbols"]]
    missing = [symbol for symbol in symbols
               if symbol.get("name") not in intl_names and symbol.get("ordinal") not in intl_ordinals]
    consumers.append({"path": relative, "sha256": image["sha256"], "machine": image["machine"],
                      "symbols": symbols, "missing_symbols": missing})
    if missing:
        raise ValueError(f"Unresolved libintl symbols: {relative}: {missing}")
assert len(consumers) == 21
report = {
    "status": "static-symbol-coverage-only-not-behavior-or-admission",
    "projection": str(projection), "manifest": str(manifest_path),
    "manifest_sha256": digest(manifest_path), "boundary_sha256": digest(boundary_path),
    "files": records, "images": images, "libintl_consumers": consumers,
    "official_lineage": "Original signed CLANGARM64 bytes; not a GNU MINGWARM64 package",
}
(root / "evidence" / "projection-and-symbols.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"files": len(records), "PEs": len(images), "consumers": len(consumers),
                  "missing_libintl_symbols": sum(len(item["missing_symbols"]) for item in consumers)}))
