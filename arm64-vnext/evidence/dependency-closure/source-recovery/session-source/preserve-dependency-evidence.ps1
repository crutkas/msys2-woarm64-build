param([Parameter(Mandatory)][string]$Workspace)
$ErrorActionPreference = 'Stop'
$destination = Join-Path $Workspace 'arm64-vnext\evidence\dependency-closure'
$rows = [Collections.Generic.List[object]]::new()
$duplicateName = '013-9bf376600cd047912cdddb5c88f6b89301727c2b9e7bbb55ecc6e4416aba2602-intake.json'
$groups = @(
    @{Root='C:\ap16-accd-mingw-closure-01\delivery-01';Target='closure\delivery-01';Purpose='Original v18 static closure, full admission table and conditional blocker decomposition';Recursive=$true},
    @{Root='C:\ap16-accd-mingw-closure-01\delivery-02';Target='closure\delivery-02';Purpose='Append-only dual-generation live HTTPS and superseded TLS evidence';Recursive=$true},
    @{Root='C:\ap16-accd-mingw-closure-01\delivery-03';Target='closure\delivery-03';Purpose='Final static/live TLS revision including separate standalone curl CA failure';Recursive=$true},
    @{Root='C:\ap11-accd-gettext01\delivery-02';Target='libintl\qualification';Purpose='Official libintl/iconv limited-role consumer, relocation and symbol qualification';Recursive=$true},
    @{Root='C:\ap11-accd-pcre2-mvp01\delivery-01';Target='pcre2\retained-qualification';Purpose='Retained 10.48-1 exact-byte API/JIT/Unicode and Git-grep qualification';Recursive=$true},
    @{Root='C:\ap11-native-provider-intake\official-clangarm64-libintl-limited-mvp-v1';Target='libintl\admission';Purpose='Intake limited libintl/iconv admission, not strict GNU gettext identity';Recursive=$true},
    @{Root='C:\ap11-native-provider-intake\pcre2-current-byte-limited-mvp-v1';Target='pcre2\retained-admission';Purpose='Intake retained PCRE2 limited-role admission for existing consumers';Recursive=$true},
    @{Root='C:\ap07-pcre2-accd01\delivery-01';Target='pcre2\full-producer';Purpose='Genuine full PCRE2 10.48-3 producer provenance, separate versioned DLL ABI';Recursive=$false},
    @{Root='C:\ap17-accd-less01\delivery-01';Target='later-native-tools\less\producer';Purpose='Later native907 less704 producer handoff and evidence index, not v18 revision';Recursive=$false},
    @{Root='C:\ap18-accd-tools01\which\delivery-01';Target='later-native-tools\which\producer';Purpose='Later native907 which2.25 producer handoff and evidence index';Recursive=$false},
    @{Root='C:\ap18-accd-tools01\dos2unix\delivery-01';Target='later-native-tools\dos2unix\producer';Purpose='Later native907 dos2unix7.5.7 producer handoff and evidence index';Recursive=$false},
    @{Root='C:\ap11-native-provider-intake\native-msys-less704-admitted-v1';Target='later-native-tools\less\admission';Purpose='Independent native907 less704 admission/readback summary';Recursive=$false},
    @{Root='C:\ap11-native-provider-intake\native-msys-which-runtime907-admitted-v1';Target='later-native-tools\which\admission';Purpose='Independent native907 which admission; genuine sh dependency remains separate';Recursive=$false},
    @{Root='C:\ap11-native-provider-intake\native-msys-dos2unix-runtime907-admitted-v1';Target='later-native-tools\dos2unix\admission';Purpose='Independent native907 dos2unix admission, including alias/MTREE metadata';Recursive=$false}
)
function Preserve([string]$Source, [string]$Relative, [string]$Purpose, [string]$Expected = '') {
    $file = Get-Item -LiteralPath $Source
    if ($file.Length -ge 50MB) { throw "Large irreplaceable evidence requires another decision: $Source ($($file.Length) bytes)" }
    $hash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Expected -and -not $hash.StartsWith($Expected)) { throw "Known seal changed: $Source" }
    $target = Join-Path $destination $Relative
    if (Test-Path -LiteralPath $target) { throw "Preserved destination already exists: $target" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $target
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $hash) {
        throw "Evidence byte-copy mismatch: $Source"
    }
    $rows.Add([ordered]@{stored_path=$Relative.Replace('\','/');original_path=$Source;sha256=$hash;bytes=$file.Length;proves=$Purpose;deduplicated=$false})
}
foreach ($group in $groups) {
    $files = Get-ChildItem -LiteralPath $group.Root -Recurse:$group.Recursive -File |
        Where-Object {$_.Extension -in '.json','.csv','.md' -or
            ($group.Target.StartsWith('closure\') -and $_.FullName.Contains('\live-tls\') -and
             ($_.Extension -eq '.log' -or $_.Name.EndsWith('-gitconfig')))}
    foreach ($file in $files) {
        if ($group.Target -eq 'closure\delivery-02' -and $file.Name -eq $duplicateName) { continue }
        $relative = Join-Path $group.Target $file.FullName.Substring($group.Root.Length + 1)
        Preserve $file.FullName $relative ($group.Purpose + ': ' + $file.Name)
    }
}
$authority = Get-Content -LiteralPath 'C:\ap16-accd-mingw-closure-01\delivery-03\authority-inputs.json' -Raw | ConvertFrom-Json
foreach ($item in $authority) {
    Preserve $item.Path (Join-Path 'authority' ([IO.Path]::GetFileName((Split-Path -Parent $item.Path)) + '--' + [IO.Path]::GetFileName($item.Path))) 'Exact v18 authority/provider record bound by sealed authority-inputs.json' $item.SHA256
}
$single = @(
    @{Source='C:\ag-mvp-f6-20260911\libintl-consumer-boundary-01.json';Target='boundary\libintl-consumer-boundary-01.json';Proof='Exact MinGW consumer boundary and identity evidence; static graph excludes dynamic shell launch';SHA='ecaa96a91879c81ec43ea3f51b359994881f08510ce58fb74d45fd6c56d88718'},
    @{Source='C:\ap11-accd-gettext01\clarifications\native-sh-clone-01\clarification.json';Target='boundary\native-sh-clone-clarification.json';Proof='Clone failure attributed to missing dynamically launched native sh, not libintl';SHA='2265c70f4e2d905839cdae983621f94f1c9c875628444ed3c0c0f475e4095e1d'},
    @{Source='C:\ag-tcl-e138-01\independent replay 20260911-01\independent-tls-evidence-01.json';Target='live-tls-original\independent-tls-evidence-01.json';Proof='Independent exact live module generations for candidate01 raw128 and named ZIP raw0';SHA='94a0f60c30d3a36fb20b17131e7915730ddb26c6ca763e7904030a406eec85dc'},
    @{Source='C:\ag-tcl-e138-01\independent replay 20260911-01\report-01\report.json';Target='live-tls-original\independent-full-mixed-report.json';Proof='Independent named ZIP standalone curl raw77 contrasted with Git HTTPS raw0';SHA='c44fb3f8238980bea3545938362e7e84ea5cb806780ea58b354261e3d3447c9b'},
    @{Source='C:\ap11-native-provider-intake\audit-v18-static-closure-supplement-v1.json';Target='authority\audit-v18-static-closure-supplement-v1.json';Proof='Intake acceptance of static audit supplement; no admission or blocker clearance';SHA='0938eb27b5a0fa8ac85f43c5b9d6a08cf67cf739f8364049f0b148fa9956fa74'},
    @{Source='C:\ap11-native-provider-intake\audit-v18-static-closure-supplement-v2.json';Target='authority\audit-v18-static-closure-supplement-v2.json';Proof='Intake append-only runtime corroboration; 81/22/59 unchanged';SHA='03b9a402d98f0f881a3486967938f60b0b6c14b461669a903b653bc106474b82'}
)
foreach ($item in $single) { Preserve $item.Source $item.Target $item.Proof $item.SHA }
$duplicateSource = "C:\ap16-accd-mingw-closure-01\delivery-02\live-tls\references\$duplicateName"
$canonical = "closure\delivery-03\live-tls\references\$duplicateName"
$dupHash = (Get-FileHash -LiteralPath $duplicateSource).Hash.ToLowerInvariant()
if ($dupHash -cne '9bf376600cd047912cdddb5c88f6b89301727c2b9e7bbb55ecc6e4416aba2602' -or
    $dupHash -cne (Get-FileHash -LiteralPath (Join-Path $destination $canonical)).Hash.ToLowerInvariant()) {
    throw 'Large intake duplicate does not match the approved canonical seal'
}
$rows.Add([ordered]@{stored_path=$canonical.Replace('\','/');original_path=$duplicateSource;sha256=$dupHash;bytes=(Get-Item -LiteralPath $duplicateSource).Length;proves='Byte-identical delivery-02 duplicate; canonical delivery-03 intake JSON preserved once by explicit coordinator decision';deduplicated=$true})
$known = @{
    'closure\delivery-01\report.md'='22b79d6d'
    'closure\delivery-01\handoff.json'='723462dad11535c8c76ca724bdec7c5fd4333e0aed15c0e7c308716c8021d3e4'
    'closure\delivery-01\dll-admission-table.csv'='ac964ec2'
    'closure\delivery-01\remaining-59-blockers.csv'='bf30c9c0'
    'closure\delivery-03\handoff.json'='5d68fc77f3e7357b47a031b4eeb3d452ed118d0833d3a29404a1953c4c34900d'
    'libintl\qualification\qualification.json'='a8234d5f98d75b8a33ae004afe71c817c65cf839aed8e896b2b9e81f669b2d5e'
    'pcre2\retained-qualification\qualification.json'='e43b0f5d7261618dabea1f55d3c16da9a56af986fc0b0fcaf16c4773155f6526'
}
foreach ($key in $known.Keys) {
    if (-not (Get-FileHash -LiteralPath (Join-Path $destination $key)).Hash.ToLowerInvariant().StartsWith($known[$key])) {
        throw "Required historical seal mismatch: $key"
    }
}
$index = [ordered]@{
    schema=1
    purpose='Byte-preserving shutdown backup of sealed dependency evidence; not a new admission'
    preservation_utc=[DateTime]::UtcNow.ToString('o')
    original_workspace=$Workspace
    copied_files=@($rows | Where-Object {-not $_.deduplicated}).Count
    mapped_original_paths=$rows.Count
    deduplication='Only the exact 6229477-byte intake JSON duplicate from delivery-02 maps to the preserved delivery-03 file; no other deduplication.'
    excluded='Executables, DLLs, package/source archives, extracted payloads, build output, reobtainable CA bundles and files not explicitly selected.'
    files=@($rows | Sort-Object stored_path,original_path)
}
$indexPath = Join-Path $destination 'preservation-index.json'
[IO.File]::WriteAllText($indexPath, ($index | ConvertTo-Json -Depth 8) + "`n", [Text.UTF8Encoding]::new($false))
$lines = [Collections.Generic.List[string]]::new()
$lines.Add("| Preserved file | What it proves | Bytes | SHA256 | Original absolute path |")
$lines.Add("|---|---|---:|---|---|")
foreach ($row in $index.files) {
    $lines.Add('| `' + $row.stored_path + '` | ' + $row.proves.Replace('|','\|') + ' | ' + $row.bytes + ' | `' + $row.sha256 + '` | `' + $row.original_path + '` |')
}
$readme = Join-Path $destination 'README.md'
$text = [IO.File]::ReadAllText($readme)
if (-not $text.Contains('<!-- PRESERVATION_INVENTORY -->')) { throw 'README inventory marker missing' }
[IO.File]::WriteAllText($readme, $text.Replace('<!-- PRESERVATION_INVENTORY -->', ($lines -join "`n")), [Text.UTF8Encoding]::new($false))
[ordered]@{copied_files=$index.copied_files;mapped_paths=$index.mapped_original_paths;total_bytes=($rows|Where-Object {-not $_.deduplicated}|Measure-Object -Property bytes -Sum).Sum;index_sha256=(Get-FileHash -LiteralPath $indexPath).Hash.ToLowerInvariant()}|ConvertTo-Json
