# ARM64 Git for Windows — Recovery & Handoff (Track A)

This directory is the recoverable handoff for **Track A**: proving the native
Windows-on-Arm (WoA) GCC toolchain builds a genuinely native ARM64 Git for
Windows, assembled into a correctly-sized, runtime-free MinGit.

**Status: Track A COMPLETE and ACCEPTED (both sides, independently verified).**

The machine holding the working tree is being reformatted. Everything in this
directory is source, scripts, documents and text-form evidence and is safe to
preserve in git. **Binaries are deliberately NOT committed** — they are
reproducible from the pipeline below and are identified here by hash so a
rebuild can be verified against exactly what shipped.

---

## 1. The accepted artefact — identity (verify a rebuild against these)

An artefact identifier is the **whole tuple**. Do not mix fields across builds.

| Field   | Value |
|---------|-------|
| name    | `MinGit-2.47.1-arm64.zip` |
| size    | **26,621,454 bytes** |
| sha256  | **`99485ab9ef0bf2a3b4ff4ab6928b923e26f2c0b63afc2fe87ef47362ebf559fd`** |
| entries | 93 |
| bin/*.exe | 16 (11 distinct) |
| PE files | 18, all `0xAA64` (ARM64), zero exceptions |

Component pins (embedded in the artefact):

| Component | sha256 | notes |
|-----------|--------|-------|
| `git.exe` | `69b1e704729cf69f0a0c029aa189eb9d38f74fc16ef37823048cb6a98b1523d1` | also `git-receive-pack.exe`, `git-upload-pack.exe` (byte-identical) |
| `ash.exe` / `busybox.exe` | `67665b44db934b574c95a600955482d35f1bb421a9498998df3e5baa96313aa8` | 756,224 bytes; ash.exe is a byte-copy of busybox.exe (argv[0] dispatch) |

**Superseded hashes — DO NOT re-pin to these:**
- `7d2c2ebf…` — pre-hardening build.
- `e78bb2dd…`, size **26,622,481** — pre-pipeline-stubs-trim build. The
  1,027-byte delta to the accepted build is exactly the four removed
  `share/pipeline-stubs/*.stub` marker files.

The sidecar `docs/MinGit-2.47.1-arm64.zip.sha256` carries the accepted hash.
Quote figures from a measurement of the current file, never from memory.

---

## 2. What CANNOT be preserved here, and how to regenerate it

| Lost on reformat | How to regenerate |
|------------------|-------------------|
| `MinGit-2.47.1-arm64.zip` (26.6 MB binary) | Run `scripts/assemble-mingit.sh` against the rebuilt package set (§3). Verify output against the §1 tuple. |
| `git.exe` and its dashed helpers (ARM64 PE) | Rebuild the git package with the WoA GCC toolchain (peer track — see git package recipe in `evidence/B4-GIT-PACKAGE-RECIPE.txt`, `evidence/B15-GIT-PACKAGE-WRAPPED.txt`). Pin to `69b1e704…`. |
| `busybox.exe` / `ash.exe` (ARM64 PE) | Rebuild busybox-w32 commit `d8d8bb397` UNMODIFIED with WoA GCC 15.0.1 (aarch64-w64-mingw32). Pin to `67665b44…`. See `scripts/make-busybox-ours.sh`. |
| Staged pacman packages (`*.pkg.tar.zst`) | Rebuilt as ephemeral inputs by `assemble-mingit.sh` STEP 0 (`make-busybox-ours.sh`, `build-gcm-stub.sh`, `build-leaves.sh`, `make-base-stubs.sh`). |
| WSL `aarch64-pc-cygwin` cross-toolchain at `/root/xc/inst` | Rebuild via the repo's `build-cross.sh` / `build-native-with-cross.sh` (repo root). |
| `builtins.txt` provenance input | **Preserved** here (`scripts/builtins.txt`, 142 lines). It must be regenerated ON AN ARM64 HOST via `git.exe --list-cmds=builtins` — an x86-64/WSL host CANNOT exec the ARM64 PE. See §4. |

---

## 3. Regeneration recipe (shortest path to a verified rebuild)

1. **Toolchain:** stand up the WoA native GCC (aarch64) toolchain. Cross-build
   recipe in repo root `build-cross.sh`; native-from-cross in
   `build-native-with-cross.sh`. Verified-standup notes in
   `evidence/WoA-native-GCC-standup-VERIFIED.txt`.
2. **git package:** build git 2.47.1 for `clangarm64` with that toolchain,
   wrap as `mingw-w64-clang-aarch64-git`. Recipe:
   `evidence/B4-GIT-PACKAGE-RECIPE.txt`; wrapper `scripts/wrap-git-package.sh`.
   **Critical:** the package MUST ship `share/git/builtins.txt` or the MinGit
   builtin-trim silently no-ops and 138 byte-identical `git.exe` copies survive
   (the 302 MB → 26 MB defect). Inject `scripts/builtins.txt` (see §4).
   Pin `git.exe` to `69b1e704…`.
3. **busybox package:** build busybox-w32 `d8d8bb397` with WoA GCC, wrap via
   `scripts/make-busybox-ours.sh`. Pin to `67665b44…`.
4. **Assemble:** run `scripts/assemble-mingit.sh`. It reproduces
   `build-extra/mingit/release.sh:126-181`, builds ephemeral leaf/stub packages
   (STEP 0), swaps in our git (STEP 1) with a PIN gate (STEP 2a), injects
   `builtins.txt` (STEP 3b), normalises pacman paths so trims fire (STEP 3),
   asserts the trim fired (STEP 4a), trims `pipeline-stubs` and asserts it
   fired, applies a two-sided bin-count bound, and (STEP 8) asserts the named
   HTTPS clone helpers are present and that no `pipeline-stubs/*.stub` survives.
5. **Verify:** compare output to the §1 tuple (size + sha256 + entries + all-18
   PE `0xAA64` + the two component pins). Use `scripts/final-measure.py` and
   `scripts/pe-machine.py`.

---

## 4. The 302 MB → 26 MB defect (must-know for any rebuild)

Our git package omitted `share/git/builtins.txt`. `make-file-list.sh`'s builtin
trim (`:77-86`, `:340-343`) guards on `test -f builtins.txt`; with the file
absent it silently no-ops, so all 138 dashed builtin `git-*.exe` — each a
byte-identical copy of `git.exe` — survive into the zip.

**Fix:** inject `builtins.txt` (142 `git-<name>.exe` lines). This reproduces
upstream's `SKIP_DASHED_BUILT_INS` outcome; `git.exe` dispatches builtins
internally. **The list must be generated on an ARM64 host** via
`git.exe --list-cmds=builtins` — WSL/x86-64 cannot exec the ARM64 PE.

This is one instance of the recurring failure class caught three times this
programme: **a trim that fires zero times looks identical to a trim with
nothing to trim.** The hardened assertions in `assemble-mingit.sh` (trim
fire-assertion, two-sided count bound, named HTTPS-helper assertion, and the
`pipeline-stubs/*.stub` exit-11 assertion) exist to make the previously
undetectable directions fail loudly.

---

## 5. Disclosed limitations (carried in RELEASE-NOTES.md)

- **`git submodule` fails under BusyBox ash.** `git-sh-setup:292` matches
  `*MINGW*`, takes the MSYS2-bash branch, and calls `builtin pwd -W` which ash
  lacks. Verified IDENTICAL against upstream's own ARM64 busybox
  (sha256 `4E510E35…`); inherent, same as git#5184 / git#6107. Does NOT affect
  `git clone`.
- **Cannot prompt for credentials by any route — one property, not two gaps.**
  `git-credential-manager.exe` and `git-credential-helper-selector.exe` are both
  153,353-byte NON-FUNCTIONAL stubs (GCM is .NET/Avalonia, out of scope for a
  C-toolchain demonstration), AND `git-askpass.exe` / `git-askyesno.exe` are not
  built. Together this means no credential prompt path exists. Disclosed in
  RELEASE-NOTES.md ("Non-functional stubs (disclosed)") and in-package
  `STUB-PLACEHOLDER.txt`.

---

## 6. The headline result (A/B proof)

Same `git.exe`, single variable = BusyBox shell on PATH:
- **Without** a shell: `git clone` exits `0xC0000005` (access violation).
- **With** our busybox as `sh.exe`: **exit 0**, `HEAD == source SHA`, status clean.
- Negative control (no sh/bash): `git submodule` exit 128.

Full transcript: `evidence/native-arm64-git-RUN-transcript.txt`,
`evidence/B8-PIPELINE-TEST-RESULT.txt`, and the A/B record in
`evidence/B16-MINGIT-ASSEMBLY.txt`.

---

## 7. Directory contents

- `scripts/` — assembly driver, package wrappers, measurement scripts,
  `builtins.txt`, the patched `make-file-list` shim (`mfl-patched.sh`).
- `evidence/` — the full verification record: A/B transcript, dedup
  measurement, name-level diff vs upstream's 24 bin exes, module-binding audit,
  git DEPENDS measurement, and all B-series addenda (B16 is the assembly log).
- `docs/` — `RELEASE-NOTES.md` (accepted, with stub disclosure and qualified
  claim) and the artefact sha256 sidecar.
- `maps/` — the last-mile and parallelisation maps.

All binding constraints observed: no upstream contact; `.copilot/repos` and peer
session dirs were read-only (copied out, never mutated).
