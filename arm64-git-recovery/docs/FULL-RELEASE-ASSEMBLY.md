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

## Native MSYS provider intake

Qualified native MSYS stages are packaged in a new private output root rather
than installed into a bootstrap or producer prefix:

```powershell
pwsh arm64-git-recovery\scripts\package-qualified-iconv.ps1 `
  -OutputDirectory C:\private\iconv-full-v1

pwsh arm64-git-recovery\scripts\package-qualified-gettext-runtime.ps1 `
  -OutputDirectory C:\private\gettext-runtime-v1

pwsh arm64-git-recovery\scripts\package-qualified-ncurses.ps1 `
  -OutputDirectory C:\private\ncurses-v1

pwsh arm64-git-recovery\scripts\package-qualified-terminal-libraries.ps1 `
  -OutputDirectory C:\private\terminal-libraries-v1

pwsh arm64-git-recovery\scripts\export-qualified-native-msys-archives.ps1 `
  -OutputDirectory C:\private\qualified-archives-v1
```

The scripts hash-pin their producer handoffs and every staged payload file.
They use `makepkg` only to apply the original split-package ownership and
metadata rules; native binaries are not rebuilt or stripped. The ncurses
packager resolves its explicit package-time `usr/lib/terminfo` link gate as a
relative symlink to `../share/terminfo` and excludes the materialized staging
directory from the development split.

Each output contains `export.json` for `provider_exports` and a separate
`handoff.json` that records producer hashes, unchanged-byte controls, and
runtime-cohort limitations. An admitted provider can still leave the release
incomplete when its dependencies or matching runtime cohort are not supplied.
