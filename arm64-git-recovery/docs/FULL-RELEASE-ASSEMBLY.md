# Full ARM64 Git for Windows assembly

`scripts/assemble-full-release.py` is the maintained successor to the historical
MinGit assembly scripts. It consumes immutable package handoffs directly and
does not install into, or copy from, an x64 bootstrap root.

The contract preserves all 15 Git 2.55 split packages and selects exactly one
curl TLS alternative (`openssl`, `gnutls`, or `winssl`). Package hashes,
identities, dependencies, conflicts, file ownership, case-insensitive path
collisions, native PE architecture, managed PE declarations, DLL imports,
documentation, licenses, launch paths, and relocatable CA configuration are
checked before a bundle can be marked complete.

Provider dependency closures are not copied wholesale. The contract defines
role-specific shipping globs: network providers contribute runtime DLL/data
surfaces, and the native Python provider contributes the interpreter, standard
library/extensions, Tcl/Tk and timezone runtime data, licenses, and dependency
DLLs. Compiler executables, generated dependency documentation, headers,
static libraries, and package provenance remain outside the shipping payload.

The package/file baseline is an explicit MINGWARM64 adaptation of the pinned
`git-for-windows/build-extra` `full-git-candidate` contract at recipe identity
`21d6ed86c38d28e89c950c9e1e349b6edefd1afb` (donor contract SHA-256
`8576a0499b93a7ddbc0f7c4ee3d9f44f5183b6c44f635561d8f31a622f350405`).
The adaptation and exact Git/network source identities are recorded in the
contract; requirements are not inferred from whichever manifests happen to be
present during an audit.

Native shipped-payload status and native build self-hosting status are separate
gates. An x64 MSYS driver may produce native ARM64 package bytes, but it cannot
satisfy the self-hosting evidence gate.

## Input

```json
{
  "schema": 1,
  "tls": "openssl",
  "git_handoff": {
    "path": "C:\\path\\git-package-handoff.json",
    "sha256": "<sha256>"
  },
  "network_export": {
    "path": "C:\\path\\network-export.json",
    "sha256": "<sha256>"
  },
  "provider_exports": [
    {
      "role": "native-msys-runtime",
      "path": "C:\\path\\runtime-export.json",
      "sha256": "<sha256>"
    },
    {
      "role": "native-python",
      "path": "C:\\path\\python-export.json",
      "sha256": "<sha256>"
    },
    {
      "role": "managed-gcm",
      "path": "C:\\path\\gcm-export.json",
      "sha256": "<sha256>"
    }
  ],
  "managed_admissions": [
    {
      "package": "mingw-w64-aarch64-git-credential-manager",
      "path": "C:\\path\\gcm-admission.json",
      "sha256": "<sha256>"
    }
  ],
  "self_hosting_evidence": {
    "path": "C:\\path\\native-self-hosting.json",
    "sha256": "<sha256>"
  }
}
```

Each additional provider export uses schema 1 and contains `packages`; every
package entry supplies `name`, `path`, and `sha256`. Relative package paths are
resolved beside the export. Package identity and dependencies are read back
from `.PKGINFO`; the export cannot override them.

The equivalent maintained producer field names `packageName` and `archive`
are also accepted. If both aliases are present, they must agree.

```json
{
  "schema": 1,
  "status": "admitted",
  "packages": [
    {
      "name": "mingw-w64-aarch64-python",
      "path": "packages/mingw-w64-aarch64-python.pkg.tar.zst",
      "sha256": "<sha256>"
    }
  ]
}
```

A corrected exact-split Git handoff may use a top-level `packages` array with
`packageName`, `archive`, and `sha256`. If it omits `source.recipeSha256`, it
must hash-bind an `immutablePriorHandoff` with the same source tag, commit,
makepkg archive, and exact split set. Only a declared `gitP4Integration`
replacement that binds the old/new git-p4 hashes and the native Python
dependency may differ; all other split archive hashes must remain unchanged.

Native self-hosting evidence is a separate schema-1 JSON document with
`status: "verified-native-self-hosting"`, `target: "aarch64-pc-msys"`, and a
nonempty `evidence` array of hash-bound native build/test receipts.

Listing GCM paths as managed files classifies them; it does not approve them.
The GCM package additionally requires version-1 admission evidence with
`status: "approved-for-native-arm64-distribution"`, `decision:
"user-approved"`, `host_architecture: "arm64"`,
`runtime_support_status: "verified"`, exact package/version/file hashes, and a
nonempty runtime evidence list. Without that explicit approval the release
remains incomplete.

`provider-not-supplied` means only that the package was absent from the input
manifests supplied to that audit. It is not a claim that the component has not
already been built elsewhere.

## Commands

Audit current inputs without writing a payload:

```powershell
python arm64-git-recovery\scripts\assemble-full-release.py audit `
  --input C:\private\full-release-input.json `
  --report C:\private\full-release-audit.json
```

Assemble only after the audit has no blockers:

```powershell
python arm64-git-recovery\scripts\assemble-full-release.py assemble `
  --input C:\private\full-release-input.json `
  --output C:\private\Git-2.55.0.windows.5-arm64-release
```

The output contains the installable zip, the exact selected package archives,
and `release-manifest.json`. The manifest contains only archive basenames and
hashes, not private producer paths.

Verify a completed bundle without trusting its directory contents:

```powershell
python arm64-git-recovery\scripts\assemble-full-release.py verify `
  --manifest C:\private\Git-2.55.0.windows.5-arm64-release\release-manifest.json
```

An incomplete audit is expected to exit 2. Hash, collision, architecture,
managed-code, or archive-contract violations exit 1 and never produce a bundle.

## OpenSSL admission verification

The admitted native OpenSSL package can be checked independently without
rebuilding it. The verifier rehashes the package, recipe, source signature,
full-test log, file manifest, extracted PE files, imports, provider output, and
digest evidence. It also runs a fresh detached-signature check with `gpgv`
against the owned copied keyring, without changing global trust. With
`--execute`, it performs fresh native ARM64 version, default/legacy provider,
and SHA-256 commands and writes a new immutable receipt. `--gpgv` may identify
an explicit verifier; otherwise the tool searches `PATH` and Git for Windows.
`--extract-root` materializes every hash-verified package member into a new
atomic private root and runs the native commands from that root, proving the
package does not depend on the historical admission extraction.

```powershell
python arm64-git-recovery\scripts\verify-openssl-admission.py `
  --admission C:\private\openssl-admission\admission.json `
  --extract-root C:\private\openssl-relocation\prefix `
  --execute `
  --output C:\private\openssl-admission-verification\execution.json `
  --report C:\private\openssl-admission-verification\verification.json
```
