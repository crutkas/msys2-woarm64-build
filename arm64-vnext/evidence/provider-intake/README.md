# Provider intake contract authority

This directory preserves the ordered provider-intake contracts and decisions
that downstream qualification sessions consumed. These are exact record bytes,
not reconstructed summaries. Package archives and payload binaries are
intentionally excluded.

## Authority order

1. The `bash-qualified-d70-*` records admit the unchanged Bash package only for
   its d70 runtime cohort and supersede the earlier rejected Bash packaging
   attempt.
2. On 2026-09-11 at 07:10:39Z,
   `bash-runtime907-qualification-input-v1.json` established the exact
   runtime-907 read-only qualification contract. Its SHA-256 is
   `4dc1ff625c82d762d25f157538146288758b7ffa2a150e09c6c4e8b28e137162`.
3. On 2026-09-11 at 07:12:28Z, the first consumer correctly invalidated its
   captures because the historical fixture selected libintl
   `eef1befd674c9febcfe769601d8e10a1022b00dabffa383b866847b935eb054d`
   instead of the contract-required
   `44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c`.
   The selected iconv
   `86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215`
   and runtime
   `907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c`
   were correct. The invalid selection, input inventory, and all six referenced
   captures are preserved rather than deleted or promoted.
4. On 2026-09-11 at 07:22:52Z, the first qualification disposition kept
   runtime-907 Bash compatibility not admitted after the controlling
   interactive signal regression.
5. On 2026-09-11 at 08:21:02Z, the final v2 decision added the complete raw
   86-case suite evidence but retained that non-admission. It supersedes the
   earlier disposition only by adding evidence; the failure and d70-only
   boundary remain authoritative.

For a replay, apply the contract's assembly order exactly: immutable historical
test fixture first, exact Bash payload, exact selected iconv and intl members,
and runtime-907 last. Verify every final member hash before execution. Test-only
utilities are never package providers and may not be shipped.

## Limited-role qualifications

The libintl export
`ac7849fd9934f5773ab1aa9a49aba30e78c371645af13944cf06d65c6c6661f1`
admits unchanged `libiconv-2.dll` and `libintl-8.dll` plus their six licenses
only for the official CLANGARM64 C-runtime role. It is not a truthful
`mingw-w64-aarch64-gettext` package admission, cannot add an alias or fake
`provides`, and cannot clear the strict GNU gettext identity or transaction
gate.

The PCRE2 export
`77837f952344405b330ee730169b83f45ce300a8a74a5cc32b498752f55dbee8`
admits only the current-byte `libpcre2-8.dll` role while retaining the same
strict selected archive
`63ca004e570269889a30d4046a77946f09ddc6179a8be9b567e90cc9f4e3d7ec`.
It does not create a new package, claim a fresh reproducible build, or authorize
the incompatible `libpcre2-8-0.dll` name.

These limited projections do not reduce the strict audit from 81 blockers to
59. The strict package identity and transaction requirements remain open until
genuine qualified packages satisfy them.

## Exact preserved files

| Repository file | Original absolute path | SHA-256 |
|---|---|---|
| `contract-series/bash-qualified-d70-export.json` | `C:\ap11-native-provider-intake\bash-qualified-d70-v1\export.json` | `f485f6e2b0ee76fe44fc1b416354367c1325d46a9d30efa39a884d7f472c747c` |
| `contract-series/bash-qualified-d70-handoff.json` | `C:\ap11-native-provider-intake\bash-qualified-d70-v1\handoff.json` | `a78223dc8f0bd93c8ec567e08b877a15cf4545946214df55fe78a1ea1c27e0f2` |
| `contract-series/bash-qualified-d70-rejection-superseding-disposition.json` | `C:\ap11-native-provider-intake\bash-qualified-d70-v1\rejection-superseding-disposition.json` | `e7d413ec32e97fe389706482eaa75cbd415c0d987ff86a31ad72b15061255389` |
| `contract-series/bash-runtime907-qualification-input-v1.json` | `C:\ap11-native-provider-intake\bash-runtime907-qualification-input-v1.json` | `4dc1ff625c82d762d25f157538146288758b7ffa2a150e09c6c4e8b28e137162` |
| `decisions/bash-runtime907-qualification-failure-v1.json` | `C:\ap11-native-provider-intake\bash-runtime907-qualification-failure-v1.json` | `ad40b7e220d3be4373ef0811523cd443a71da60058c9b9c1c90ab11794294ac5` |
| `decisions/bash-runtime907-final-qualification-v2-verdict.json` | `C:\ap11-native-provider-intake\bash-runtime907-final-qualification-v2\verdict.json` | `3b5f68e0c37fbcaa7f502b9ffe5fae7c5649545bccead9553430af2ac305a450` |
| `invalid-selection/inputs.json` | `C:\ag-bash907-20260911-01\inputs.json` | `7401311e846a014d8dbc7c0ee834814a7c5a6b13ac600ac6b28f09e65f9adf66` |
| `invalid-selection/invalid-selection.json` | `C:\ag-bash907-20260911-01\invalid-selection.json` | `3116c150a98b2f2098c984295489e1d66ab8beb4874e8ea5a690dbd77762e588` |
| `invalid-selection/captures/interactive-01-result.json` | `C:\ag-bash907-20260911-01\interactive-01\result.json` | `8452d2fcf14895769127daabfb7242ca6693bf85b270e934b0bdf63d4614ee0a` |
| `invalid-selection/captures/jobs-builtin-pipeline-907-01-result.json` | `C:\ag-bash907-20260911-01\jobs-builtin-pipeline-907-01\result.json` | `cea6c3fd19bf56362dabb084dc35c7db117a334eaca9aff4f54bbb8cc55228af` |
| `invalid-selection/captures/jobs-direct-group-907-01-result.json` | `C:\ag-bash907-20260911-01\jobs-direct-group-907-01\result.json` | `eeec35964a010648a953e6d77fb3f3eb0526f8bf607fd1d13bc5a368c36eaad0` |
| `invalid-selection/captures/jobs-pgid-907-01-result.json` | `C:\ag-bash907-20260911-01\jobs-pgid-907-01\result.json` | `6b2144359a8cfb49aa7fe0cae726d3ec21ad5ab62386592c92fb0f666bb83a06` |
| `invalid-selection/captures/jobs-reversed-907-01-result.json` | `C:\ag-bash907-20260911-01\jobs-reversed-907-01\result.json` | `27525b021771e989aabb14a1b234dd1bc992d44d53f215d0c8ec544b99f00a2e` |
| `invalid-selection/captures/jobs-single-907-01-result.json` | `C:\ag-bash907-20260911-01\jobs-single-907-01\result.json` | `2ea44cffab3e7a0ecc5615a6d8f2e0fb56644f8973ba953a2a73c9d03e3155b4` |
| `limited-roles/libintl/export.json` | `C:\ap11-native-provider-intake\official-clangarm64-libintl-limited-mvp-v1\export.json` | `ac7849fd9934f5773ab1aa9a49aba30e78c371645af13944cf06d65c6c6661f1` |
| `limited-roles/libintl/qualification.json` | `C:\ap11-native-provider-intake\official-clangarm64-libintl-limited-mvp-v1\evidence\qualification.json` | `a8234d5f98d75b8a33ae004afe71c817c65cf839aed8e896b2b9e81f669b2d5e` |
| `limited-roles/libintl/independent-verification.json` | `C:\ap11-native-provider-intake\official-clangarm64-libintl-limited-mvp-v1\evidence\independent-verification.json` | `c509766c1488a198b4f387bbc9b18d133c3df531daa8c0ecf19d826e5e965092` |
| `limited-roles/pcre2/export.json` | `C:\ap11-native-provider-intake\pcre2-current-byte-limited-mvp-v1\export.json` | `77837f952344405b330ee730169b83f45ce300a8a74a5cc32b498752f55dbee8` |
| `limited-roles/pcre2/qualification.json` | `C:\ap11-native-provider-intake\pcre2-current-byte-limited-mvp-v1\evidence\qualification.json` | `e43b0f5d7261618dabea1f55d3c16da9a56af986fc0b0fcaf16c4773155f6526` |
| `limited-roles/pcre2/independent-verification.json` | `C:\ap11-native-provider-intake\pcre2-current-byte-limited-mvp-v1\evidence\independent-verification.json` | `86438b3de91f98c861a73f12844752efb680608dfc2f15f7a5158d22bda10581` |

`manifest.json` repeats these identities in machine-readable form. The local
`.gitattributes` prevents Git from rewriting copied record bytes.
