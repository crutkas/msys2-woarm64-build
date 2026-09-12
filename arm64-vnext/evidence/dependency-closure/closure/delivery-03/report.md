# Static closure and current admission: 21 MinGW consumers

**Result: no missing DLL files or private import symbols, but two present OpenSSL DLLs are superseded and unadmitted.**
This is a read-only measurement of `limited-candidate-02` (manifest `708394d8b303874307db541d278b9891d2b1fde1a9948e5266a3a992555e33f1`), reconciled with the intake owner's current v18 authority. No binary was changed, renamed, loaded, or executed.


## Revision 2: live HTTPS use of superseded TLS is confirmed

**The old OpenSSL pair is not confined to IMAP: independent live module samples prove that public HTTPS clones loaded it.** The original static scope was deliberately narrower. This revision preserves the original report and adds the exact peer observations; no payload was replaced or rerun here.

Independent evidence: `live-tls/independent-tls-evidence-01.json`, SHA-256 `94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc`, produced by `b1b1deaf-f47e-4ecf-a9d7-8ff7a75fe4d9`. Its referenced requests, environments, raw observations, outputs, custody records, shipped configuration and binary literal were re-read and hash-verified for this amendment.

| Independently preserved generation | Public HTTPS clone result | Live helper identity | CA result | TLS admission result |
|---|---|---|---|---|
| Candidate-01; manifest `a2052594e723bbc0f419cc546c19252b804af51d2440e64a29c847056bb316c3`; 12,376 copied files | **FAIL, raw 128** | PID 20464; creation FILETIME 134335839054013820 | Failed trust-anchor loading from `C:/mingwarm64/etc/ssl/certs/ca-bundle.crt`, despite bundles present inside the moved artifact | **Superseded/unadmitted pair actually loaded** |
| Named ZIP `7a4e99306da86abfc5591b96056ef06279bb8c4ca7353a7572a0e266abcdc854`; 12,392 extracted files | **PASS, raw 0, for this clone** | PID 19536; creation FILETIME 134335841375272335 | Already-shipped `sslCAInfo = %(prefix)/etc/ssl/certs/ca-bundle.crt` resolved the bundle; no verifier repair | **Same superseded/unadmitted pair actually loaded** |

Both helpers have SHA-256 `23f0ed83d9f815765f7bccd8a301e217d245c87ef1be36cf9239e30c077e8a6a`, also the helper hash in the static graph. Both live generations loaded:

| Module | Full SHA-256 |
|---|---|
| `libcurl-4.dll` | `d060e2d1127b52b49f7956d5eee59681ae160cd79bdac2156a45c05fbdd46669` |
| `libssl-3-arm64.dll` | `819faab1f9b057302009d35fda49853aea8ccaadc29d2189420237ae8528da48` |
| `libcrypto-3-arm64.dll` | `0d35dfe504cfc03e49c2d6c989ff3838216c658aa5c23559de2756e46fd6561a` |

The libcurl image contains the NUL-terminated ASCII literal `/mingwarm64/etc/ssl/certs/ca-bundle.crt` at **file offset 1,117,512**, in **`.rdata`**, in both copies. Each copy contains a real relative CA bundle at `mingwarm64/etc/ssl/certs/ca-bundle.crt` (and `mingwarm64/ssl/certs/ca-bundle.crt`), SHA-256 `8b347435463fdfb8400da4599d2e1af448ae8426ca7546c417aa289cb1c61bfa`. Candidate-01's shipped configuration did not override the default. The named ZIP's shipped prefix-relative configuration did.

**Two defects must remain separate:** candidate-01's immediate raw-128 failure was CA lookup relocation; superseded TLS provenance remained a defect in **both** generations. Do not attribute the CA failure to old OpenSSL, do not carry the candidate failure into the successful named ZIP result, and do not treat the named ZIP's functional success as crypto admission.

The clones used the genuine shipped helper and public URL `https://github.com/octocat/Hello-World.git`. No CA/environment/exec-path repair or TLS-verification disablement was made by the verifier. These are ordinary, generation-bound module samples, **not exhaustive load-event coverage**. Full reference hashes and copied raw records are in `live-tls-confirmation.json` and `live-tls/references/`.

The static closure counts and conditional **81 total / 22 gettext-related / 59 other** blocker-row breakdown below are unchanged. Zero unresolved static imports does not establish whole-program runtime correctness, full dynamic closure, relocation correctness, or current provider admission.


## Revision 3: standalone shipped curl still fails in the named ZIP

The independent verifier subsequently supplied a separate result for the **shipped `curl.exe`**, not Git's HTTPS helper: **raw exit 77**, with `error adding trust anchors from file: C:/mingwarm64/etc/ssl/certs/ca-bundle.crt`. The bundle is present inside the moved named ZIP. Git's shipped prefix-relative `sslCAInfo` fixes Git's CA selection but does **not** configure standalone curl.

| Artifact / operation | Raw result | Interpretation |
|---|---:|---|
| Candidate-01, Git public HTTPS clone | **128 - FAIL** | Compiled CA default lookup defeats this generation's relocation. |
| Named ZIP, Git public HTTPS clone | **0 - PASS for this operation** | Shipped prefix-relative Git CA configuration works; superseded TLS still loaded. |
| Same named ZIP, standalone shipped curl HTTPS HEAD | **77 - FAIL** | Standalone curl still consults the compiled CA default; no verifier override or repair. |

The standalone process was PID **2644**, creation FILETIME **134335842597890221**, image SHA-256 `6ddfbcd7c5fcd015112d7e002727b20abc70b7e2c7f643b029cd8d70e9e196be`. Its exact generation also sampled `libcurl-4.dll` `d060e2d1...`, old `libssl-3-arm64.dll` `819faab1...`, and old `libcrypto-3-arm64.dll` `0d35dfe5...` (full hashes in the preceding TLS module table).

Citation: independent mixed report SHA-256 `c44fb3f8238980bea3545938362e7e84ea5cb806780ea58b354261e3d3447c9b`, copied to `live-tls/independent-full-mixed-report.json`. Exact request, output and raw process/module observation are copied under `live-tls/standalone-curl/`; their hashes are respectively `b223ee40180e726fa4160dbd1ea862f600b3c778188b92da5738fabf58aa778c`, `6629743422516870f9cdacb999280888ece4af9a77467dfe217795b662c2ed4d`, and `ec6c6145d29855437f2f242daed0175277b92c2384d5c6931dbeedafe5132e1b`.

These are distinct outcomes, not a single “HTTPS passed/failed” headline. CA lookup behavior and crypto-provider admission remain separate defects. The independent module samples establish actual use, not exhaustive load-event coverage. The original static report, its counts and the conditional 81/22/59 arithmetic remain unchanged.

## Counts

| Measure | Count |
|---|---:|
| Exact consumer seeds | 21 |
| Package-owned PE nodes (19 executables + 10 DLLs) | 29 |
| Distinct private DLLs | 10 |
| Admitted selected-package DLLs | 5 |
| Admitted limited-role DLLs | 3 |
| Superseded/unadmitted present DLLs | 2 |
| Windows boundary leaves (6 System32 + 13 API sets) | 19 |
| Normal import edges / delay-import edges | 516 / 0 |
| Physically missing DLL names / missing private imported symbols | 0 / 0 |
| MSYS imports in this static graph | 0 |

## Per-DLL admission table

Receipt IDs below refer to full paths and SHA-256 values in the following table. `dll-admission-table.csv` includes every full file hash and receipt hash; no filename match alone is treated as admission.

| DLL | Runtime side | Current admission for inspected bytes | Provider / receipt | Consumer seeds reaching it |
|---|---|---|---|---:|
| `libcrypto-3-arm64.dll` | MinGW/Windows-UCRT | **SUPERSEDED—UNADMITTED** | mingw-w64-aarch64-openssl / R1 | 1 |
| `libexpat-1.dll` | MinGW/Windows-UCRT | Admitted selected package | mingw-w64-aarch64-expat / R2 | 1 |
| `libiconv-2.dll` | MinGW/Windows-UCRT | Admitted limited role only | mingw-w64-clang-aarch64-libiconv 1.19-1 (C projection) / R3 | 21 |
| `libidn2-0.dll` | MinGW/Windows-UCRT | Admitted selected package | mingw-w64-aarch64-libidn2 / R4 | 1 |
| `libintl-8.dll` | MinGW/Windows-UCRT | Admitted limited role only | mingw-w64-clang-aarch64-gettext-runtime 1.0-1 (C projection) / R3 | 21 |
| `libpcre2-8.dll` | MinGW/Windows-UCRT | Admitted limited role only | mingw-w64-aarch64-pcre2 / R5 | 19 |
| `libssl-3-arm64.dll` | MinGW/Windows-UCRT | **SUPERSEDED—UNADMITTED** | mingw-w64-aarch64-openssl / R1 | 1 |
| `libtre-5.dll` | MinGW/Windows-UCRT | Admitted selected package | mingw-w64-aarch64-libtre / R2 | 1 |
| `libunistring-5.dll` | MinGW/Windows-UCRT | Admitted selected package | mingw-w64-aarch64-libunistring / R4 | 1 |
| `libz.dll` | MinGW/Windows-UCRT | Admitted selected package | mingw-w64-aarch64-zlib / R4 | 19 |
| `advapi32.dll` | Windows system boundary | Windows satisfied | Windows System32 DLL | — |
| `api-ms-win-crt-convert-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-environment-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-filesystem-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-heap-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-locale-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-math-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-private-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-process-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-runtime-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-stdio-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-string-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-time-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `api-ms-win-crt-utility-l1-1-0.dll` | Windows system boundary | Windows satisfied | Windows API-set contract → System32 ucrtbase.dll | — |
| `crypt32.dll` | Windows system boundary | Windows satisfied | Windows System32 DLL | — |
| `kernel32.dll` | Windows system boundary | Windows satisfied | Windows System32 DLL | — |
| `ntdll.dll` | Windows system boundary | Windows satisfied | Windows System32 DLL | — |
| `user32.dll` | Windows system boundary | Windows satisfied | Windows System32 DLL | — |
| `ws2_32.dll` | Windows system boundary | Windows satisfied | Windows System32 DLL | — |

| Receipt | Full SHA-256 | Path |
|---|---|---|
| R1 | `4c3a57be0859f70a355a6d133604cf278cd06fc8406f734344bf15331ebf1a62` | `C:\ap11-native-provider-intake\openssl-mingwarm64-admitted-v1\export.json` |
| R2 | `50135bf37587bf428930ccd6f3cc93bb0a0891fbd80bb74d18446911a5896c2f` | `C:\ap11-native-provider-intake\revoked-free-closures-v2\python-export.json` |
| R3 | `ac7849fd9934f5773ab1aa9a49aba30e78c371645af13944cf06d65c6c6661f1` | `C:\ap11-native-provider-intake\official-clangarm64-libintl-limited-mvp-v1\export.json` |
| R4 | `aa92b9ef76a7c0d2ffcd72b2f816ea30f0d0cbfc55e9d949eef073324e8817ae` | `C:\ap11-native-provider-intake\revoked-free-closures-v2\network-export.json` |
| R5 | `77837f952344405b330ee730169b83f45ce300a8a74a5cc32b498752f55dbee8` | `C:\ap11-native-provider-intake\pcre2-current-byte-limited-mvp-v1\export.json` |

**The two OpenSSL rows deliberately remain red.** The inspected DLLs are `libssl-3-arm64.dll` SHA `819faab1f9b057302009d35fda49853aea8ccaadc29d2189420237ae8528da48` and `libcrypto-3-arm64.dll` SHA `0d35dfe504cfc03e49c2d6c989ff3838216c658aa5c23559de2756e46fd6561a`, from superseded archive `256c79d70ee8a4dc65e6cc532242841373cedddabf67442e19205a026d1d80d3`.

The current admitted OpenSSL archive is `02f2e786dcf78a3b47d62a18cb0d1d9078cfcb69486a891bc4b901ad21b8e5ab`, bound by receipt `4c3a57be0859f70a355a6d133604cf278cd06fc8406f734344bf15331ebf1a62`. Its independently read archive members have different hashes: SSL `c1220fb0a6faea975376bbdde558ec19f9ada0a5f5ab0a9b86db14ed0f896b61`, crypto `dd210957efceb1999e38f2b5f5165c370fb6da6a1d7eff1185dd6edf1bc33818`. They were **not substituted** into the candidate.

**Static-edge statement only, now supplemented by live HTTPS confirmation above:** both inspected TLS DLLs are reachable from `git-imap-send.exe` only within these 21 seeds' static import graph. They were nevertheless actually loaded by `git-remote-https` in both peer captures. Static reachability does **not** limit total TLS exposure: process-launched HTTPS helpers, embedded/static code, dynamically loaded libraries and plugins are outside this graph. `libcurl-4.dll` has no import edge in this measured closure; that is not proof that the program contains or uses no curl/TLS code.

## The 81 full-release blocker rows

| Category | Total v18 rows | Gettext-related | Other rows |
|---|---:|---:|---:|
| Missing DLL import edges | 21 | 21 | 0 |
| Missing package/provider identities | 36 | 1 | 35 |
| Missing required payload files | 18 | 0 | 18 |
| Private operational paths | 4 | 0 | 4 |
| Managed-component admission | 1 | 0 | 1 |
| Native self-hosting evidence | 1 | 0 | 1 |
| **Total** | **81** | **22** | **59** |

The 21 import-edge rows all name **one** DLL, `libintl-8.dll`; the additional row is the strict `mingw-w64-aarch64-gettext` package identity. Independent computation using the v18 **selected package bytes** (not the limited candidate) likewise finds exactly this one missing DLL identity across 21 consumers. Limited libintl/PCRE2 file-role admissions do not satisfy the strict GNU gettext identity/transaction gate. Therefore 81 remains the authoritative audit count; 59 is only the arithmetic remainder **if all 22 strict gettext gates were genuinely resolved**, not a new verdict.

### Why 59 is not 59 independent implementations

| Other blocker family | Rows |
|---|---:|
| Credential-manager/selector integration | 4 |
| Native self-hosting evidence | 1 |
| MSYS shell profile | 1 |
| Coreutils provider and seven required executables | 8 |
| Findutils provider and find executable | 2 |
| MSYS less provider and executable | 2 |
| Perl and eight Perl modules | 10 |
| Sed provider and executable | 2 |
| MSYS OpenSSH provider and four executables | 5 |
| MinGW libcurl operational-path gate | 1 |
| MinGW Tcl operational-path gates | 3 |
| Other 20 distinct package identities | 20 |

The other 20 package identities are: `antiword`, `connect`, `dash`, `docx2txt`, `dos2unix`, `gnupg`, `mintty`, `nano`, `odt2txt`, `patch`, `ssh-pageant`, `subversion`, `tar`, `tig`, `unzip`, `vim`, `which`, `winpty`, `xpdf-tools`, `xz`.

Coreutils, OpenSSH, Perl, less, findutils and sed each have package and/or required-file rows describing overlapping obligations. The three Tcl path rows concern one DLL; the fourth path row concerns libcurl. Package/evidence gates may require more than one implementation or qualification step, so neither the grouped count nor CPU availability establishes an effort estimate.

## Boundaries and caveats

- The fixed point expands **all package-owned normal and delay imports**. Windows DLLs and API-set contracts are legitimate terminal boundaries; this is not a recursive security/implementation audit of Windows itself. The actual host API-set schema and every System32 boundary file/host were read and hash-bound.
- All 29 application-side PEs in the graph are genuine AA64. No MSYS runtime is imported. The separate native MSYS PCRE2 needed by less is **not** this MinGW PCRE2 provider.
- Native `sh.exe` is a known **dynamic command dependency**: the earlier clone failure disappeared when the real native `usr\bin` was supplied. The original A/B/A failures and append-only clarification are preserved. This graph does not count the MSYS shell or its runtime as MinGW-import leaves.
- Credential helpers, pagers, hooks, SSH, remote helpers, certificate data and configured plugins require separate command/configuration and behavior coverage. Static symbol availability is not runtime or end-to-end acceptance.
- “Admitted selected package” means an exact archive/member match in v18, not that all that package's dependencies or all full-release requirements have passed. The limited official gettext and PCRE2 limitations remain in force.
- The blocker ledger v5's separate-producer MSYS-PCRE2 scheduling wording was subsequently superseded by the one-serial-job PCRE2→less assignment to d207; no dependency or audit count was altered here.

## Machine-readable evidence

- `static-graph.json`: fixed-point nodes, all edges/symbols, seed reachability, Windows API-set resolution and hashes.
- `admission-table.json` / `dll-admission-table.csv`: every DLL's full hash, receipt, provider, status, strict-selection difference and member proof.
- `blocker-breakdown.json` / `remaining-59-blockers.csv`: the complete unchanged blocker rows and family mapping.
- `authority-inputs.json`: exact snapshotted current intake authorities.
