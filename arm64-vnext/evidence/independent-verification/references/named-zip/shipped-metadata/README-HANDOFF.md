# Native ARM64 Git Bash engineering MVP

**Limited engineering handoff, not RTM or full Git for Windows release admission.**

Assembly source: `https://github.com/crutkas/msys2-woarm64-build` commit `901256ba4e9fe48b6babaa51849733d8189b5e14`, tree `1f0bd4fa2fc04e1b484ff5eaa2e22a5829cf321f`.

Extract to a writable directory on Windows 11 ARM64. Launch `Git-Bash-Native.cmd`.
The upstream `git-bash.exe` mintty entry is not the supported entrypoint in this artifact.
All supported application payload PEs are ordinary ARM64. Windows system components and
one-time validation tooling are recorded separately; no x64 bootstrap is shipped.

Verify the detached ZIP SHA-256 before extraction, then the file hashes in `manifest.json`.
A ZIP cannot embed its own final digest; its exact artifact hash is in the adjacent receipt.

Supported evidence covers native Bash, local Git/hooks/recursive clones, verified HTTPS,
controlled SSH public-key/host-key checks, fork/pipeline/subshell, filesystem and signals.
Admission scopes and independent moved-root replay are in `provenance.json` and `evidence/`.
Use `git commit -m` and non-paged commands: an interactive editor, terminal emulator,
Git GUI/gitk launch workflow, and interactive credential services are not qualified.

The configured `winsymlinks:sys` links have MSYS POSIX semantics. Windows/UCRT
applications do not necessarily dereference them: do not treat them as native
Windows symlinks or claim Git symlink checkout/compiler-source-link compatibility.

## Explicit limitations

- Limited native engineering artifact, not RTM or a strict full-release package transaction.
- No native Perl provider: Perl-dependent commands, git-svn, git-send-email and related integrations are unsupported.
- GCM, mintty, full editors, service integration and installer/signing are not supplied.
- Use Git-Bash-Native.cmd for the supported console entry; upstream git-bash.exe expects the absent mintty.
- POSIX chmod/stty/false utility providers are withheld; Bash builtins remain available.
- Utility supported locale is LC_ALL=C with explicit MSYS system-file symlinks and noacl mounts.
- Source-specific commit/tree and reproducibility evidence is incomplete for some retained package providers; no identity is fabricated.
- libintl-8.dll contains compiled default /clangarm64/share/locale; unbound/default-domain localization is not admitted.
- Official gettext CLI default French lookup failed before and after moving; no CLI/tools/docs/catalogs are shipped.
- libidn2 and libtre translated diagnostics are not admitted; only their functional semantics are admitted.
- The qualification subset fixture bare-clone access violation is not attributable to this projection (official/revoked/restored-official all failed there). Full-artifact clone behavior is outside this verdict and must be tracked by the artifact owner.
- This limited verdict does not clear the strict full-release package identity or canonical /mingwarm64 provider gate.
- No PCRE2-specific signed source archive, exact CMake command, or independently reproducible build receipt is available; do not claim a fresh/reproducible PCRE2 build.
- The original package metadata comes from the umbrella network-provider export; this intake does not rewrite it or create a replacement package.
- Full upstream PCRE2 suite was not rerun.
- Retained pcre2test has no readline/editline support; CLI tools are not projected.
- The newer 10.48-3 package exports libpcre2-8-0.dll and remains incompatible with current Git imports; no alias is permitted.
- All 37 executables retain absolute producer source/build/include paths. For the 34 Coreutils commands these are classified as source/debug provenance and moved-root controls pass; they still prevent any reproducible-build claim.
- find, xargs and sed embed the private bootstrap locale directory and are admitted only with LC_ALL=C; translated diagnostics/NLS relocation are not admitted.
- Historical Coreutils suite is incomplete: 48 PASS, 41 FAIL, 23 SKIP, 4 ERROR.
- No original native13 PKGBUILD or complete compiler-input manifest exists.
- chmod mode semantics, stty PTY/conhost closure and false negative exit are withheld rather than normalized.
- No full provider, full suite, arbitrary locale, package provides, or strict package-manager transaction is claimed.
- Portable Win32-OpenSSH client, not the native MSYS OpenSSH provider Git for Windows normally ships.
- GSSAPI/Heimdal integration, installed services, FIDO/PKCS11 hardware and real credential-store operations are not qualified.
- Only software public-key handshake, exact command response and wrong-host-key rejection are positively exercised; SCP/SFTP and agent service workflows are not claimed.
- Native MSYS OpenSSH candidate 00882b9e is explicitly rejected and excluded due private path/untested OpenSSL provenance; this role does not waive that rejection.
- Limited engineering MVP, not a full Git for Windows release, complete native SDK, or C++ qualification.
- 3,022 original payload files lack full Git commit/tree identities. Original package/archive/source receipts remain explicit; unavailable source commits are not inferred. Recovered recipe commit/tree identities are not upstream-source or source-to-binary attestations.
- Live module snapshots cover four responsive entrypoint checkpoints, not every short-lived descendant. Complete process-generation accounting is a distinct 238/238 observer result.
- The independent replay embedded here consumed exact frozen payload bytes in a moved root. Final ZIP custody, extraction and recreation require an additional detached independent final-ZIP result.
- The supported portable SSH route is Microsoft ARM64 Win32-OpenSSH, not native MSYS OpenSSH/Heimdal. The rejected native-MSYS SSH candidate contributes no bytes.
- Interactive editor, pager/terminal-emulator, Git GUI/gitk, credential-store, SSH-agent/service, GSSAPI and complete Perl-dependent workflows are not qualified.
- MSYS system-file symlinks have supported POSIX semantics but are not native Windows symlinks. UCRT application/compiler source-link dereference is not qualified.
- The exact negative-hook contract uses the published observer's existing fixture API, unchanged observer/helper binaries, controller-bound source/argv, observed generation causality and 22 refusal controls. It is not kernel argv capture or a general raw-exit decoder.

Issue/contact route: the linked assembly source pull request in the crutkas fork.
