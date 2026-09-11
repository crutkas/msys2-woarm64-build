#requires -Version 7.3
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\libiconv-current-d70-v1',
    [string]$Stage = 'C:\ag-bash-e138-01\iconv-full-recovery-02\stage',
    [string]$Inventory = 'C:\ag-bash-e138-01\iconv-full-recovery-02\stage.inventory.json',
    [string]$ProducerResult = 'C:\ag-bash-e138-01\iconv-full-recovery-02\result.json',
    [string]$SharedProof = 'C:\ag-bash-e138-01\iconv-full-shared-proof-recovery-01\result.json',
    [string]$StaticProof = 'C:\ag-bash-e138-01\iconv-full-static-proof-recovery-01\result.json',
    [string]$PinnedRecipe = 'C:\ag-bash-e138-01\sources\libiconv\PKGBUILD',
    [string]$BootstrapRoot = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64',
    [string]$ToolchainBin = 'C:\agtc-libs-01\sdk\bin',
    [string]$RuntimeDll = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\recipe\payload\runtime\usr\bin\msys-2.0.dll',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf',
    [string]$CompressionPolicyHandoff = 'C:\ap06-2160\compression-policy-handoff-20260909-01\handoff.json',
    [string]$CompressionPolicyRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$inventoryPin = 'ade429de6ca8ea1c6da0e9937ba4d52be1dc1b2250a04ed0901659b4c72635ca'
$producerPin = '44839c2e10f7a4efe9e0e5824588c807378f84368c684c4631acc459353d2b16'
$sharedProofPin = '8662f65a7d8d6877c0b8cefb2bdcd5ed9d2b1f3473f4c87d31841a6da903f50a'
$staticProofPin = 'ed46c28ee4a6e5cc56f55ea4d0d56e381046e9ff035c0889b2aa90a70fdb8485'
$recipePin = '72144bedfb5efa0b492c27cde22918e14c0745896e624ab063c735e2bb516c7c'
$runtimePin = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$iconvPin = '86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215'
$charsetPin = '0d6c999892ae10d3e173792596ef4653514777eebddb75015868a9056e6f7d73'
$iconvExePin = '1354cb317c75b52db5f2e0d808d6612a561f93cbbafe0e2900d090e061acc8fc'

if (-not $CompressionPolicyRoot) {
    $CompressionPolicyRoot = Join-Path (
        Split-Path -Parent $PSScriptRoot
    ) 'native-packaging\compression-policy'
}

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Hash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected,
        [Parameter(Mandatory)][string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
    $actual = Get-Hash $Path
    if ($actual -ne $Expected) {
        throw "$Label changed: expected $Expected, got $actual"
    }
}

function Convert-ToMsysPath {
    param([Parameter(Mandatory)][string]$Path)

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to MSYS form: $resolved"
    }
    return "/$($Matches[1].ToLowerInvariant())/$($Matches[2] -replace '\\', '/')"
}

function Assert-GzipPayloadHash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )

    $stream = [IO.File]::OpenRead($Path)
    try {
        $gzip = [IO.Compression.GZipStream]::new(
            $stream,
            [IO.Compression.CompressionMode]::Decompress
        )
        try {
            $hash = [Security.Cryptography.SHA256]::Create()
            try {
                $actual = [Convert]::ToHexString(
                    $hash.ComputeHash($gzip)
                ).ToLowerInvariant()
            }
            finally {
                $hash.Dispose()
            }
        }
        finally {
            $gzip.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
    if ($actual -ne $Expected) {
        throw "Decompressed hash mismatch for ${Path}: expected $Expected, got $actual"
    }
}

$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw "Output must be new: $output"
}
Assert-Hash $Inventory $inventoryPin 'Qualified libiconv inventory'
Assert-Hash $ProducerResult $producerPin 'Qualified libiconv producer result'
Assert-Hash $SharedProof $sharedProofPin 'Qualified libiconv shared proof'
Assert-Hash $StaticProof $staticProofPin 'Qualified libiconv static proof'
Assert-Hash $PinnedRecipe $recipePin 'Pinned MSYS2 libiconv recipe'
Assert-Hash $CompressionPolicyHandoff (
    '406b2632c55b136be368d12609c55649a98b1d852d7f65b506149523b9ddd9dc'
) 'Compression policy handoff'
foreach ($entry in ([ordered]@{
    'makepkg-compression-policy.sh' = 'a2e161767e4d9dea88768eac448170ec53981acb05efe06ad7064e2ddafc62d1'
    'makepkg-compression.sh' = '41bc1d98d912ddbca60f1a6369be0ee9f97959787dcf499eaee814a5f01406d6'
    'with-makepkg-compression.sh' = 'b3324cc71bb44ad74ed00064e420db90158fb9aa2da022667a7fe6eaa3e8571c'
}).GetEnumerator()) {
    Assert-Hash (
        Join-Path $CompressionPolicyRoot $entry.Key
    ) $entry.Value "Compression policy $($entry.Key)"
}

$inventoryData = Get-Content -Raw -LiteralPath $Inventory | ConvertFrom-Json -AsHashtable
$producer = Get-Content -Raw -LiteralPath $ProducerResult | ConvertFrom-Json -AsHashtable
$shared = Get-Content -Raw -LiteralPath $SharedProof | ConvertFrom-Json -AsHashtable
$static = Get-Content -Raw -LiteralPath $StaticProof | ConvertFrom-Json -AsHashtable
$sourceFiles = @($inventoryData.get_Item('files').GetEnumerator() | Sort-Object Key)
if ($producer.get_Item('status') -cne
        'native-NLS-component-built-upstream-checked-consumer-proof-pending' -or
    $producer.get_Item('profile') -cne 'iconv-full' -or
    $producer.get_Item('nls_enabled') -ne $true -or
    $producer.get_Item('process').get_Item('passed') -ne $true -or
    $producer.get_Item('process').get_Item('created_processes') -ne
        $producer.get_Item('process').get_Item('observed_processes') -or
    $shared.get_Item('status') -cne 'native-NLS-API-loaded-modules-passed' -or
    $shared.get_Item('kind') -cne 'iconv' -or
    $shared.get_Item('linkage') -cne 'shared' -or
    $shared.get_Item('stage_manifest_sha256') -cne $inventoryPin -or
    $static.get_Item('status') -cne 'native-NLS-API-loaded-modules-passed' -or
    $static.get_Item('kind') -cne 'iconv' -or
    $static.get_Item('linkage') -cne 'static' -or
    $static.get_Item('stage_manifest_sha256') -cne $inventoryPin -or
    $sourceFiles.Count -ne 65) {
    throw 'The supplied libiconv evidence is not the complete qualified stage.'
}
foreach ($entry in $sourceFiles) {
    Assert-Hash (
        Join-Path $Stage $entry.Key.Replace('/', '\')
    ) $entry.Value.get_Item('sha256') "Qualified libiconv payload $($entry.Key)"
}

$runtimeEntries = @($sourceFiles | Where-Object {
    $_.Key -like 'usr/share/*' -or
    $_.Key -in @('usr/bin/msys-iconv-2.dll', 'usr/bin/msys-charset-1.dll')
})
if ($runtimeEntries.Count -ne 55) {
    throw "Pinned libiconv split ownership changed: $($runtimeEntries.Count)"
}

New-Item -ItemType Directory -Path (
    $output,
    "$output\recipe\payload",
    "$output\packages",
    "$output\readback",
    "$output\readback-runtime\usr\bin",
    "$output\readback-runtime\tmp",
    "$output\consumer"
) | Out-Null
foreach ($entry in $runtimeEntries) {
    $destination = Join-Path "$output\recipe\payload" $entry.Key.Replace('/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath (
        Join-Path $Stage $entry.Key.Replace('/', '\')
    ) -Destination $destination
    Assert-Hash $destination $entry.Value.get_Item('sha256') "Copied libiconv payload $($entry.Key)"
}

$hashLines = $runtimeEntries | ForEach-Object {
    "$($_.Value.get_Item('sha256'))  payload/$($_.Key)"
}
[IO.File]::WriteAllText(
    "$output\recipe\payload-files.sha256",
    ($hashLines -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)
& "$env:SystemRoot\System32\tar.exe" -cf "$output\recipe\payload.tar" `
    -C "$output\recipe" payload
if ($LASTEXITCODE -ne 0) {
    throw 'Could not archive the qualified libiconv payload.'
}
$template = Join-Path $PSScriptRoot '..\native-packaging\libiconv\PKGBUILD.in'
$recipe = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
$recipe = $recipe.Replace('@PAYLOAD_SHA256@', (Get-Hash "$output\recipe\payload.tar"))
$recipe = $recipe.Replace('@FILES_SHA256@', (Get-Hash "$output\recipe\payload-files.sha256"))
[IO.File]::WriteAllText("$output\recipe\PKGBUILD", $recipe, [Text.UTF8Encoding]::new($false))

$bash = "$BootstrapRoot\usr\bin\bash.exe"
$msysOutput = Convert-ToMsysPath $output
$msysConfig = Convert-ToMsysPath $MakepkgConfig
$msysWrapper = Convert-ToMsysPath (Join-Path $CompressionPolicyRoot 'with-makepkg-compression.sh')
$oldPath = $env:PATH
try {
    $env:PATH = Split-Path -Parent $bash
    $command = @"
set -euo pipefail
export PATH=/usr/bin
export PKGDEST='$msysOutput/packages'
export BUILDDIR='$msysOutput/build'
export LOGDEST='$msysOutput/logs'
export WOARM64_JOBS=1
cd '$msysOutput/recipe'
/usr/bin/bash '$msysWrapper' /usr/bin/makepkg --config '$msysConfig' --check --cleanbuild --log --force --noconfirm
"@
    & $bash --noprofile --norc -c $command | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "makepkg failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PATH = $oldPath
}

$archive = @(Get-ChildItem "$output\packages" -File -Filter '*.pkg.tar.zst')
if ($archive.Count -ne 1) {
    throw "Expected one libiconv package archive, found $($archive.Count)"
}
$pkginfo = (& tar -xOf $archive[0].FullName '.PKGINFO') -join "`n"
foreach ($line in @(
    'pkgname = libiconv',
    'pkgver = 1.19-1',
    'depend = gcc-libs',
    'license = spdx:GPL-3.0-only AND LGPL-2.1-only'
)) {
    if ($pkginfo -notmatch [regex]::Escape($line)) {
        throw "libiconv .PKGINFO is missing: $line"
    }
}
& tar -xf $archive[0].FullName -C "$output\readback"
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract packaged libiconv.'
}
foreach ($entry in $runtimeEntries) {
    $relative = [string]$entry.Key
    if ($relative -like 'usr/share/man/*') {
        Assert-GzipPayloadHash (
            Join-Path "$output\readback" (($relative + '.gz').Replace('/', '\'))
        ) $entry.Value.get_Item('sha256')
    }
    else {
        Assert-Hash (
            Join-Path "$output\readback" $relative.Replace('/', '\')
        ) $entry.Value.get_Item('sha256') "Packaged libiconv payload $relative"
    }
}

$packagedIconv = "$output\readback\usr\bin\msys-iconv-2.dll"
$packagedCharset = "$output\readback\usr\bin\msys-charset-1.dll"
Assert-Hash $packagedIconv $iconvPin 'Packaged libiconv DLL'
Assert-Hash $packagedCharset $charsetPin 'Packaged libcharset DLL'
Assert-Hash $RuntimeDll $runtimePin 'Current d70 runtime'
$strings = Join-Path $ToolchainBin 'aarch64-pc-cygwin-strings.exe'
$blockedPattern = '/msys64/usr/|/mingwarm64/bin|/mingwarm64/etc|/mingwarm64/share|/mingwarm64/lib/tcl'
foreach ($dll in $packagedIconv, $packagedCharset) {
    if (@(& $strings -a $dll | Select-String -Pattern $blockedPattern).Count -ne 0) {
        throw "Packaged libiconv runtime contains a blocked operational path: $dll"
    }
}

$dependencyBin = "$output\readback-runtime\usr\bin"
Copy-Item -LiteralPath $RuntimeDll, $packagedIconv, $packagedCharset -Destination $dependencyBin
$source = @'
#include <iconv.h>
#include <localcharset.h>
#include <stdio.h>
#include <string.h>
int main(void) {
  char input[] = "A";
  char output[8] = {0};
  char *inbuf = input;
  char *outbuf = output;
  size_t inleft = 1;
  size_t outleft = sizeof output;
  iconv_t cd = iconv_open("UTF-16LE", "UTF-8");
  if (cd == (iconv_t)-1) return 10;
  if (iconv(cd, &inbuf, &inleft, &outbuf, &outleft) == (size_t)-1) return 11;
  if (iconv_close(cd) != 0) return 12;
  if ((unsigned char)output[0] != 0x41 || output[1] != 0) return 13;
  if (locale_charset() == NULL) return 14;
  puts("provider-libiconv-ok");
  return 0;
}
'@
[IO.File]::WriteAllText("$output\consumer\iconv.c", $source, [Text.UTF8Encoding]::new($false))
$consumer = "$dependencyBin\libiconv-consumer.exe"
& (Join-Path $ToolchainBin 'aarch64-pc-cygwin-gcc.exe') '-O2' '-Werror' `
    '-Wl,--no-insert-timestamp' "-I$(Join-Path $Stage 'usr\include')" `
    "$output\consumer\iconv.c" (Join-Path $Stage 'usr\lib\libcharset.dll.a') `
    (Join-Path $Stage 'usr\lib\libiconv.dll.a') '-o' $consumer
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to link the current-d70 libiconv consumer.'
}

$oldPath = $env:PATH
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldTmpdir = $env:TMPDIR
try {
    $env:PATH = "$dependencyBin;C:\Windows\System32"
    $env:TEMP = "$output\readback-runtime\tmp"
    $env:TMP = $env:TEMP
    $env:TMPDIR = $env:TEMP
    $consumerOutput = @(& $consumer 2>&1)
    if ($LASTEXITCODE -ne 0 -or
        ($consumerOutput -join "`n").Trim() -ne 'provider-libiconv-ok') {
        throw "Current-d70 libiconv consumer failed: $($consumerOutput -join "`n")"
    }
}
finally {
    $env:PATH = $oldPath
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:TMPDIR = $oldTmpdir
}

$package = [ordered]@{
    name = 'libiconv'
    path = $archive[0].FullName
    sha256 = Get-Hash $archive[0].FullName
}
$export = "$output\export.json"
[ordered]@{
    schema = 1
    status = 'admitted-qualified-current-d70-native-msys-libiconv-exported'
    provider = 'native-msys-libiconv'
    version = 'v1'
    runtime_cohort = [ordered]@{
        sha256 = $runtimePin
        compatibility_with_current_d70_runtime_claimed = $true
    }
    packages = @($package)
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $export -Encoding utf8NoBOM

$handoff = "$output\handoff.json"
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-msys-libiconv-packaged'
    provider_export = [ordered]@{ path = $export; sha256 = Get-Hash $export }
    source = [ordered]@{
        stage = [IO.Path]::GetFullPath($Stage)
        inventory = [ordered]@{ path = [IO.Path]::GetFullPath($Inventory); sha256 = $inventoryPin }
        producer_result = [ordered]@{ path = [IO.Path]::GetFullPath($ProducerResult); sha256 = $producerPin }
        shared_proof = [ordered]@{ path = [IO.Path]::GetFullPath($SharedProof); sha256 = $sharedProofPin }
        static_proof = [ordered]@{ path = [IO.Path]::GetFullPath($StaticProof); sha256 = $staticProofPin }
        pinned_recipe = [ordered]@{ path = [IO.Path]::GetFullPath($PinnedRecipe); sha256 = $recipePin }
    }
    ownership = [ordered]@{
        source_stage_files_verified = $sourceFiles.Count
        packaged_files = $runtimeEntries.Count
        package = 'libiconv'
        iconv_package_admitted = $false
        libiconv_devel_package_admitted = $false
    }
    exact_binary_hashes = [ordered]@{
        'msys-iconv-2.dll' = $iconvPin
        'msys-charset-1.dll' = $charsetPin
    }
    readback = [ordered]@{
        consumer = $consumerOutput
        runtime_sha256 = $runtimePin
        blocked_operational_paths = @()
    }
    withheld_iconv_tool = [ordered]@{
        path = 'usr/bin/iconv.exe'
        sha256 = $iconvExePin
        blocking_operational_path = (
            'C:/ag-bash-e138-01/host-bootstrap-02/msys64/usr/share/locale'
        )
        producer_need = (
            'Provide a fresh qualified iconv.exe built with canonical ' +
            '--localedir=/usr/share/locale; do not repackage or rename the existing bytes.'
        )
    }
    package = $package
    controls = [ordered]@{
        source_rebuilt_by_intake = $false
        producer_stage_modified = $false
        dll_bytes_modified = $false
        private_iconv_executable_admitted = $false
        development_metadata_claimed = $false
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $handoff -Encoding utf8NoBOM

Get-Item -LiteralPath $archive[0].FullName, $export, $handoff |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
