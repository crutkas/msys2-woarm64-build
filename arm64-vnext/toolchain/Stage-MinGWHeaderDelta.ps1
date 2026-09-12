[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $BaselineManifest,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string] $BaselineManifestSHA256,
    [Parameter(Mandatory)][string] $PinnedHeaderTemplate,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $StageReceipt
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Hash([string] $Path) { (Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant() }
if ((Hash $BaselineManifest) -cne $BaselineManifestSHA256) { throw 'Baseline receipt differs.' }
$baseline = Get-Content -Raw -LiteralPath $BaselineManifest | ConvertFrom-Json
if ($baseline.SchemaVersion -ne 1 -or $baseline.Status -cne 'qualified' -or
    $baseline.Kind -cne 'native-mingw-package-cohort' -or
    $baseline.Target -cne 'aarch64-w64-mingw32' -or $baseline.Host -cne 'Windows ARM64') {
    throw 'An independently qualified native MinGW package cohort is required.'
}
$oldRoot = [IO.Path]::GetFullPath($baseline.Prefix).TrimEnd('\') + '\'
$newRoot = [IO.Path]::GetFullPath($Prefix).TrimEnd('\') + '\'
$receiptPath = [IO.Path]::GetFullPath($StageReceipt)
if ((Test-Path -LiteralPath $Prefix) -or (Test-Path -LiteralPath $StageReceipt) -or
    $newRoot.StartsWith($oldRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $receiptPath.StartsWith($oldRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $receiptPath.StartsWith($newRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use new candidate and evidence paths outside the immutable baseline.'
}
if ((Hash $PinnedHeaderTemplate) -cne 'eeef89bcc19b9449fb67aa54ef0d5048dedd70464ad231281e250cd5699285e6') {
    throw 'Expected the unchanged _mingw.h.in blob from pinned 70d63e7c9a477b8b275a9782b289fbf1614b6e9e.'
}
$patch = Join-Path $PSScriptRoot 'mingw-woarm64-fastfail-c89-inline.patch'
if ((Hash $patch) -cne '5c89fe22fe5b9a63b43ca4e82b6c1f9fee802cd259a75cf238a821d44529ebd6') {
    throw 'The header delta patch identity changed.'
}
$relativeHeader = 'aarch64-w64-mingw32\include\_mingw.h'
$oldLine = '#define __MINGW_FASTFAIL_INLINE static inline'
$newLine = '#define __MINGW_FASTFAIL_INLINE static __inline__'
foreach ($path in @($PinnedHeaderTemplate, (Join-Path $oldRoot $relativeHeader))) {
    $content = [IO.File]::ReadAllText($path)
    if ([regex]::Matches($content, [regex]::Escape($oldLine)).Count -ne 1 -or $content.Contains($newLine)) {
        throw "The expected unmodified ARM64 fastfail definition is missing: $path"
    }
}
$expected = @{}
foreach ($file in $baseline.Files) {
    $absolute = [IO.Path]::GetFullPath((Join-Path $oldRoot $file.Path))
    if (-not $absolute.StartsWith($oldRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $expected.ContainsKey($file.Path) -or (Hash $absolute) -cne $file.SHA256) {
        throw "Invalid or changed baseline file: $($file.Path)"
    }
    $expected.Add($file.Path, $file.SHA256)
}
if (@($expected.Keys | Where-Object { $_ -like 'share\toolchain-epochs\fastfail-c89\*' }).Count) {
    throw 'The baseline already contains a fastfail-c89 epoch.'
}
$items = @(Get-ChildItem -LiteralPath $oldRoot -Force -Recurse)
if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Baseline links must be materialized before creating a Windows header cohort.'
}
$files = @($items | Where-Object { -not $_.PSIsContainer })
if ($files.Count -ne $expected.Count) { throw 'Baseline inventory file count differs.' }
foreach ($file in $files) {
    if (-not $expected.ContainsKey([IO.Path]::GetRelativePath($oldRoot, $file.FullName))) {
        throw "Uninventoried baseline file: $($file.FullName)"
    }
}
if ($expected[$relativeHeader] -cne 'b6959899088af2f03ae26b714098fa8f591f9a8e9e502857f2cf668af2871292') {
    throw 'This delta expects the failure-bound cc02 header identity.'
}
Copy-Item -LiteralPath $oldRoot.TrimEnd('\') -Destination $Prefix -Recurse
$headerPath = Join-Path $Prefix $relativeHeader
$header = [IO.File]::ReadAllText($headerPath)
[IO.File]::WriteAllText($headerPath, $header.Replace($oldLine, $newLine), [Text.UTF8Encoding]::new($false))
$headerHash = Hash $headerPath
foreach ($file in $baseline.Files) {
    $wanted = if ($file.Path -ceq $relativeHeader) { $headerHash } else { $file.SHA256 }
    if ((Hash (Join-Path $oldRoot $file.Path)) -cne $file.SHA256 -or
        (Hash (Join-Path $Prefix $file.Path)) -cne $wanted) {
        throw "Unexpected baseline or delta change: $($file.Path)"
    }
}
$metadata = [IO.Directory]::CreateDirectory((Join-Path $Prefix 'share\toolchain-epochs\fastfail-c89')).FullName
Copy-Item -LiteralPath $patch -Destination $metadata
Copy-Item -LiteralPath $PinnedHeaderTemplate -Destination "$metadata\pinned-_mingw.h.in"
[ordered]@{
    SchemaVersion = 1; Status = 'header-delta-candidate-not-qualified'
    Prefix = $newRoot.TrimEnd('\')
    BaselineManifest = $BaselineManifest; BaselineManifestSHA256 = $BaselineManifestSHA256
    BaselinePrefix = $oldRoot.TrimEnd('\'); BaselineEpoch = $baseline.Epoch
    ChangedHeader = $relativeHeader
    PreviousHeaderSHA256 = $expected[$relativeHeader]; HeaderSHA256 = $headerHash
    Source = @{
        Repository = 'https://github.com/Windows-on-ARM-Experiments/mingw-woarm64.git'
        Revision = '70d63e7c9a477b8b275a9782b289fbf1614b6e9e'
        TemplateSHA256 = Hash $PinnedHeaderTemplate
        PatchSHA256 = Hash $patch
    }
    CompilerAndLibraryBinariesUnchanged = $true
    BaselineFiles = $baseline.Files
    Scope = 'Only the C89-safe keyword spelling changes in the ARM64 fastfail header; no full new compiler/CRT/FP qualification or implicit package admission'
} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $StageReceipt -Encoding utf8
Write-Output "Staged unqualified C89 header delta at $Prefix"
