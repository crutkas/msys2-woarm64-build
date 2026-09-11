#requires -Version 7.3
[CmdletBinding()]
param(
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\gettext-runtime-relocatable-v2',
    [string]$Stage = 'C:\ag-bash-e138-01\gettext-runtime-relocatable-03\stage',
    [string]$Inventory = 'C:\ag-bash-e138-01\gettext-runtime-relocatable-03\stage.inventory.json',
    [string]$ProducerResult = 'C:\ag-bash-e138-01\gettext-runtime-relocatable-03\result.json',
    [string]$SourceAdoption = 'C:\ag-bash-e138-01\sources\gettext-msys\adoption.json',
    [string]$SourceArchive = 'C:\ag-bash-e138-01\cache\gettext-0.22.5.tar.gz',
    [string]$BootstrapRoot = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64',
    [string]$ReadbackSdk = 'C:\ag-bash-e138-01\bash-sdk-relocatable-02\stage',
    [string]$ToolchainBin = 'C:\agtc-libs-01\sdk\bin',
    [string]$RuntimeDll = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\recipe\payload\runtime\usr\bin\msys-2.0.dll',
    [string]$GccLibs = 'C:\ap11-native-provider-intake\gcc-libs-v1\payload\usr\bin',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf',
    [string]$CompressionPolicyHandoff = 'C:\ap06-2160\compression-policy-handoff-20260909-01\handoff.json',
    [string]$CompressionPolicyRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$inventoryPin = 'c89b98a0eab2f9efaa04272db5318543ed56bcf4d23d3ebd351d42621a64dd2b'
$producerPin = '7b50e53e8f389201c22d36420f381e0e82fc99ad1923eb78e274ca97b44fb32e'
$adoptionPin = 'f7e2f10bb5008f1b066a79b67afc27a99722e9d576e85a349c153cd46ccade88'
$sourceArchivePin = 'ec1705b1e969b83a9f073144ec806151db88127f5e40fe5a94cb6c8fa48996a0'
$runtimePin = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$iconvPin = '86aa5600dd67dc8985ed4f218420549ed46539ae739dbbeaf11f68d0c1db4215'
$intlPin = '44c50b20168751f4b5a0107a7b85c7e9ff9565062b1be2b86c65eb5beeaa339c'
$asprintfPin = '57103e55441a2853b4e7b4066e78c5ffa7ebe140b11064a8554c5be26d559b26'
$licensePin = '3fe5361f24b7c49ba12911c08f5a33f9cb18871d95d9fb881f5b8a4793e04288'

if (-not $CompressionPolicyRoot) {
    $CompressionPolicyRoot = Join-Path (
        Split-Path -Parent $PSScriptRoot
    ) 'native-packaging\compression-policy'
}

function Get-Sha256 {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Pin {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected,
        [Parameter(Mandatory)][string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
    $actual = Get-Sha256 $Path
    if ($actual -cne $Expected) {
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

function Get-Imports {
    param([Parameter(Mandatory)][string]$Path)

    return @(
        & (Join-Path $ToolchainBin 'aarch64-pc-cygwin-objdump.exe') -p $Path |
            Select-String 'DLL Name: (.+)$' |
            ForEach-Object { $_.Matches[0].Groups[1].Value } |
            Sort-Object -Unique
    )
}

$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw "Output must be new: $output"
}

Assert-Pin $Inventory $inventoryPin 'Qualified gettext runtime inventory'
Assert-Pin $ProducerResult $producerPin 'Qualified gettext runtime producer result'
Assert-Pin $SourceAdoption $adoptionPin 'Gettext source adoption'
Assert-Pin $SourceArchive $sourceArchivePin 'Pinned gettext source archive'
Assert-Pin $CompressionPolicyHandoff (
    '406b2632c55b136be368d12609c55649a98b1d852d7f65b506149523b9ddd9dc'
) 'Compression policy handoff'
foreach ($entry in ([ordered]@{
    'makepkg-compression-policy.sh' = 'a2e161767e4d9dea88768eac448170ec53981acb05efe06ad7064e2ddafc62d1'
    'makepkg-compression.sh' = '41bc1d98d912ddbca60f1a6369be0ee9f97959787dcf499eaee814a5f01406d6'
    'with-makepkg-compression.sh' = 'b3324cc71bb44ad74ed00064e420db90158fb9aa2da022667a7fe6eaa3e8571c'
}).GetEnumerator()) {
    Assert-Pin (Join-Path $CompressionPolicyRoot $entry.Key) $entry.Value "Compression policy $($entry.Key)"
}

$inventoryData = Get-Content -Raw -LiteralPath $Inventory | ConvertFrom-Json -AsHashtable
$producer = Get-Content -Raw -LiteralPath $ProducerResult | ConvertFrom-Json -AsHashtable
$adoption = Get-Content -Raw -LiteralPath $SourceAdoption | ConvertFrom-Json -AsHashtable
if ($producer.get_Item('status') -cne 'qualified-relocatable-gettext-runtime' -or
    $producer.get_Item('stage_inventory_sha256') -cne $inventoryPin -or
    $producer.get_Item('parent_raw_exit') -ne 0 -or
    $producer.get_Item('created') -ne $producer.get_Item('observed') -or
    $producer.get_Item('unrelayed_high_exits') -ne 0 -or
    $producer.get_Item('intl_dll_sha256') -cne $intlPin -or
    $inventoryData.get_Item('status') -cne 'sealed-relocatable-native-arm64-gettext-runtime' -or
    $inventoryData.get_Item('file_count') -ne 101 -or
    $inventoryData.get_Item('arm64_pe_count') -ne 5 -or
    $inventoryData.get_Item('relocation').get_Item('canonical') -cne '/usr/share/locale' -or
    @($inventoryData.get_Item('relocation').get_Item('forbidden_hits')).Count -ne 0 -or
    $adoption.get_Item('source_manifest_sha256') -cne
        $inventoryData.get_Item('source_manifest_sha256') -or
    $adoption.get_Item('source_unchanged') -ne $true) {
    throw 'The supplied gettext runtime evidence is not the qualified relocatable result.'
}
Assert-Pin $inventoryData.get_Item('recipe').get_Item('path') (
    $inventoryData.get_Item('recipe').get_Item('sha256')
) 'Qualified gettext runtime recipe'

$sourceFiles = @($inventoryData.get_Item('files').GetEnumerator() | Sort-Object Key)
if ($sourceFiles.Count -ne 101) {
    throw "Qualified gettext runtime inventory changed file count: $($sourceFiles.Count)"
}
foreach ($entry in $sourceFiles) {
    Assert-Pin (
        Join-Path $Stage $entry.Key.Replace('/', '\')
    ) $entry.Value.get_Item('sha256') "Qualified gettext payload $($entry.Key)"
}

New-Item -ItemType Directory -Path (
    $output,
    "$output\recipe\payload\usr\bin",
    "$output\recipe\payload\licenses\libintl",
    "$output\recipe\payload\licenses\libasprintf",
    "$output\packages",
    "$output\readback",
    "$output\readback-runtime\usr\bin",
    "$output\readback-runtime\tmp",
    "$output\consumer"
) | Out-Null

Copy-Item -LiteralPath (Join-Path $Stage 'usr\bin\msys-intl-8.dll') `
    -Destination "$output\recipe\payload\usr\bin\msys-intl-8.dll"
Copy-Item -LiteralPath (Join-Path $Stage 'usr\bin\msys-asprintf-0.dll') `
    -Destination "$output\recipe\payload\usr\bin\msys-asprintf-0.dll"
Assert-Pin "$output\recipe\payload\usr\bin\msys-intl-8.dll" $intlPin 'Copied libintl DLL'
Assert-Pin "$output\recipe\payload\usr\bin\msys-asprintf-0.dll" $asprintfPin 'Copied libasprintf DLL'

$licenseExtract = "$output\license-source"
New-Item -ItemType Directory -Path $licenseExtract | Out-Null
& "$env:SystemRoot\System32\tar.exe" -xf $SourceArchive -C $licenseExtract `
    'gettext-0.22.5/gettext-runtime/intl/COPYING.LIB' `
    'gettext-0.22.5/gettext-runtime/libasprintf/COPYING.LIB'
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract the pinned gettext runtime licenses.'
}
$intlLicense = "$licenseExtract\gettext-0.22.5\gettext-runtime\intl\COPYING.LIB"
$asprintfLicense = "$licenseExtract\gettext-0.22.5\gettext-runtime\libasprintf\COPYING.LIB"
Assert-Pin $intlLicense $licensePin 'libintl license'
Assert-Pin $asprintfLicense $licensePin 'libasprintf license'
Copy-Item -LiteralPath $intlLicense -Destination "$output\recipe\payload\licenses\libintl\COPYING.LIB"
Copy-Item -LiteralPath $asprintfLicense -Destination "$output\recipe\payload\licenses\libasprintf\COPYING.LIB"

$payloadFiles = @(
    Get-ChildItem "$output\recipe\payload" -Recurse -File | Sort-Object FullName
)
$hashLines = $payloadFiles | ForEach-Object {
    $relative = $_.FullName.Substring("$output\recipe\".Length).Replace('\', '/')
    "$(Get-Sha256 $_.FullName)  $relative"
}
[IO.File]::WriteAllText(
    "$output\recipe\payload-files.sha256",
    ($hashLines -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)
& "$env:SystemRoot\System32\tar.exe" -cf "$output\recipe\payload.tar" -C "$output\recipe" payload
if ($LASTEXITCODE -ne 0) {
    throw 'Could not archive the qualified gettext runtime payload.'
}

$template = Join-Path $PSScriptRoot '..\native-packaging\gettext-runtime\PKGBUILD.in'
$recipe = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
$recipe = $recipe.Replace('@PAYLOAD_SHA256@', (Get-Sha256 "$output\recipe\payload.tar"))
$recipe = $recipe.Replace('@FILES_SHA256@', (Get-Sha256 "$output\recipe\payload-files.sha256"))
if ($recipe.Contains('@')) {
    throw 'Unresolved gettext package recipe token.'
}
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
export SRCDEST='$msysOutput/sources'
export SRCPKGDEST='$msysOutput/source-packages'
export LOGDEST='$msysOutput/logs'
export BUILDDIR='$msysOutput/build'
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

$archives = @(Get-ChildItem "$output\packages" -File -Filter '*.pkg.tar.zst' | Sort-Object Name)
if ($archives.Count -ne 2) {
    throw "Expected two gettext runtime package archives, found $($archives.Count)."
}
$archiveByName = @{}
foreach ($archive in $archives) {
    $pkginfo = (& tar -xOf $archive.FullName '.PKGINFO') -join "`n"
    $nameLine = @($pkginfo -split "`n" | Where-Object { $_ -like 'pkgname = *' })
    if ($nameLine.Count -ne 1) {
        throw "Package has no unique pkgname: $($archive.FullName)"
    }
    $name = $nameLine[0].Substring('pkgname = '.Length)
    $root = "$output\readback\$name"
    New-Item -ItemType Directory -Path $root | Out-Null
    & tar -xf $archive.FullName -C $root
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract package: $($archive.FullName)"
    }
    $archiveByName[$name] = [ordered]@{
        file = $archive
        root = $root
        pkginfo = $pkginfo
    }
}

$metadata = [ordered]@{
    libintl = @(
        'pkgname = libintl',
        'pkgver = 0.22.5-1',
        'depend = gcc-libs',
        'depend = libiconv',
        'license = spdx:LGPL-2.1-or-later'
    )
    libasprintf = @(
        'pkgname = libasprintf',
        'pkgver = 0.22.5-1',
        'depend = gcc-libs',
        'license = spdx:LGPL-2.1-or-later'
    )
}
foreach ($name in $metadata.Keys) {
    if (-not $archiveByName.ContainsKey($name)) {
        throw "Missing gettext runtime split archive: $name"
    }
    foreach ($line in $metadata[$name]) {
        if ($archiveByName[$name].pkginfo -notmatch [regex]::Escape($line)) {
            throw "$name .PKGINFO is missing: $line"
        }
    }
}

$intlDll = Join-Path $archiveByName.libintl.root 'usr\bin\msys-intl-8.dll'
$asprintfDll = Join-Path $archiveByName.libasprintf.root 'usr\bin\msys-asprintf-0.dll'
Assert-Pin $intlDll $intlPin 'Packaged libintl DLL'
Assert-Pin $asprintfDll $asprintfPin 'Packaged libasprintf DLL'
Assert-Pin (
    Join-Path $archiveByName.libintl.root 'usr\share\licenses\libintl\COPYING.LIB'
) $licensePin 'Packaged libintl license'
Assert-Pin (
    Join-Path $archiveByName.libasprintf.root 'usr\share\licenses\libasprintf\COPYING.LIB'
) $licensePin 'Packaged libasprintf license'

$imports = [ordered]@{
    libintl = Get-Imports $intlDll
    libasprintf = Get-Imports $asprintfDll
}
if (Compare-Object $imports.libintl @('KERNEL32.dll', 'msys-2.0.dll', 'msys-iconv-2.dll') -SyncWindow 0) {
    throw "Unexpected libintl imports: $($imports.libintl -join ', ')"
}
if (Compare-Object $imports.libasprintf @('KERNEL32.dll', 'msys-2.0.dll') -SyncWindow 0) {
    throw "Unexpected libasprintf imports: $($imports.libasprintf -join ', ')"
}

$strings = Join-Path $ToolchainBin 'aarch64-pc-cygwin-strings.exe'
$blockedPattern = '/msys64/usr/|/mingwarm64/bin|/mingwarm64/etc|/mingwarm64/share|/mingwarm64/lib/tcl'
foreach ($dll in $intlDll, $asprintfDll) {
    $blocked = @(& $strings -a $dll | Select-String -Pattern $blockedPattern)
    if ($blocked.Count -ne 0) {
        throw "Packaged gettext runtime contains blocked operational paths: $dll"
    }
}
$canonicalLocale = @(& $strings -a $intlDll | Select-String -SimpleMatch '/usr/share/locale')
if ($canonicalLocale.Count -eq 0) {
    throw 'Packaged libintl does not contain the canonical locale path.'
}

$dependencyBin = "$output\readback-runtime\usr\bin"
Assert-Pin $RuntimeDll $runtimePin 'Current d70 runtime'
$iconvDll = Join-Path $ReadbackSdk 'usr\bin\msys-iconv-2.dll'
Assert-Pin $iconvDll $iconvPin 'Qualified libiconv dependency'
Copy-Item -LiteralPath $RuntimeDll, $iconvDll, $intlDll, $asprintfDll -Destination $dependencyBin
foreach ($name in 'msys-gcc_s-seh-1.dll', 'msys-stdc++-6.dll') {
    Copy-Item -LiteralPath (Join-Path $GccLibs $name) -Destination $dependencyBin
}

$intlSource = @'
#include <libintl.h>
#include <stdio.h>
#include <string.h>
int main(void) {
  const char *value = gettext("provider-intl-ok");
  puts(value);
  return strcmp(value, "provider-intl-ok") != 0;
}
'@
$asprintfSource = @'
#include <autosprintf.h>
#include <iostream>
int main() {
  std::cout << gnu::autosprintf("provider-asprintf-%d", 42) << "\n";
  return 0;
}
'@
[IO.File]::WriteAllText("$output\consumer\intl.c", $intlSource, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText("$output\consumer\asprintf.cc", $asprintfSource, [Text.UTF8Encoding]::new($false))
$gcc = Join-Path $ToolchainBin 'aarch64-pc-cygwin-gcc.exe'
$gxx = Join-Path $ToolchainBin 'aarch64-pc-cygwin-g++.exe'
$include = Join-Path $Stage 'usr\include'
$library = Join-Path $Stage 'usr\lib'
$iconvLibrary = Join-Path $ReadbackSdk 'usr\lib'
$intlExe = "$dependencyBin\intl-consumer.exe"
$asprintfExe = "$dependencyBin\asprintf-consumer.exe"
& $gcc '-O2' '-Werror' '-Wl,--no-insert-timestamp' "-I$include" "$output\consumer\intl.c" `
    "-L$library" "-L$iconvLibrary" '-lintl' '-liconv' '-o' $intlExe
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to link the current-d70 libintl consumer.'
}
& $gxx '-O2' '-Werror' '-Wl,--no-insert-timestamp' "-I$include" "$output\consumer\asprintf.cc" `
    "-L$library" '-lasprintf' '-o' $asprintfExe
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to link the current-d70 libasprintf consumer.'
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
    $intlOutput = @(& $intlExe 2>&1)
    if ($LASTEXITCODE -ne 0 -or ($intlOutput -join "`n").Trim() -ne 'provider-intl-ok') {
        throw "Current-d70 libintl consumer failed: $($intlOutput -join "`n")"
    }
    $asprintfOutput = @(& $asprintfExe 2>&1)
    if ($LASTEXITCODE -ne 0 -or
        ($asprintfOutput -join "`n").Trim() -ne 'provider-asprintf-42') {
        throw "Current-d70 libasprintf consumer failed: $($asprintfOutput -join "`n")"
    }
}
finally {
    $env:PATH = $oldPath
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:TMPDIR = $oldTmpdir
}

$packages = @(
    foreach ($name in 'libintl', 'libasprintf') {
        [ordered]@{
            name = $name
            path = $archiveByName[$name].file.FullName
            sha256 = Get-Sha256 $archiveByName[$name].file.FullName
        }
    }
)
$export = "$output\export.json"
[ordered]@{
    schema = 1
    status = 'admitted-qualified-current-d70-native-msys-gettext-runtime-exported'
    provider = 'native-msys-gettext-runtime'
    version = 'v1'
    runtime_cohort = [ordered]@{
        sha256 = $runtimePin
        compatibility_with_current_d70_runtime_claimed = $true
    }
    packages = $packages
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $export -Encoding utf8NoBOM

$handoff = "$output\handoff.json"
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-msys-gettext-runtime-packaged'
    provider_export = [ordered]@{ path = $export; sha256 = Get-Sha256 $export }
    source = [ordered]@{
        stage = [IO.Path]::GetFullPath($Stage)
        inventory = [ordered]@{ path = [IO.Path]::GetFullPath($Inventory); sha256 = $inventoryPin }
        producer_result = [ordered]@{ path = [IO.Path]::GetFullPath($ProducerResult); sha256 = $producerPin }
        adoption = [ordered]@{ path = [IO.Path]::GetFullPath($SourceAdoption); sha256 = $adoptionPin }
        archive = [ordered]@{ path = [IO.Path]::GetFullPath($SourceArchive); sha256 = $sourceArchivePin }
        version = '0.22.5-1'
    }
    ownership = [ordered]@{
        source_stage_files_verified = $sourceFiles.Count
        packaged_stage_files = 2
        package_added_license_files = 2
        unshipped_stage_files = $sourceFiles.Count - 2
        libintl = @('usr/bin/msys-intl-8.dll', 'usr/share/licenses/libintl/COPYING.LIB')
        libasprintf = @('usr/bin/msys-asprintf-0.dll', 'usr/share/licenses/libasprintf/COPYING.LIB')
        gettext_tools_devel_docs_admitted = $false
    }
    exact_binary_hashes = [ordered]@{
        'msys-intl-8.dll' = $intlPin
        'msys-asprintf-0.dll' = $asprintfPin
    }
    readback = [ordered]@{
        imports = $imports
        canonical_locale = '/usr/share/locale'
        blocked_operational_paths = @()
        libintl_consumer = $intlOutput
        libasprintf_consumer = $asprintfOutput
        runtime_sha256 = $runtimePin
        iconv_sha256 = $iconvPin
    }
    packages = $packages
    controls = [ordered]@{
        source_rebuilt_by_intake = $false
        producer_stage_modified = $false
        dll_bytes_modified = $false
        unrelated_gettext_payload_claimed = $false
        revoked_mingw_gettext_archive_readmitted = $false
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $handoff -Encoding utf8NoBOM

Get-Item -LiteralPath @($packages.path + @($export, $handoff)) |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Sha256 $_.FullName }}
