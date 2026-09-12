#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest,
    [Parameter(Mandatory)][string] $Payload,
    [Parameter(Mandatory)][string] $BuildReceipt,
    [Parameter(Mandatory)][string] $ConsumerReceipt,
    [Parameter(Mandatory)][string] $ConsumerExecutable,
    [Parameter(Mandatory)][string] $SourceManifest,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\cohort-inventory.ps1"
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Libxcrypt package preparation must use a new output.' }
$pins = @(
    @{Path=$BuildReceipt;SHA256='514e4ae1e59867a143e416ab9c6cde30efe8ecaaaf958012d03b62e4f7ae6c97'},
    @{Path=$ConsumerReceipt;SHA256='a1d13f86fe48ca418ed6b123d098c7da87d5c8e323db9a02b0909a6a0cb7fd40'},
    @{Path=$SourceManifest;SHA256='52c89e7429bbaf2425ae9d58ce95b3a67be6ec7b36cd54dcb45d26db9b68d51d'},
    @{Path=$Manifest;SHA256='bf9042587a9a474641e8ffbf05b03afb7c1608a82c7feca634b94ac3c15fb522'}
)
foreach ($pin in $pins) {
    if ((Get-FileHash -LiteralPath $pin.Path).Hash.ToLowerInvariant() -cne $pin.SHA256) {
        throw "Published libxcrypt input changed: $($pin.Path)"
    }
}
$qualified = & "$PSScriptRoot\read-qualified-toolchain.ps1" -Prefix $Prefix -Manifest $Manifest
$build = Get-Content -Raw -LiteralPath $BuildReceipt | ConvertFrom-Json -AsHashtable
$consumer = Get-Content -Raw -LiteralPath $ConsumerReceipt | ConvertFrom-Json -AsHashtable
if ($build.status -cne 'native-msys-library-built-checked-bootstrap-driver' -or $build.package -cne 'libxcrypt' -or
    $build.process.passed -ne $true -or $build.process.exit -ne 0 -or
    $consumer.passed -ne $true -or $consumer.process.exit -ne 0 -or
    $consumer.stage_manifest_sha256 -cne $pins[0].SHA256 -or
    $consumer.dlls['msys-2.0.dll'] -cne $qualified.Components.RuntimeDll.SHA256 -or
    (Get-FileHash -LiteralPath $ConsumerExecutable).Hash.ToLowerInvariant() -cne $consumer.consumer_sha256) {
    throw 'Native libxcrypt source-build/runtime-consumer qualification is incomplete or unpaired.'
}
foreach ($pair in @(@('cc1','CC1'),@('as','Assembler'),@('ld','Linker'))) {
    if ($build.support[$pair[0]].sha256 -cne $qualified.Components[$pair[1]].SHA256 -or
        $consumer.support[$pair[0]].sha256 -cne $qualified.Components[$pair[1]].SHA256) {
        throw "Libxcrypt producer/consumer tool does not match the qualified SDK: $($pair[0])"
    }
}
$files = @($build.files.GetEnumerator() | ForEach-Object {
    @{Path=$_.Key.Replace('/','\');SHA256=$_.Value.sha256}
})
Assert-CohortInventory $Payload $files
foreach ($protected in $Payload, $Prefix) {
    $path = (Resolve-Path -LiteralPath $protected).ProviderPath.TrimEnd('\')
    if ($output.StartsWith("$path\",[StringComparison]::OrdinalIgnoreCase)) { throw 'Package preparation must not write inside immutable inputs.' }
}
New-Item -ItemType Directory -Path "$output\provenance","$output\control" | Out-Null
Copy-Item -LiteralPath $Payload -Destination "$output\payload" -Recurse
Assert-CohortInventory "$output\payload" $files
Copy-Item -LiteralPath $BuildReceipt -Destination "$output\provenance\build-receipt.json"
Copy-Item -LiteralPath $ConsumerReceipt -Destination "$output\provenance\consumer-receipt.json"
Copy-Item -LiteralPath $SourceManifest -Destination "$output\provenance\source-manifest.json"
Copy-Item -LiteralPath $Manifest -Destination "$output\provenance\sdk-manifest.json"
Copy-Item -LiteralPath $ConsumerExecutable -Destination "$output\control\native-crypt-consumer.exe"
Copy-Item -LiteralPath $qualified.Components.RuntimeDll.Path -Destination "$output\control\msys-2.0.dll"
if ((Get-FileHash -LiteralPath "$output\control\msys-2.0.dll").Hash.ToLowerInvariant() -cne $consumer.dlls['msys-2.0.dll']) {
    throw 'Copied consumer runtime changed.'
}
$lines = @($files | Sort-Object Path | ForEach-Object { "$($_.SHA256)  payload/$($_.Path.Replace('\','/'))" })
[IO.File]::WriteAllText("$output\payload-files.sha256",($lines -join "`n")+"`n",[Text.UTF8Encoding]::new($false))
foreach ($part in 'payload','provenance','control') {
    & "$env:SystemRoot\System32\tar.exe" -cf "$output\$part.tar" -C $output $part
    if ($LASTEXITCODE) { throw "Libxcrypt $part archive failed." }
}
$template = [IO.Path]::GetFullPath("$PSScriptRoot\..\..\..\packages\native-msys-libxcrypt\PKGBUILD.in")
$text = [IO.File]::ReadAllText($template).Replace("`r`n","`n")
foreach ($entry in @(
    @{Token='@PAYLOAD_SHA256@';File='payload.tar'}, @{Token='@FILES_SHA256@';File='payload-files.sha256'},
    @{Token='@PROVENANCE_SHA256@';File='provenance.tar'}, @{Token='@CONTROL_SHA256@';File='control.tar'}
)) {
    if ([regex]::Matches($text,[regex]::Escape($entry.Token)).Count -ne 1) { throw 'Unexpected package template checksum token.' }
    $text = $text.Replace($entry.Token,(Get-FileHash -LiteralPath (Join-Path $output $entry.File)).Hash.ToLowerInvariant())
}
[IO.File]::WriteAllText("$output\PKGBUILD",$text,[Text.UTF8Encoding]::new($false))
Assert-CohortInventory $Payload $files
[ordered]@{
    Status='qualified-native-msys-libxcrypt-payload-prepared';Epoch=$qualified.EpochSHA256
    SourcePayload=$Payload;PayloadFiles=$files;Pins=$pins;Output=$output
    RecipeSHA256=(Get-FileHash -LiteralPath "$output\PKGBUILD").Hash.ToLowerInvariant()
    Scope='Real source-built MSYS payload packaged as runtime/devel splits; no compiler rebuild or MinGW substitution'
    RetainedSdkTargetLibrariesRebuilt=$false;LibraryPayloadRebuiltByProducer=$true;InstalledIntoBootstrap=$false
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output\preparation.json" -Encoding utf8
