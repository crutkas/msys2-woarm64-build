# Native ARM64 Git Bash engineering assembly

These tools assemble existing, receipt-bound native payloads. They do not
rebuild Git, OpenSSL, curl, the MSYS runtime, or an admitted package.
An assembly or static import audit is not an admission verdict.

## Required distinctions

* MSYS Bash and its libraries use the LP64 MSYS runtime. Windows/UCRT Git and
  its `libintl-8.dll` dependencies do not. Never substitute `msys-intl-8.dll`
  for the latter or force-load the MSYS runtime into a Windows library.
* All 21 measured `libintl-8.dll` consumers ship under `mingwarm64/` and have
  no MSYS-runtime import. An official CLANGARM64 C-runtime projection is only
  usable with its separate limited-MVP admission. It is not a replacement
  `mingw-w64-aarch64-gettext` package, and no `provides` is invented.
* Win32-OpenSSH ARM64 is a distinct, explicitly labelled portable client
  fallback, not Git for Windows' MSYS OpenSSH/Heimdal integration.
* The coordinator's initial "Perl is authorization-blocked" assessment was
  incomplete. Supported MSYS system-file symlinks pass POSIX semantics, but
  the current UCRT-hosted compiler reads their cookie bytes as C input.
  `core.symlinks=false` writes link text, not target contents, and is not a
  solution. The bounded dereferenced-source experiment belongs to the Perl
  producer. No machine-wide symlink privilege change is authorized here.

## Pipeline

1. `prepare_plan.py --spec INPUT.json --output PLAN.json` reads exact package
   handoffs and creates an explicit runtime-only file selection. Input paths
   stay in the local plan, not in executable configuration.
2. `artifact.py assemble --plan PLAN.json --output ROOT` verifies receipt and
   archive identities, rejects conflicting or non-ARM64 PEs, and records
   source/package provenance for each copied file. Symlinks require an
   explicit alias declaration. SDK/compiler/development payloads are omitted.
3. `audit_closure.py --root ROOT --output AUDIT.json` reads actual normal and
   delay PE imports and distinguishes bundled dependencies, real System32
   files, and Windows API-set contracts. This is not live module evidence.
4. `run_behavior.py --root ROOT --output NEW-RESULTS` runs native Bash/Git
   local repositories, hooks, recursive submodules, pipelines, fork/wait,
   signals, file operations, random-device reads, and real verified HTTPS.
   Only an empty private user configuration and the extraction's own system
   configuration are used. `%(prefix)` anchors the CA bundle to the extraction
   rather than to the caller's working directory.
5. `observe_behavior.py` repeats those cases in a separate instrumented copy
   using the published observer and its exact precompiled helper. Helper
   instrumentation is not a shipped payload. Every raw Windows exit remains
   unchanged; unknown child exits fail closed. A positive parent is not enough.
6. `attest_entrypoints.py` checks responsive Bash, Git, HTTPS-helper and Python
   processes with the epoch process attestor and read-only module snapshots.
   Snapshot coverage is labelled; this does not imply module completeness for
   every short-lived descendant.
7. `controlled_ssh.py` uses a pinned, privately installed native Python
   AsyncSSH test server. It performs real encrypted public-key authentication,
   an exact command/response, and a wrong-host-key rejection. Keys and ACL
   changes are confined to new disposable fixture files. No service or real
   user SSH configuration is changed. The Windows client needs `PROGRAMDATA`
   in its otherwise sanitized OS environment.
8. `moved_replay.py` creates byte-identical diagnostic ZIPs from two independent
   directories, extracts into different paths containing spaces, and starts
   fresh functional and live-attestation subprocesses. Local replay is not
   relabelled independent remote artifact custody.
9. `check_launcher.py --root ROOT --output NEW-RESULTS` exercises the actual
   CMD-to-login-Bash entrypoint with bounded commands and private configuration.
   Redirected console execution does not certify interactive PTY/job control.
10. `seal.py --spec SEAL.json --root ROOT --manifest MANIFEST.json --plan PLAN.json
    --output NEW-OUTPUT` requires successful, hash-bound evidence and explicit
    publication authority. The specification includes `assembly_manifest_sha256`,
    `assembly_plan_sha256`, `top_source`, `publication_authority`,
    `publication_authorized`, `evidence`, and `evidence_limitations`.
    It checks observer inventory, independent replay identity, SSH/runtime
    bytes and measured payload modules against the exact root. Original
    producer/admission receipt JSONs and their restrictions travel in
    `provenance.json`; a receipt hash alone is not substituted for its contents.

The first-artifact filename is
`arm64-vnext-2026-08-31-v1-git-bash-mvp-arm64.zip`. Do **not** use that name,
publish, or claim first-artifact acceptance until provider admission and all
required end-to-end evidence are present. Diagnostic archives deliberately
use `NON-ADMITTED` names.

## Evidence progression

The combined runtime `907afa09...` has separate reproducibility and native
runtime qualification. It is consumed, never rebuilt here.

| Layer | Measured outcome | Not implied |
|---|---|---|
| Initial diagnostic assembly | 12,376 files, 333 ARM64 PEs, resolved static DLL closure | Provider or behavior admission |
| First functional run | Ten native cases passed; missing selected `sed` blocked submodules | Full local Git closure |
| Second functional run | Recursive submodules passed; relative CA default blocked HTTPS | TLS verification may be disabled |
| Corrected diagnostic root | Twelve real local/runtime/HTTPS cases passed; input bytes unchanged | Full child-exit or module attestation |
| Observer integration | 230/230 generations observed; exact 1792/32256 contracts accepted; a separate negative-hook Bash 256 stayed rejected | A blanket exit-status decoder |
| Relocation | Two byte-identical diagnostic archives and two fresh moved functional runs | Publication authorization |
| Controlled SSH | Native portable client authenticated; wrong host key was rejected | MSYS OpenSSH, GSSAPI, or installed service support |

The independent subset-fixture bare-clone AV is retained as reported evidence.
The full extraction subsequently passed plain bare clone and bare
`--no-local`, including the same source repository. This separates full-payload
behavior from incomplete subset behavior; it does not retroactively change
the earlier failure or blame gettext without a causal comparison.

## Source and metadata

The local input specification binds package exports by path and SHA-256 and
contains `git`, `network`, `python`, `msys_exports`, `extra_components`, and
`top_source`. Every extra component has its original source/provenance, exact
file/archive identity, and explicit selection/mapping. Package metadata is
not rewritten to impersonate another namespace.

Missing source-specific provenance must remain a limitation, not a guessed
commit. At publication, the generated handoff must name one exact assembly
source commit/tree and preserve the producer identities for every component.
Artifact digests belong in detached receipts: embedding a ZIP's own digest
inside that ZIP would be self-referential.

Run the existing focused controls with native Python:

```powershell
python -B -m unittest discover -s .\arm64-git-recovery\native\mvp -p "test_*.py"
python -B -m unittest discover -s .\arm64-git-recovery\native -p "test_bounded_process.py"
```
