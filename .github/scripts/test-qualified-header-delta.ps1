#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\cohort-inventory.ps1"
$manifestHash = (Get-FileHash -LiteralPath $Manifest).Hash.ToLowerInvariant()
if ($manifestHash -cne '80e5dd2079f540bb1c0ee448ce27d211c8e3608b1f9e690edbd0c628b88f7739') {
    throw 'Header-delta manifest differs from the accepted source-owner pin.'
}
$data = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json
if ($data.Kind -cne 'native-mingw-header-delta' -or $data.Status -cne 'qualified-header-delta' -or
    $data.Target -cne 'aarch64-w64-mingw32' -or $data.Host -cne 'Windows ARM64/UCRT' -or
    $data.ChangedFiles.Count -ne 1 -or $data.Files.Count -ne 4030) { throw 'Unexpected header-delta declaration.' }
$descriptors = @($data.BaselineManifest,$data.SourceGuard,$data.NativeQualification,$data.RawPEIdentities)
foreach ($descriptor in $descriptors) {
    if ((Get-FileHash -LiteralPath $descriptor.Path).Hash.ToLowerInvariant() -cne $descriptor.SHA256) {
        throw 'Bound header-delta evidence changed.'
    }
}
$baselineData = Get-Content -Raw -LiteralPath $data.BaselineManifest.Path | ConvertFrom-Json
$baseline = & "$PSScriptRoot\test-qualified-native-cohort.ps1" -Prefix $baselineData.Prefix -Manifest $data.BaselineManifest.Path
if ($baseline.Epoch -cne $data.BaselineManifest.Epoch) { throw 'Header-delta baseline qualification changed.' }
$change = $data.ChangedFiles[0]
if ($change.Path -cne 'aarch64-w64-mingw32\include\_mingw.h' -or
    $change.BeforeSHA256 -cne 'b6959899088af2f03ae26b714098fa8f591f9a8e9e502857f2cf668af2871292' -or
    $change.SHA256 -cne 'dc7a4b6814d2529862e4e254935adddf1c6ffddb0cd5069d8146513c5f81efb9') {
    throw 'Header delta is not the exact C89 inline spelling repair.'
}
$expected = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($file in $baselineData.Files) { $expected.Add($file.Path,$file.SHA256) }
if ($expected[$change.Path] -cne $change.BeforeSHA256) { throw 'Original header does not match the declared baseline.' }
$expected[$change.Path] = $change.SHA256
$expected.Add('share\toolchain-epochs\fastfail-c89\mingw-woarm64-fastfail-c89-inline.patch',$data.Source.PatchSHA256)
$expected.Add('share\toolchain-epochs\fastfail-c89\pinned-_mingw.h.in',$data.Source.TemplateSHA256)
foreach ($file in $data.Files) {
    if (-not $expected.ContainsKey($file.Path) -or $expected[$file.Path] -cne $file.SHA256) {
        throw "Header cohort changed another input: $($file.Path)"
    }
}
Assert-CohortInventory $Prefix @($data.Files)
$epoch = & "$PSScriptRoot\get-toolchain-epoch.ps1" -Inputs $data.Files
if ($epoch -cne $data.Epoch) { throw 'Header cohort epoch does not match its full inventory.' }
$old = [IO.File]::ReadAllText((Join-Path $baseline.Prefix $change.Path))
$new = [IO.File]::ReadAllText((Join-Path $Prefix $change.Path))
if ($old.Replace('#define __MINGW_FASTFAIL_INLINE static inline','#define __MINGW_FASTFAIL_INLINE static __inline__') -cne $new) {
    throw 'Header change extends beyond the qualified spelling fix.'
}
$sourceGuard = Get-Content -Raw -LiteralPath $data.SourceGuard.Path | ConvertFrom-Json
$native = Get-Content -Raw -LiteralPath $data.NativeQualification.Path | ConvertFrom-Json
if ($sourceGuard.passed -ne $true -or $native.passed -ne $true -or $native.runs.Count -ne 36 -or
    $native.compiler_process.machine -cne '0xAA64' -or $native.header.sha256 -cne $change.SHA256 -or
    $native.c99_assembly_unchanged_except_header_location -ne $true) { throw 'Header source/native controls are incomplete.' }
foreach ($run in $native.runs) {
    $expectedExit = if ($run.name -ceq 'old-c89') { 1 } else { 0 }
    if ($run.exit_code -ne $expectedExit) { throw "Unexpected header control result: $($run.name)" }
}
[pscustomobject]@{
    Kind='qualified-native-mingw-header-delta-binding';Prefix=(Resolve-Path -LiteralPath $Prefix).ProviderPath
    Epoch=$epoch;Target=$data.Target;Files=$data.Files;BaselineEpoch=$baseline.Epoch
    Descriptors=@(@{Path=(Resolve-Path -LiteralPath $Manifest).ProviderPath;SHA256=$manifestHash}) + $descriptors
    Scope='Explicit header-only successor; unchanged binary baseline plus separately bound C89/native delta controls, not package admission'
}
