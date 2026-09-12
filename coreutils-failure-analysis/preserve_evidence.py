"""Emergency byte-exact preservation before the source machine is destroyed."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


DEST = Path("arm64-vnext/evidence/coreutils")
FAILURES = Path(r"C:\ag-exit-e138-01\coreutils-failures-20260911-01")
MVP = Path(r"C:\ag-exit-e138-01\coreutils-20260910-01")
PRODUCER = Path(r"C:\ag-coreutils-e138-01\coreutils-native-13")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def select_files():
    selected = {}

    def add(source, relative, proves, required=True):
        source = Path(source)
        if not source.is_file():
            if required:
                raise FileNotFoundError(source)
            return
        key = str(relative).replace("\\", "/")
        if key in selected:
            raise RuntimeError(f"Duplicate evidence destination: {key}")
        selected[key] = (source, proves)

    for source in FAILURES.iterdir():
        if source.is_file() and source.suffix in (".json", ".log", ".h"):
            add(source, Path("failure-analysis") / source.name, "Exact grouped analysis, provenance, or raw replay summary; historical verdicts unchanged.")
    for folder, label in (("retained", "Original per-test FAIL/ERROR log, status, testcase, or selected configuration snapshot."),
                          ("mechanism-source", "Exact source/API excerpt used to localize a failure mechanism.")):
        for source in (FAILURES / folder).rglob("*"):
            if source.is_file():
                add(source, Path("failure-analysis") / source.relative_to(FAILURES), label)
    for case in (FAILURES / "runs").iterdir():
        if case.is_dir():
            for name in ("result.json", "native-job.json", "target.log", "observer.log"):
                add(case / name, Path("failure-analysis/runs") / case.name / name,
                    "Unmodified controlled replay record or raw process output, including nonzero exits, timeouts and coverage gaps.")
    for name in ("result.json", "build.log", "api-control.c"):
        add(FAILURES / "api-build" / name, Path("failure-analysis/api-build") / name,
            "Test-only runtime API diagnostic source, build command or log; executable excluded.")
    for source in MVP.iterdir():
        if source.is_file() and source.suffix in (".json", ".log"):
            add(source, Path("mvp") / source.name, "Original limited utility selection, exact PE/import closure, package ownership or qualification summary.")
    for case in (MVP / "cases").iterdir():
        if not case.is_dir():
            continue
        for source in case.iterdir():
            if source.is_file() and source.suffix in (".json", ".log", ".stdout", ".stderr"):
                add(source, Path("mvp/cases") / case.name / source.name,
                    "Original/moved-root execution record or raw log; all earlier failed harness attempts retained.")
        debug = case / "debug"
        if debug.is_dir():
            for source in debug.iterdir():
                if source.is_file() and (source.suffix == ".json" or source.name in ("stdout.bin", "stderr.bin")):
                    add(source, Path("mvp/cases") / case.name / "debug" / source.name,
                        "Raw debugger event/generation/mapped-module evidence or stdout/stderr capture; .bin here is a log, not executable payload.")
        snapshots = case / "source"
        if snapshots.is_dir():
            for source in snapshots.glob("*.py"):
                add(source, Path("mvp/cases") / case.name / "source" / source.name,
                    "Exact per-run harness source snapshot, preserving intermediate failed-harness provenance.")
    for folder in ("package", "findutils-mvp-projection", "sed-mvp-projection"):
        for source in (MVP / folder).iterdir():
            if source.is_file() and source.suffix == ".json":
                add(source, Path("mvp") / folder / source.name,
                    "Candidate archive hash, exact file ownership, source inventory or limited-scope metadata; archive/payload excluded.")
    for folder in ("provenance", "licenses"):
        for source in (MVP / folder).rglob("*"):
            if source.is_file():
                add(source, Path("mvp") / source.relative_to(MVP),
                    "Original recipe/patch, source identity or license; no source archive or build tree.")
    for name in ("result.json", "build.log", "pty-control.c"):
        add(MVP / "pty-build" / name, Path("mvp/pty-build") / name,
            "Non-shipping owned-PTY diagnostic source/build receipt; genuine strict-closure failure remains recorded.")
    for name in ("build.log", "observed.log", "stage-coreutils.sha256", "stage-gmp.sha256"):
        add(PRODUCER / name, Path("original-producer") / name,
            "Original coreutils-native-13 raw suite/build output or exact stage hash list.")
    add(PRODUCER.parent / "native-coreutils-consumer-01/consumer-manifest.json",
        "original-producer/consumer-manifest.json", "Historical per-file consumer lineage; not a complete producer qualification.")
    for name in ("native-bash-test-utilities.manifest.json", "admission.json"):
        add(Path(r"C:\ag-utils-e138-01\native-utilities-06") / name, Path("original-composition") / name,
            "825-file native utility composition and historical d70-only scope.")
    external = {
        r"C:\ap11-native-provider-intake\coreutils-rootcause-evidence-v1\verdict.json": "intake/rootcause-verdict.json",
        r"C:\ap11-native-provider-intake\native-utilities-limited-mvp-v1\export.json": "intake/limited-mvp-export.json",
        r"C:\ap11-native-provider-intake\native-utilities-limited-mvp-v1\handoff.json": "intake/limited-mvp-handoff.json",
        r"C:\ag-bash907-20260911-02\qualification-handoff-01\handoff.json": "adjacent/bash907-handoff.json",
    }
    unavailable = []
    for source, target in external.items():
        if Path(source).is_file():
            add(source, target, "Adjacent owner's exact verdict/handoff; its recorded scope is not broadened.")
        else:
            unavailable.append({"original_path": source, "reason": "Not present at emergency preservation time; prior conversation is not substituted for file bytes."})
    return selected, unavailable


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    manifest_path = DEST / "manifest.json"
    if manifest_path.exists():
        raise RuntimeError("Evidence preservation requires fresh output; never overwrite a preserved bundle.")
    selected, unavailable = select_files()
    entries = []
    suspect = re.compile(rb"github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    for relative, (source, proves) in sorted(selected.items()):
        target = DEST / relative
        data = source.read_bytes()
        if data.startswith(b"MZ"):
            raise RuntimeError(f"Executable bytes must not enter the evidence bundle: {source}")
        if suspect.search(data):
            raise RuntimeError(f"Credential-shaped content requires manual handling; no bytes published: {source}")
        if len(data) >= 90 * 1024 * 1024:
            raise RuntimeError(f"Evidence file too large for ordinary Git: {source}")
        before = hashlib.sha256(data).hexdigest()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
        copied, after = sha(target), sha(source)
        if before != copied or before != after:
            raise RuntimeError(f"Source changed during emergency copy: {source}")
        entries.append({"file": relative, "sha256": copied, "bytes": len(data),
                        "original_path": str(source), "proves": proves,
                        "before_sha256": before, "after_source_sha256": after})
    manifest = {"schema": 1, "preservation": "Exact source bytes; no reformatting or newline conversion",
                "files": entries, "unavailable_adjacent_receipts": unavailable,
                "excluded": ["executables/DLLs", "package/source archives", "payload/extracted/build trees",
                             "temporary workdirs and ACL test objects", "runtime/compiler SDKs"]}
    with manifest_path.open("wb") as stream:
        stream.write((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    readme = r"""# Coreutils evidence: emergency preservation and rehydration

This directory preserves original local evidence **byte-for-byte** before the source
machine is reformatted. The original `C:\ag-*`, `C:\ap*` and `C:\agtc-*` paths in
receipts will no longer exist. Treat them as provenance labels, not runnable paths.
The catalog below maps each preserved file to its absolute original path and full
SHA-256. `.gitattributes` applies `-text` to every file in this subtree.

## What a fresh session must know

The original question was whether the retained **41 FAIL** results collapse into
common causes (line endings, locale/NLS, Windows permissions, or POSIX filesystem
assumptions) or represent independent defects. **UNRESOLVED in full:** the analysis
did establish the primary grouping below, but two secondary historical mechanisms,
seven persistent permission cases, and incomplete full-suite coverage remain.
Do not erase the completed grouping, and do not claim that all 41 are fixed.

## Prominent finding: native exec presents a different argv[0]

**Seventeen failures share an argv[0] diagnostic/test-filter mechanism.**
Together with the 14 permission cases, two primary mechanisms account for
**31 of 41 failures**. This is a major diagnosis, not a successful full-suite
outcome: **grouping causes is not fixing defects**. Every original FAIL remains
FAIL in its original receipt; successful fresh controlled replays are separate.

The retained native process received an absolute `/cygdrive/.../src/program`
name where the harness expected a basename. Gnulib intentionally preserves
an explicitly supplied pathname in diagnostics. This is an exec/launch boundary
that may affect consumers beyond Coreutils; do not paper over it by stripping
paths from output. Read `lib/progname.c`, the original launch logs, and the
coherent-native-parent A/B evidence.

Cross-reference **crutkas/msys2-runtime#32**, "Preserve argv semantics and close
runtime link mechanics". The emergency coordinator reported it green and
mergeable with 18 successful checks at preservation time; that is a time-bound
report, not a permanent GitHub status guarantee. It may address part of this
boundary or require extension; the relationship is not assumed proven.
URL: https://github.com/crutkas/msys2-runtime/pull/32

Also cross-reference Bash owner session
`2f84a483-facd-42d6-8afd-f265471bb751` and its evidence handoff
`C:\ag-bash907-20260911-02\qualification-handoff-01\handoff.json`
(preserved under `adjacent/` if available). It investigated Ctrl-C on
`sleep 60 | cat` returning shell `$?=0` rather than `130`, with an exec/process-group
membership hypothesis. **These are not established as the same defect.**
Later updates reported matching member PGIDs/foreground ownership in a controlled
run and retained intermittent/runtime-only failure `ad40`; that narrows the
hypothesis rather than proving the broad claim. The final Bash handoff records
82 parent raw0, two raw1, two raw1460 and coverage gaps, not 82 fully covered passes.

The immutable original completed-test tally is **48 PASS / 41 FAIL / 23 SKIP /
4 ERROR**. The original full suite never completed. `original-producer/build.log`
and `observed.log` each have SHA-256
`3c8434c393ee9716816c938a98a127951dee307441f334c38e44e3816d8adc4a`.

| Primary grouping (disjoint) | FAIL | ERROR |
|---|---:|---:|
| Absolute argv[0] diagnostics and dependent test-filter contamination | 17 | 0 |
| Permission model / genuine MSYS-NTFS POSIX semantic gaps | 14 | 0 |
| Mixed-runtime paths, PIDs, procfs, descriptors and symlinks | 6 | 2 |
| Invalid argument byte converted to private-use UTF-8 | 1 | 0 |
| Compound help/version launch and support-file problems | 1 | 0 |
| Secondary legacy launch mechanism not confirmed | 2 | 0 |
| Oversized inherited environment rejected by xargs | 0 | 1 |
| RTLD_NEXT absent: injected readdir helper cannot compile | 0 | 1 |
| **Total** | **41** | **4** |

Read `failure-analysis/result.json` first, then `failure-analysis/causes.json`.
They bind all 45 individual tests, source/log witnesses and controlled replays.
The two unresolved secondary cases are `join.pl`'s high-byte separator and
`wc-files0-from.pl`'s `/dev/null` input under the historical mixed launch. Correct
native subcases do not retroactively prove the missing old argv/fd snapshots.

Thirty-two unchanged shell scripts were replayed with coherent native inputs:
latest results were **19 shell raw0 / 12 raw1 / 1 bounded-incomplete raw1460**.
Private ACL controls removed five additional failures, but seven shell cases
still fail POSIX delete/traversal expectations even with ACLs. Direct runtime
calls reproduce those inconsistencies without Coreutils: `access(parent,W_OK)`
denies while `unlinkat(child)` succeeds; opening through an unsearchable parent
succeeds while `chdir` denies. These are real semantic gaps, not waived tests.
The 12 Perl scripts were analyzed from complete retained logs/source plus focused
native subcases; **they were not all rerun as complete Perl scripts**.

The full help/version replay remained bounded-incomplete and needs a genuine
AA64 native MSYS `gzip` helper. Intake found only x64 bootstrap gzip copies.
Do not copy those, fake compressed fixtures, or report the help test as passing.
Timeout records preserve their coverage gaps: the analysis performed 82 runs,
18,915 created versus 18,895 observed generations; the 20 gaps are rejected
timeout observations, not successful coverage. All owned job trees were drained.

**Standing rule:** a test that genuinely does not apply must be documented with
the exact assumption it makes. A real failure must never be reclassified as
inapplicable to improve the number. Preserve raw Windows DWORDs, semantic test
results and observer verdicts separately. No stubs, status-normalization shims,
or retrospective upgrading of old receipts.

## Adjacent findings and utility overlap

The user reported a **measured official CLANGARM64 gettext defect**:
`bindtextdomain` returns the compiled-in `/clangarm64/share/locale` regardless;
localized output falls back to English even with `LANGUAGE` and `LC_ALL` set and
`setlocale` succeeding. If a future failure is catalog/translation-related,
check that exact loaded provider rather than ignoring the finding. However,
the retained Coreutils failures force the C locale and use the separate MSYS
`msys-intl-8.dll` provider. This analysis evidenced **zero catalog-translation or
newline-only cause groups**; it did not transfer the CLANGARM64 finding across ABI.
The original CLANGARM64 measurement receipt was not produced in this lane.

Session `2f84a483` found the Bash upstream suite needs genuine **test-only
utilities beyond the limited MVP**, including `chmod`, `stty` and `false`.
Those binaries must not be silently omitted or stubbed when testing Bash.
`chmod`'s arbitrary POSIX modes are limited under `noacl`; `stty` needs a real
terminal and the default ConPTY path exposed external proxy/coverage issues;
`false` intentionally exits nonzero. Full Bash testing also exposed a genuine
compiler test dependency for `glob-bracket.tests`; unresolved Bash timeouts are
not automatically Coreutils defects.

The requested inventory was **37 GNU Coreutils candidates plus find/xargs/sed**.
All 40 candidates were present with AA64 PE headers. Limited intake admitted only
**34 Coreutils commands plus the three extras = 37 shipped commands**, 43 owned
files in three archives. This distinction matters when someone says "MVP 37".

The 34 named Coreutils projection commands were:
`cat cp mkdir mv rm rmdir ln readlink pwd env uname dd wc sort uniq head tail cut
tr sleep true test stat touch basename dirname tee printf expr install ls timeout
realpath od`.
The separately named extras were `find`, `xargs`, `sed`.
`chmod`, `stty`, and `false` were withheld from positive/shipping claims, but remain
real test-only dependencies. The seven assembler-critical commands were
`cat cp env mkdir rm sort uniq`. Extra-command behavior was limited to
`LC_ALL=C`; their compiled private locale paths remained an explicit limitation.

MVP raw runs, failed intermediate harness attempts, per-run source snapshots,
original/moved-root results, package ownership and source hashes are under `mvp/`.
The exact current qualification runtime was AA64 `msys-2.0.dll`
`907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c`.
The original native13 producer runtime was `baa144d1848ea17e8dee944279f4dc707f45581bc5a5e912b451a87cbe7abd15`.
Never silently substitute one for the other. There was no complete native13
compiler-input manifest, original PKGBUILD or successful full producer suite.
Limited MVP admission is not full Coreutils/findutils/sed provider admission.

## Rehydrate without this machine

1. Verify this checkout: `python arm64-vnext/evidence/coreutils/verify.py`.
2. Use `manifest.json` to resolve old absolute paths to preserved relative files.
   Preserve receipts themselves unchanged; write a separate relocation map.
3. Read original log/status files before the grouped conclusions. Consult each
   failed test's source definition and its exact native replay separately.
4. Reobtain sources using the preserved archive/recipe hashes. Rebuild/requalify
   absent native binaries and helpers in fresh private roots. Do not infer a
   producer history from only a PE header or copied library.
5. Use one coherent MSYS parent/runtime/root with explicit PATH and mount/symlink
   settings. Compare modes through private `noacl` versus ACL controls without
   changing global privileges. Raw status and complete generation coverage remain
   mandatory; the historical raw-only observer does not grant an exit-domain proof.
6. Do not run plain `make` in a runtime tree: the historical `gentls_offsets`
   `.long` versus ARM64 `.word` mismatch can overwrite valid offsets.
7. Finish the seven permission cases and two unconfirmed secondary mechanisms;
   acquire a real AA64 gzip provider and complete full scripts before broad claims.

Published tooling before this preservation:
- `36339064525fa27372bdff5dcd4e31bbcb2d4a32`: `coreutils-qualification/`.
- `5b28927d5b974d5bb63ce0cf061aaa2b42505dea`: `coreutils-failure-analysis/`.
- Root-cause result SHA: `4131eddd53bcc4ad53ffc4a6b0ec73cdf578d4579cee7519368547cbb9eb3e9d`.
- Causes ledger SHA: `46d85ebbb726b65dfca1bd2f6fa61814c4a2db066e0f72598f7d148769273635`.
- MVP result SHA: `7716bc2e291ac0f45ecc21a4a7bdc804c292766b00d14565dc70a240938bacf5`.

No binaries, package/source archives, SDKs, full extracted/build trees or temporary
ACL test workdirs are included. Selected configuration/test-source snapshots are
evidence, not runnable build trees. Files named `stdout.bin` / `stderr.bin` below
are raw logs, never executable payloads. `.gitattributes`, `verify.py`,
`manifest.json` and this README are newly generated preservation controls rather
than historical receipts. A README cannot embed its own stable SHA-256; its bytes
are protected by the pushed Git commit. All historical evidence hashes are below.

## Preservation control hashes

"""
    readme += f"- `manifest.json`: `{sha(manifest_path)}` (new provenance index).\n"
    for name in (".gitattributes", "verify.py"):
        readme += f"- `{name}`: `{sha(DEST / name)}` (new preservation control).\n"
    readme += f"\nPreserved **{len(entries)} files**, **{sum(row['bytes'] for row in entries):,} bytes**.\n"
    if unavailable:
        readme += "\n### Adjacent receipts unavailable locally\n\n"
        for row in unavailable:
            readme += f"- `{row['original_path']}`: {row['reason']}\n"
    readme += "\n## Exact evidence catalog\n\n| Preserved file | What it proves | SHA-256 | Absolute original path |\n|---|---|---|---|\n"
    for row in entries:
        escape = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        readme += f"| `{escape(row['file'])}` | {escape(row['proves'])} | `{row['sha256']}` | `{escape(row['original_path'])}` |\n"
    with (DEST / "README.md").open("xb") as stream:
        stream.write(readme.encode("utf-8"))
    print(json.dumps({"files": len(entries), "bytes": sum(row["bytes"] for row in entries),
                      "manifest_sha256": sha(manifest_path), "readme_sha256": sha(DEST / "README.md"),
                      "unavailable_adjacent": unavailable}))


if __name__ == "__main__":
    main()
