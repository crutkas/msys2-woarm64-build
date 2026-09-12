#requires -Version 7.3
param(
    [Parameter(Mandatory)][ValidateSet('zlib', 'libiconv-bootstrap')][string] $Package,
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
$settings = @{
    zlib = @{
        Build='e206df14f9a4aa12dca6c88e13427e03ca2d0233100f243426c7cd9b5bfe4960'
        Consumer='d1899371f8c00c18452b4bd96b99bb7677b5a2e63cf5645793264d5cd5855506'
        Source='c53223c0fff652c40bb0f98c6fadd94440b4d3d6f2bd2b6fc491683ca0b5c8e0'
        ProducerName='zlib-msys';Version='1.3.2';ConsumerName='native-zlib-consumer.exe'
        Dlls=@('msys-z.dll');Excluded=@()
    }
    'libiconv-bootstrap' = @{
        Build='f2cdb106a5e3ae89fd5d4467e4352aa1bd864f04652999e26d4f9f5286603732'
        Consumer='86bea80ec80e535c7565cf5689c205cafb4dcccd4a21d290ce9f519d1647148b'
        Source='ea7fe95778e8cbedab64c082f07e99ed0c82678503e903fac3fb4cc7fbdd3ef4'
        ProducerName='libiconv-bootstrap';Version='1.19';ConsumerName='native-iconv-consumer.exe'
        Dlls=@('msys-iconv-2.dll','msys-charset-1.dll')
        Excluded=@('usr\lib\libiconv.la','usr\lib\libcharset.la')
    }
}[$Package]
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'MSYS library package output must be new.' }
$pins = @(
    @{Path=$BuildReceipt;SHA256=$settings.Build}, @{Path=$ConsumerReceipt;SHA256=$settings.Consumer},
    @{Path=$SourceManifest;SHA256=$settings.Source},
    @{Path=$Manifest;SHA256='bf9042587a9a474641e8ffbf05b03afb7c1608a82c7feca634b94ac3c15fb522'}
)
foreach ($pin in $pins) {
    if ((Get-FileHash -LiteralPath $pin.Path).Hash.ToLowerInvariant() -cne $pin.SHA256) {
        throw "Published MSYS library input changed: $($pin.Path)"
    }
}
$qualified = & "$PSScriptRoot\read-qualified-toolchain.ps1" -Prefix $Prefix -Manifest $Manifest
$build = Get-Content -Raw -LiteralPath $BuildReceipt | ConvertFrom-Json -AsHashtable
$consumer = Get-Content -Raw -LiteralPath $ConsumerReceipt | ConvertFrom-Json -AsHashtable
$source = Get-Content -Raw -LiteralPath $SourceManifest | ConvertFrom-Json -AsHashtable
if ($build.status -cne 'native-msys-library-built-checked-bootstrap-driver' -or
    $build.package -cne $settings.ProducerName -or $source.source.version -cne $settings.Version -or
    $build.process.exit -ne 0 -or $build.process.passed -ne $true -or
    $consumer.passed -ne $true -or $consumer.process.exit -ne 0 -or
    $consumer.stage_manifest_sha256 -cne $settings.Build -or
    (Get-FileHash -LiteralPath $ConsumerExecutable).Hash.ToLowerInvariant() -cne $consumer.consumer_sha256 -or
    $consumer.dlls['msys-2.0.dll'] -cne $qualified.Components.RuntimeDll.SHA256) {
    throw 'Native library producer/consumer/source/runtime qualification is incomplete.'
}
if ($Package -eq 'libiconv-bootstrap' -and
    'Encoder CLI NLS explicitly disabled until native MSYS libintl exists' -cnotin $build.limitations) {
    throw 'The iconv bootstrap NLS limitation must be retained explicitly.'
}
foreach ($pair in @(@('cc1','CC1'),@('as','Assembler'),@('ld','Linker'))) {
    if ($build.support[$pair[0]].sha256 -cne $qualified.Components[$pair[1]].SHA256 -or
        $consumer.support[$pair[0]].sha256 -cne $qualified.Components[$pair[1]].SHA256) {
        throw "Producer/consumer tool differs from the qualified SDK: $($pair[0])"
    }
}
$files = @($build.files.GetEnumerator() | ForEach-Object { @{Path=$_.Key.Replace('/','\');SHA256=$_.Value.sha256} })
Assert-CohortInventory $Payload $files
foreach ($dll in $settings.Dlls) {
    if ($consumer.dlls[$dll] -cne $build.files["usr/bin/$dll"].sha256) { throw "Unpaired library DLL: $dll" }
}
foreach ($protected in $Payload, $Prefix) {
    $path = (Resolve-Path -LiteralPath $protected).ProviderPath.TrimEnd('\')
    if ($output.StartsWith("$path\",[StringComparison]::OrdinalIgnoreCase)) { throw 'Output must not be inside immutable inputs.' }
}
New-Item -ItemType Directory -Path "$output\provenance","$output\control" | Out-Null
Copy-Item -LiteralPath $Payload -Destination "$output\payload" -Recurse
Assert-CohortInventory "$output\payload" $files
Copy-Item -LiteralPath $BuildReceipt -Destination "$output\provenance\build-receipt.json"
Copy-Item -LiteralPath $ConsumerReceipt -Destination "$output\provenance\consumer-receipt.json"
Copy-Item -LiteralPath $SourceManifest -Destination "$output\provenance\source-manifest.json"
Copy-Item -LiteralPath $Manifest -Destination "$output\provenance\sdk-manifest.json"
Copy-Item -LiteralPath $ConsumerExecutable -Destination (Join-Path "$output\control" $settings.ConsumerName)
Copy-Item -LiteralPath $qualified.Components.RuntimeDll.Path -Destination "$output\control\msys-2.0.dll"
if ((Get-FileHash -LiteralPath "$output\control\msys-2.0.dll").Hash.ToLowerInvariant() -cne $consumer.dlls['msys-2.0.dll']) {
    throw 'Copied runtime changed.'
}
$changes = @()
if ($Package -eq 'zlib') {
    $pc = [IO.File]::ReadAllText("$output\payload\usr\lib\pkgconfig\zlib.pc")
    if ([regex]::Matches($pc,[regex]::Escape(' -L${sharedlibdir}')).Count -ne 1) { throw 'Unexpected pinned zlib.pc cleanup input.' }
    $changes += @{Path='usr\lib\pkgconfig\zlib.pc';Before=$build.files['usr/lib/pkgconfig/zlib.pc'].sha256
        ExpectedContent=$pc.Replace(' -L${sharedlibdir}','');Reason='Exact upstream package cleanup of duplicate shared-library search flag'}
}
$lines = @($files | Sort-Object Path | ForEach-Object { "$($_.SHA256)  payload/$($_.Path.Replace('\','/'))" })
[IO.File]::WriteAllText("$output\payload-files.sha256",($lines -join "`n")+"`n",[Text.UTF8Encoding]::new($false))
foreach ($part in 'payload','provenance','control') {
    & "$env:SystemRoot\System32\tar.exe" -cf "$output\$part.tar" -C $output $part
    if ($LASTEXITCODE) { throw "Library $part archive failed." }
}
$text = [IO.File]::ReadAllText("$PSScriptRoot\..\..\..\packages\native-msys-$Package\PKGBUILD.in").Replace("`r`n","`n")
foreach ($entry in @(
    @{Token='@PAYLOAD_SHA256@';File='payload.tar'}, @{Token='@FILES_SHA256@';File='payload-files.sha256'},
    @{Token='@PROVENANCE_SHA256@';File='provenance.tar'}, @{Token='@CONTROL_SHA256@';File='control.tar'}
)) {
    if ([regex]::Matches($text,[regex]::Escape($entry.Token)).Count -ne 1) { throw 'Unexpected checksum template.' }
    $text = $text.Replace($entry.Token,(Get-FileHash -LiteralPath (Join-Path $output $entry.File)).Hash.ToLowerInvariant())
}
[IO.File]::WriteAllText("$output\PKGBUILD",$text,[Text.UTF8Encoding]::new($false))
Assert-CohortInventory $Payload $files
[ordered]@{
    Status='qualified-native-msys-library-payload-prepared';Package=$Package;Version=$settings.Version
    Epoch=$qualified.EpochSHA256;SourcePayload=$Payload;PayloadFiles=$files;Pins=$pins
    Output=$output;ConsumerName=$settings.ConsumerName;Dlls=$settings.Dlls
    ExpectedPackagingChanges=$changes;ExcludedFiles=$settings.Excluded
    RecipeSHA256=(Get-FileHash -LiteralPath "$output\PKGBUILD").Hash.ToLowerInvariant()
    BuildLimitations=$build.limitations;CliNlsEnabled=$(if ($Package -eq 'libiconv-bootstrap') { $false } else { $null })
    Scope='Native MSYS packages only; iconv CLI bootstrap is not a normal iconv provider'
    RetainedSdkTargetLibrariesRebuilt=$false;InstalledIntoBootstrap=$false
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$output\preparation.json" -Encoding utf8
