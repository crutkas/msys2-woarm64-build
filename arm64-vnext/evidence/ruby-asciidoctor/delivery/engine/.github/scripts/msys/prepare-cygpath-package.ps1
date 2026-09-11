#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest,
    [Parameter(Mandatory)][string] $UtilityReceipt,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\cohort-inventory.ps1"
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Cygpath package preparation must use a new output.' }
if ((Get-FileHash -LiteralPath $UtilityReceipt).Hash.ToLowerInvariant() -cne
    'd7bd08ab55bcbe3b1e3086a65c9f07463d09fd3ff09c071070b6b7b60b7d97c6') { throw 'Native cygpath receipt differs from the accepted pin.' }
$proof = Get-Content -Raw -LiteralPath $UtilityReceipt | ConvertFrom-Json
$qualified = & "$PSScriptRoot\read-qualified-toolchain.ps1" -Prefix $Prefix -Manifest $Manifest
if ($proof.status -cne 'native-msys-cygpath-utility-qualified' -or
    $proof.target -cne 'aarch64-pc-cygwin/MSYS' -or $proof.results.cases -ne 32 -or $proof.results.passed -ne 32 -or
    $proof.paired_runtime.sha256 -cne $qualified.Components.RuntimeDll.SHA256) {
    throw 'Native cygpath qualification is incomplete or paired to a different runtime.'
}
foreach ($binding in $proof.payload, $proof.license, $proof.native_summary, $proof.native_cases,
    $proof.native_process, $proof.native_loaded_modules, $proof.runtime_receipt, $proof.sdk_receipt) {
    if ((Get-FileHash -LiteralPath $binding.path).Hash.ToLowerInvariant() -cne $binding.sha256) {
        throw "Native cygpath input changed: $($binding.path)"
    }
}
$files = @(
    @{Path='usr\bin\cygpath.exe';SHA256=$proof.payload.sha256},
    @{Path='usr\share\licenses\cygpath\CYGWIN_LICENSE';SHA256=$proof.license.sha256}
)
Assert-CohortInventory $proof.payload_root $files
foreach ($protected in $proof.payload_root, $Prefix) {
    $path = (Resolve-Path -LiteralPath $protected).ProviderPath.TrimEnd('\')
    if ($output.StartsWith("$path\",[StringComparison]::OrdinalIgnoreCase)) { throw 'Package output must not be inside immutable inputs.' }
}
New-Item -ItemType Directory -Path "$output\provenance","$output\control" | Out-Null
Copy-Item -LiteralPath $proof.payload_root -Destination "$output\payload" -Recurse
Assert-CohortInventory "$output\payload" $files
Copy-Item -LiteralPath $UtilityReceipt -Destination "$output\provenance\utility-receipt.json"
Copy-Item -LiteralPath $Manifest -Destination "$output\provenance\sdk-manifest.json"
Copy-Item -LiteralPath $proof.native_summary.path -Destination "$output\provenance\native-summary.json"
Copy-Item -LiteralPath $proof.native_cases.path -Destination "$output\provenance\native-cases.json"
Copy-Item -LiteralPath $qualified.Components.RuntimeDll.Path -Destination "$output\control\msys-2.0.dll"
if ((Get-FileHash -LiteralPath "$output\control\msys-2.0.dll").Hash.ToLowerInvariant() -cne $proof.paired_runtime.sha256) {
    throw 'Control runtime changed.'
}
$lines = @($files | ForEach-Object { "$($_.SHA256)  payload/$($_.Path.Replace('\','/'))" })
[IO.File]::WriteAllText("$output\payload-files.sha256",($lines -join "`n")+"`n",[Text.UTF8Encoding]::new($false))
foreach ($part in 'payload','provenance','control') {
    & "$env:SystemRoot\System32\tar.exe" -cf "$output\$part.tar" -C $output $part
    if ($LASTEXITCODE) { throw "Cygpath $part archive failed." }
}
$template = [IO.Path]::GetFullPath("$PSScriptRoot\..\..\..\packages\native-msys-cygpath\PKGBUILD.in")
$text = [IO.File]::ReadAllText($template).Replace("`r`n","`n")
foreach ($entry in @(
    @{Token='@PAYLOAD_SHA256@';File='payload.tar'}, @{Token='@FILES_SHA256@';File='payload-files.sha256'},
    @{Token='@PROVENANCE_SHA256@';File='provenance.tar'}, @{Token='@CONTROL_SHA256@';File='control.tar'}
)) {
    if ([regex]::Matches($text,[regex]::Escape($entry.Token)).Count -ne 1) { throw 'Unexpected checksum template.' }
    $text = $text.Replace($entry.Token,(Get-FileHash -LiteralPath (Join-Path $output $entry.File)).Hash.ToLowerInvariant())
}
[IO.File]::WriteAllText("$output\PKGBUILD",$text,[Text.UTF8Encoding]::new($false))
Assert-CohortInventory $proof.payload_root $files
[ordered]@{
    Status='qualified-native-msys-cygpath-payload-prepared';Epoch=$qualified.EpochSHA256
    Input=$UtilityReceipt;SourcePayload=$proof.payload_root;PayloadFiles=$files
    Output=$output;RecipeSHA256=(Get-FileHash -LiteralPath "$output\PKGBUILD").Hash.ToLowerInvariant()
    BuildHost=$proof.build_host;ExecutionHost=$proof.execution_host
    Scope='Standalone native utility split, no runtime provider claim or runtime DLL in package'
    ProducerCompilerRebuilt=$false;RetainedSdkTargetLibrariesRebuilt=$false;InstalledIntoBootstrap=$false
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output\preparation.json" -Encoding utf8
