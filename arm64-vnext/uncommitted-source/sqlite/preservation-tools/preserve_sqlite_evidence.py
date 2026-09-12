"""Preserve measured SQLite/MVP evidence only; never copy payloads or build trees."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

WORKTREE = Path(r"C:\Users\crutkasLocal\.copilot\repos\copilot-worktrees\msys2-woarm64-build\crutkas-probable-lamp")
DESTINATION = WORKTREE / "arm64-vnext/evidence/sqlite"
ROOTS = [
    ("sqlite-original", Path(r"C:\ag-sqlite-e138-01")),
    ("sqlite-continuation", Path(r"C:\ag-sqlite-resume-01")),
    ("sqlite-combined", Path(r"C:\ag-sqlite-combined-01")),
    ("independent-mvp", Path(r"C:\ag-mvp-independent-sqlite-20260911")),
]
EXCLUDED_DIRECTORIES = {
    "runtime", "payload", "bin", "source", "sources", "inputs", "consumers", "home",
    "temp", "tmp", "cache", "stage", "splits", "tsrc", "compiler", "bootstrap",
    "host-compiler", "tcl", "tcl-source", "readline", "ncurses", "zlib", "observer",
    "ssh-fixture-driver", "controller-home", "controller-temp", "ssh-fixture-driver",
    "moved candidate with spaces", "fresh moved Git Bash extraction",
    "sealed inputs", "evidence", ".git", "__pycache__", "native-exits",
}
EVIDENCE_PREFIXES = (
    "configure-", "build-run-", "extensions-run-", "install-run-", "proof-",
    "quicktest-", "veryquick-per-file-", "handoff-", "host-jim-", "foreign-environment-",
    "environment-differential-", "mksourceid-diagnostic-", "fts5secure3-", "round1-hang-",
    "halt-", "baseline-", "shell-composition-", "upstream-shell5-", "inputs-",
    "ordinary-", "package-", "replay-", "final-901256b", "quicktest-08-scale",
)
TEXT_SUFFIXES = (".json", ".log", ".stdout", ".stderr")
SPECIAL_LOGS = {"stdout.bin", "stderr.bin", "test-out.txt", "shell5-verbose.txt", "cases.tsv"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def measured_file(path):
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in SPECIAL_LOGS


def selected_files():
    selected = {}
    excluded = []
    for label, root in ROOTS:
        if not root.is_dir():
            raise ValueError(f"Measured evidence root missing: {root}")
        for path in root.iterdir():
            if path.is_file() and measured_file(path):
                selected[f"{label}/{path.name}"] = path
            elif path.is_dir() and path.name.startswith(EVIDENCE_PREFIXES):
                pending = [path]
                while pending:
                    directory = pending.pop()
                    for entry in directory.iterdir():
                        if entry.is_symlink() or entry.is_junction():
                            continue
                        if entry.is_file() and measured_file(entry):
                            selected[f"{label}/{entry.relative_to(root).as_posix()}"] = entry
                        elif entry.is_dir():
                            name = entry.name
                            if name in EXCLUDED_DIRECTORIES or name.startswith(
                                    ("testdir", "testrunner_bld_", "unexpected-bootstrap-cache")):
                                continue
                            # Runtime/build work directories may contain arbitrary fixtures.
                            # Only their already named measured logs are retained separately.
                            if name == "work" or name.endswith(".git") or name in {
                                "source repo", "served.git", "encrypted clone", "rejected clone",
                                "https-clone", "clone", "child", "first moved extraction", "second moved extraction",
                            }:
                                continue
                            pending.append(entry)
        # This folder contains real build outputs. Select only named logs, never
        # copy its source, database fixtures, generated headers or binaries.
        if label == "sqlite-original":
            for name in ("config.log", "testrunner.log", "test-out.txt", "native-test-path.txt"):
                path = root / "build-06" / name
                if path.is_file():
                    selected[f"{label}/build-06/{name}"] = path
            for directory in root.glob("quicktest-build-*"):
                for name in ("config.log", "testrunner.log"):
                    path = directory / name
                    if path.is_file():
                        selected[f"{label}/{path.relative_to(root).as_posix()}"] = path
        if label == "sqlite-combined":
            for path in (root / "inputs-01/evidence").glob("*.json"):
                selected[f"{label}/{path.relative_to(root).as_posix()}"] = path
        if label == "independent-mvp":
            for directory in root.glob("final-901256b*"):
                path = directory / "sealed inputs/artifact-receipt.json"
                if path.is_file():
                    selected[f"{label}/{path.relative_to(root).as_posix()}"] = path
    # Full verbose upstream output is diagnostic evidence, even though its
    # generic filename has .txt rather than .log.
    original = ROOTS[0][1]
    for directory in original.glob("*"):
        if directory.is_dir() and directory.name.startswith(("quicktest-", "veryquick-per-file-")):
            for path in (directory / "verbose").glob("*.txt"):
                selected[f"sqlite-original/{path.relative_to(original).as_posix()}"] = path
    return selected


def chunks(path, maximum=45 * 1024 * 1024):
    with path.open("rb") as stream:
        while data := stream.read(maximum):
            yield data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args()
    selected = selected_files()
    sizes = {name: path.stat().st_size for name, path in selected.items()}
    print(json.dumps({"files": len(selected), "bytes": sum(sizes.values()),
                      "largest": sorted(sizes.items(), key=lambda x: -x[1])[:15]}, indent=2), flush=True)
    if not args.copy:
        return
    DESTINATION.mkdir(parents=True, exist_ok=False)
    (DESTINATION / ".gitattributes").write_text(
        "# Preserve evidence bytes exactly, including raw textual stdout/stderr logs.\n"
        "* -text\n** -text\n", encoding="ascii", newline="\n")
    rows = []
    for index, (name, source) in enumerate(sorted(selected.items()), 1):
        with source.open("rb") as stream:
            magic = stream.read(8)
        if magic.startswith((b"MZ", b"PK\x03\x04", b"MDMP", b"\x28\xb5\x2f\xfd", b"\x1f\x8b")):
            raise ValueError(f"Disallowed payload/archive/dump masquerading as evidence: {source}")
        before = digest(source)
        size = source.stat().st_size
        destination = DESTINATION / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        parts = []
        if size > 45 * 1024 * 1024:
            for number, data in enumerate(chunks(source), 1):
                target = destination.with_name(destination.name + f".part-{number:03d}")
                with target.open("xb") as stream:
                    stream.write(data)
                part_sha = hashlib.sha256(data).hexdigest()
                if digest(target) != part_sha:
                    raise ValueError("Evidence chunk copy differs")
                parts.append({"path": target.relative_to(DESTINATION).as_posix(),
                              "size": len(data), "sha256": part_sha})
        else:
            shutil.copyfile(source, destination)
            if digest(destination) != before:
                raise ValueError(f"Evidence copy differs: {source}")
        if digest(source) != before or source.stat().st_size != size:
            raise ValueError(f"Evidence changed during preservation: {source}")
        row = {"path": name, "original_absolute_path": str(source), "size": size,
               "sha256": before, "parts": parts, "copied_bytes_unchanged": True}
        rows.append(row)
        if index % 500 == 0:
            print(f"Preserved {index}/{len(selected)} evidence files", flush=True)
    scope = {
        "schema": 1,
        "scope": "Byte-preserved measured SQLite and independent MVP consumer evidence; not payloads, archives, build trees or general provider admission",
        "authoritative_sqlite_package_flags": {"mvp_runtime_only": True, "provider_admitted": False},
        "qualification_limits": [
            "Original SQLite quicktest: 885632 tests, 94 errors, 36 sanitizer-dependent jobs omitted; failures not waived.",
            "Original independent veryquick: 398797 tests, 215 errors in 22 failed files; failures not waived.",
            "Native positive SQLite compatibility consumers on combined907 passed; minimal runtime-only package receipt remains provider_admitted=false.",
            "Earlier shell5 assertion success did not promote nine raw256 observer failures.",
            "First final MVP ZIP readback failed in the SSH fixture because spaced known-host paths were not quoted inside OpenSSH -o.",
            "Fixed-controller final readback passed on the same immutable artifact; original failed receipts are preserved, not rewritten.",
            "Independent MVP consumer results do not claim full release, universal provider admission, all-short-descendant module completeness or a general raw-exit decoder.",
        ],
        "excluded_by_instruction": [
            "PE executables and DLLs", "Package and ZIP archives", "Build/source/runtime payload trees",
            "Binary minidumps (their hashes and decoded frame evidence are retained)",
            "Temporary/private SSH keys, generated repositories and database fixtures",
            "Per-invocation native-exits leaf files (aggregate observer native-job receipts retain measured exits and coverage)",
        ],
        "files": rows,
    }
    (DESTINATION / "preservation-manifest.json").write_text(json.dumps(scope, indent=2) + "\n", encoding="utf-8", newline="\n")
    header = """# SQLite measured evidence preservation

These are original measured receipts, logs and manifests copied byte-for-byte before the machine wipe.
**Explicit receipt flags govern: `mvp_runtime_only: true` and `provider_admitted: false`.**
Nothing in this index upgrades that minimal SQLite runtime compatibility proof to provider admission.
Independent final MVP consumer replay is a separate limited-engineering scope, not full-release admission.

## Outcomes and retained failures

- Original native SQLite seven-split build and positive API/CLI/Tcl/extension evidence are retained.
- The complete upstream quicktest recorded **94 errors / 885,632 tests** with 36 sanitizer-dependent jobs omitted.
- Independent veryquick recorded **215 errors / 398,797 tests**, with 22 failed files.
- Permission, symlink, WAL/journal, missing sanitizer-library, environment, raw-exit and pipe-hang evidence stays failed or scoped as originally recorded.
- The shell/TDBC continuation and combined-runtime compatibility proof do not waive prior upstream failures or the raw-256 observer gate.
- The first independent final ZIP verifier failed in its spaced-path SSH fixture. Its original failed result and input readback are retained alongside the later successful fixed-controller replay of the **same** artifact bytes.
- No PE payloads, archives, dumps, source/build trees, generated repositories, database fixtures or private keys are preserved here. Their exact hashes/provenance remain in the measured receipts.

## Byte identity and rehydration

`.gitattributes` applies `-text` recursively so Git must not normalize these bytes.
`preservation-manifest.json` and the table below give the original absolute Windows path, original byte count and SHA-256 of every preserved file.
Paths are evidence provenance only, **not** live prerequisites to recreate on the new host.
Files exceeding 45 MiB are represented by numbered byte-exact `.part-NNN` files: concatenate their bytes in listed order, then verify the original SHA-256.
Do not use a text editor, text pipeline or newline conversion to reassemble them.

The saved receipts distinguish already-built payload provenance from new runtime compatibility validation.
Unavailable source identity, historic failures and candidate/admission limitations are not invented or erased.

## Per-file SHA-256 index

| Preserved relative path | Original absolute path | Bytes | SHA-256 |
|---|---|---:|---|
"""
    lines = [header]
    for row in rows:
        relative = row["path"]
        if row["parts"]:
            relative += " (concatenate parts)"
        lines.append(f"| `{relative}` | `{row['original_absolute_path']}` | {row['size']} | `{row['sha256']}` |\n")
        for part in row["parts"]:
            lines.append(f"| `{part['path']}` | byte chunk of `{row['original_absolute_path']}` | {part['size']} | `{part['sha256']}` |\n")
    (DESTINATION / "README.md").write_text("".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps({"destination": str(DESTINATION), "original_files": len(rows),
                      "bytes": sum(row["size"] for row in rows),
                      "manifest_sha256": digest(DESTINATION / "preservation-manifest.json")}), flush=True)


if __name__ == "__main__":
    main()
