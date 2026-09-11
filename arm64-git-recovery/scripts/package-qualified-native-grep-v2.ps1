[CmdletBinding()]
param(
    [string]$SourceRoot = 'C:\ap11-native-provider-intake\qualified-utilities-v1\grep',
    [string]$DependencyStage = 'C:\ag-utils-e138-01\native-utilities-06\stage',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\qualified-grep-v4',
    [string]$Bash = 'C:\ag-readline-e138-01\bootstrap\msys64\usr\bin\bash.exe',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf',
    [string]$CompressionPolicyHandoff = 'C:\ap06-2160\compression-policy-handoff-20260909-01\handoff.json',
    [string]$CompressionPolicyRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$runtimeHash = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$sourceManifestHash = '9b69aec1c40919880b3b14ea7046c04862f320a1a197cdff21077535a5516df5'
$sourceArchiveHash = '5e55eb0a1cfadf6c16e6c0be9d52ed5ccbf710df35c660ee75a01286a6b47c59'
$grepBinaryHash = 'b3782095e266bc620dde3dddecab39ac5882bc43e3eaa6d9b48791ccec06b64a'
if (-not $CompressionPolicyRoot) {
    $CompressionPolicyRoot = Join-Path (
        Split-Path -Parent $PSScriptRoot
    ) 'native-packaging\compression-policy'
}

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    $actual = Get-Hash $Path
    if ($actual -ne $Expected) {
        throw "Hash mismatch for ${Path}: expected $Expected, got $actual"
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
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Expected
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

$sourcePayload = Join-Path $SourceRoot 'payload'
$sourceManifestPath = Join-Path $SourceRoot 'payload-manifest.json'
$sourceArchive = Join-Path $SourceRoot 'packages\grep-1~3.0-7-aarch64.pkg.tar.zst'
Assert-FileHash -Path $sourceManifestPath -Expected $sourceManifestHash
Assert-FileHash -Path $sourceArchive -Expected $sourceArchiveHash
Assert-FileHash -Path $CompressionPolicyHandoff -Expected (
    '406b2632c55b136be368d12609c55649a98b1d852d7f65b506149523b9ddd9dc'
)
$compressionPolicyFiles = [ordered]@{
    'makepkg-compression-policy.sh' = 'a2e161767e4d9dea88768eac448170ec53981acb05efe06ad7064e2ddafc62d1'
    'makepkg-compression.sh' = '41bc1d98d912ddbca60f1a6369be0ee9f97959787dcf499eaee814a5f01406d6'
    'with-makepkg-compression.sh' = 'b3324cc71bb44ad74ed00064e420db90158fb9aa2da022667a7fe6eaa3e8571c'
}
foreach ($policyFile in $compressionPolicyFiles.GetEnumerator()) {
    Assert-FileHash -Path (
        Join-Path $CompressionPolicyRoot $policyFile.Key
    ) -Expected $policyFile.Value
}
$manifest = Get-Content -Raw -LiteralPath $sourceManifestPath | ConvertFrom-Json
if ($manifest.package -ne 'grep' -or
    $manifest.version -ne '3.0-7' -or
    $manifest.runtime_sha256 -ne $runtimeHash) {
    throw 'Source grep payload manifest identity is invalid'
}

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Versioned output directory already exists: $OutputDirectory"
}
$payloadRoot = Join-Path $OutputDirectory 'payload'
$baselineRoot = Join-Path $OutputDirectory 'baseline-readback'
New-Item -ItemType Directory -Path $payloadRoot, $baselineRoot | Out-Null
& tar -xf $sourceArchive -C $baselineRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract original grep archive for payload comparison'
}
foreach ($entry in $manifest.files) {
    $source = Join-Path $sourcePayload ($entry.path -replace '/', '\')
    Assert-FileHash -Path $source -Expected $entry.sha256
    $destination = Join-Path $payloadRoot ($entry.path -replace '/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) |
        Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

$wrapperTransforms = @(
    [ordered]@{
        name = 'egrep'
        source_sha256 = '5fb6fffc64cea74659e50118403c6c190dac6c9cafd4bf0168a5fb2b7b027b0a'
        content = "#!/usr/bin/sh`nexec grep -E `"`$@`"`n"
    },
    [ordered]@{
        name = 'fgrep'
        source_sha256 = '3e2eb9ac0bf277c07919f69d70d9c6d481b78a74b0ad6139b00107e49cf65563'
        content = "#!/usr/bin/sh`nexec grep -F `"`$@`"`n"
    }
)
foreach ($wrapper in $wrapperTransforms) {
    $path = Join-Path $payloadRoot "usr\bin\$($wrapper.name)"
    Assert-FileHash -Path $path -Expected $wrapper.source_sha256
    [IO.File]::WriteAllText(
        $path,
        $wrapper.content,
        [Text.UTF8Encoding]::new($false)
    )
    $wrapper['package_sha256'] = Get-Hash $path
}
Assert-FileHash -Path (Join-Path $payloadRoot 'usr\bin\grep.exe') -Expected $grepBinaryHash

$packageRoot = Join-Path $OutputDirectory 'package'
New-Item -ItemType Directory -Path $packageRoot | Out-Null
$msysPayload = Convert-ToMsysPath -Path $payloadRoot
$pkgbuild = @"
pkgname=grep
pkgver=3.0
pkgrel=7
epoch=1
pkgdesc='A string search utility'
arch=('arm64')
url='https://www.gnu.org/software/grep/'
license=('spdx:GPL-3.0-or-later')
depends=('libiconv' 'libintl' 'libpcre' 'sh')

options=('!strip' '!debug' 'staticlibs')
source=()

package() {
  cp -a '$msysPayload/.' "`${pkgdir}/"
  chmod 755 "`${pkgdir}/usr/bin/egrep" "`${pkgdir}/usr/bin/fgrep"
}
"@.Replace("`r`n", "`n")
Set-Content -LiteralPath (Join-Path $packageRoot 'PKGBUILD') -Value $pkgbuild -Encoding utf8NoBOM

$packageOutput = Join-Path $packageRoot 'packages'
$makepkgBuild = Join-Path $packageRoot 'makepkg-build'
New-Item -ItemType Directory -Path $packageOutput, $makepkgBuild | Out-Null
$msysPackageRoot = Convert-ToMsysPath -Path $packageRoot
$msysPackageOutput = Convert-ToMsysPath -Path $packageOutput
$msysMakepkgBuild = Convert-ToMsysPath -Path $makepkgBuild
$msysMakepkgConfig = Convert-ToMsysPath -Path $MakepkgConfig
$msysCompressionWrapper = Convert-ToMsysPath -Path (
    Join-Path $CompressionPolicyRoot 'with-makepkg-compression.sh'
)
$oldPath = $env:PATH
try {
    $env:PATH = Split-Path -Parent $Bash
    $command = @"
export PKGDEST='$msysPackageOutput'
export BUILDDIR='$msysMakepkgBuild'
export WOARM64_JOBS=1
cd '$msysPackageRoot'
/usr/bin/bash '$msysCompressionWrapper' /usr/bin/makepkg --config '$msysMakepkgConfig' --force --cleanbuild --noconfirm
"@
    & $Bash --noprofile --norc -c ($command.Replace("`r`n", "`n")) | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "makepkg failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:PATH = $oldPath
}

$archives = @(Get-ChildItem -LiteralPath $packageOutput -File -Filter '*.pkg.tar.zst')
if ($archives.Count -ne 1) {
    throw "Expected one grep archive, found $($archives.Count)"
}
$archive = $archives[0]
$readbackRoot = Join-Path $OutputDirectory 'readback'
New-Item -ItemType Directory -Path $readbackRoot | Out-Null
& tar -xf $archive.FullName -C $readbackRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract repackaged grep archive'
}

$metadataPaths = @('.BUILDINFO', '.MTREE', '.PKGINFO')
$baselineFiles = @(
    Get-ChildItem -LiteralPath $baselineRoot -Recurse -File | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($baselineRoot.Length + 1).Replace('\', '/')
            sha256 = Get-Hash $_.FullName
        }
    } | Where-Object { $_.path -notin $metadataPaths }
)
$readbackFiles = @(
    Get-ChildItem -LiteralPath $readbackRoot -Recurse -File | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($readbackRoot.Length + 1).Replace('\', '/')
            sha256 = Get-Hash $_.FullName
        }
    } | Where-Object { $_.path -notin $metadataPaths }
)
if ($baselineFiles.Count -ne $readbackFiles.Count) {
    throw (
        "Archive payload count changed: baseline=$($baselineFiles.Count), " +
        "readback=$($readbackFiles.Count)"
    )
}
$readbackByPath = @{}
foreach ($row in $readbackFiles) {
    $readbackByPath[$row.path] = $row.sha256
}
$unchangedArchivePayload = @()
foreach ($row in $baselineFiles) {
    if (-not $readbackByPath.ContainsKey($row.path)) {
        throw "Archive payload path is missing after repack: $($row.path)"
    }
    $wrapper = $wrapperTransforms | Where-Object {
        "usr/bin/$($_.name)" -eq $row.path
    }
    $expected = if ($null -ne $wrapper) {
        $wrapper.package_sha256
    }
    else {
        $row.sha256
    }
    if ($readbackByPath[$row.path] -ne $expected) {
        throw (
            "Archive payload hash changed unexpectedly for $($row.path): " +
            "expected $expected, got $($readbackByPath[$row.path])"
        )
    }
    if ($null -eq $wrapper) {
        $unchangedArchivePayload += $row
    }
}
foreach ($wrapper in $wrapperTransforms) {
    $path = Join-Path $readbackRoot "usr\bin\$($wrapper.name)"
    Assert-FileHash -Path $path -Expected $wrapper.package_sha256
}
Assert-FileHash -Path (Join-Path $readbackRoot 'usr\bin\grep.exe') -Expected $grepBinaryHash
$pkginfo = (& tar -xOf $archive.FullName '.PKGINFO') -join "`n"
foreach ($line in @(
    'pkgname = grep',
    'pkgver = 1~3.0-7',
    'depend = libiconv',
    'depend = libintl',
    'depend = libpcre',
    'depend = sh'
)) {
    if ($pkginfo -notmatch [regex]::Escape($line)) {
        throw "Repackaged grep .PKGINFO is missing: $line"
    }
}

$probeInput = Join-Path $readbackRoot 'probe.txt'
[IO.File]::WriteAllText(
    $probeInput,
    "first`nneedle`nthird`n",
    [Text.UTF8Encoding]::new($false)
)
$oldPath = $env:PATH
try {
    $env:PATH = "$(Join-Path $readbackRoot 'usr\bin');$(Join-Path $DependencyStage 'usr\bin');C:\Windows\System32"
    $grepOutput = @(& (Join-Path $readbackRoot 'usr\bin\grep.exe') 'needle' $probeInput 2>&1)
    if ($LASTEXITCODE -ne 0 -or ($grepOutput -join "`n").Trim() -ne 'needle') {
        throw "Native grep readback failed: $($grepOutput -join "`n")"
    }
    $wrapperReadbacks = @()
    $msysReadbackBin = Convert-ToMsysPath -Path (
        Join-Path $readbackRoot 'usr\bin'
    )
    $msysDependencyBin = Convert-ToMsysPath -Path (
        Join-Path $DependencyStage 'usr\bin'
    )
    $msysProbeInput = Convert-ToMsysPath -Path $probeInput
    foreach ($wrapper in $wrapperTransforms) {
        $wrapperPath = Join-Path $readbackRoot "usr\bin\$($wrapper.name)"
        $msysWrapperPath = Convert-ToMsysPath -Path $wrapperPath
        $command = @"
PATH='${msysReadbackBin}:${msysDependencyBin}:/usr/bin' '$msysWrapperPath' needle '$msysProbeInput'
"@
        $output = @(& $Bash --noprofile --norc -c $command 2>&1)
        if ($LASTEXITCODE -ne 0 -or ($output -join "`n").Trim() -ne 'needle') {
            throw "$($wrapper.name) wrapper readback failed: $($output -join "`n")"
        }
        $wrapperReadbacks += [ordered]@{
            name = $wrapper.name
            sha256 = $wrapper.package_sha256
            output = $output
            interpreter_harness = $Bash
        }
    }
}
finally {
    $env:PATH = $oldPath
}

$payloadManifest = Join-Path $OutputDirectory 'payload-manifest.json'
[ordered]@{
    schema = 1
    package = 'grep'
    version = '1~3.0-7'
    source_archive = [ordered]@{
        path = $sourceArchive
        sha256 = $sourceArchiveHash
    }
    source_manifest = [ordered]@{
        path = $sourceManifestPath
        sha256 = $sourceManifestHash
    }
    unchanged_binary = [ordered]@{
        path = 'usr/bin/grep.exe'
        sha256 = $grepBinaryHash
    }
    wrapper_transforms = $wrapperTransforms
    unchanged_archive_payload = $unchangedArchivePayload
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $payloadManifest -Encoding utf8NoBOM

$export = Join-Path $OutputDirectory 'export.json'
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-grep-wrapper-relocation-exported'
    provider = 'native-msys-grep'
    version = 'v4'
    runtime_cohort = [ordered]@{
        sha256 = $runtimeHash
        compatibility_with_current_d70_runtime_claimed = $true
    }
    packages = @(
        [ordered]@{
            name = 'grep'
            path = $archive.FullName
            sha256 = Get-Hash $archive.FullName
        }
    )
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $export -Encoding utf8NoBOM

$handoff = Join-Path $OutputDirectory 'handoff.json'
[ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-grep-repackaged'
    provider_export = [ordered]@{
        path = $export
        sha256 = Get-Hash $export
    }
    payload_manifest = [ordered]@{
        path = $payloadManifest
        sha256 = Get-Hash $payloadManifest
    }
    package = [ordered]@{
        path = $archive.FullName
        sha256 = Get-Hash $archive.FullName
    }
    current_runtime_readback = [ordered]@{
        native_grep_sha256 = $grepBinaryHash
        native_grep_output = $grepOutput
        wrappers = $wrapperReadbacks
        runtime_sha256 = $runtimeHash
    }
    controls = [ordered]@{
        source_rebuilt = $false
        grep_binary_modified = $false
        data_payload_modified = $false
        archive_payload_hash_compared_to_original = $true
        exact_wrapper_hash_gate = $true
        only_wrapper_shebangs_changed = $true
        wrapper_dependency_remains_sh = $true
        dependency_archives_not_repackaged = $true
        compression_policy = [ordered]@{
            handoff = [ordered]@{
                path = $CompressionPolicyHandoff
                sha256 = Get-Hash $CompressionPolicyHandoff
            }
            jobs = 1
            xz_threads = 1
            zstd_single_thread = $true
            installed_makepkg_unchanged = $true
        }
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 12 |
    Set-Content -LiteralPath $handoff -Encoding utf8NoBOM

Get-Item -LiteralPath $archive.FullName, $export, $handoff |
    Select-Object FullName, Length
