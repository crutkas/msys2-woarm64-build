[CmdletBinding()]
param(
    [string]$Admission = 'C:\ag-utils-e138-01\native-utilities-06\admission.json',
    [string]$Manifest = 'C:\ag-utils-e138-01\native-utilities-06\native-bash-test-utilities.manifest.json',
    [string]$Stage = 'C:\ag-utils-e138-01\native-utilities-06\stage',
    [string]$UtilityExport = 'C:\ap11-native-provider-intake\qualified-utilities-v1\export.json',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\qualified-utility-libraries-v1',
    [string]$Bash = 'C:\ag-readline-e138-01\bootstrap\msys64\usr\bin\bash.exe',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedAdmissionHash = 'bbc0046280991ae12f14298c8886faf78706e97be3aaf98e4369702912c47445'
$expectedManifestHash = '300bda77f05606c6f49390297695d0507d769b2dc527843c746b0f6e1b72c9aa'
$expectedUtilityExportHash = '0e2cdcb4b06130289a0722a13d8694ca7630cca06776589d4fd2988a09d32866'
$expectedRuntimeHash = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$gmpSourceUrl = 'https://ftp.gnu.org/gnu/gmp/gmp-6.3.0.tar.xz'
$gmpSourceHash = 'a3c2b80201b89e68616f4ad30bc66aee4927c3ce50e33929ca819d5c43538898'

$packages = @(
    [ordered]@{
        name = 'gmp'
        version = '6.3.0'
        release = '2'
        description = 'A free library for arbitrary precision arithmetic'
        url = 'https://gmplib.org/'
        license = 'LGPL-3.0-or-later OR GPL-2.0-or-later'
        depends = @()
        files = @(
            'usr/bin/msys-gmp-10.dll',
            'usr/bin/msys-gmpxx-4.dll',
            'usr/share/info/gmp.info',
            'usr/share/info/gmp.info-1',
            'usr/share/info/gmp.info-2'
        )
        license_kind = 'gmp-source'
    },
    [ordered]@{
        name = 'mpfr'
        version = '4.2.2'
        release = '1'
        description = 'Multiple-precision floating-point library'
        url = 'https://www.mpfr.org/'
        license = 'LGPL-3.0-or-later'
        depends = @('gmp>=5.0')
        files = @(
            'usr/bin/msys-mpfr-6.dll',
            'usr/share/info/mpfr.info',
            'usr/share/doc/mpfr/**'
        )
        license_kind = 'stage'
        license_path = 'usr/share/doc/mpfr/COPYING.LESSER'
    },
    [ordered]@{
        name = 'libpcre'
        version = '8.45'
        release = '5'
        description = 'Perl-compatible regular expression runtime library'
        url = 'https://www.pcre.org/'
        license = 'BSD-3-Clause'
        depends = @('gcc-libs')
        files = @('usr/bin/msys-pcre-1.dll')
        license_kind = 'stage'
        license_path = 'usr/share/doc/pcre/LICENCE'
    }
)

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
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
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

Assert-FileHash -Path $Admission -Expected $expectedAdmissionHash
Assert-FileHash -Path $Manifest -Expected $expectedManifestHash
Assert-FileHash -Path $UtilityExport -Expected $expectedUtilityExportHash
$admissionData = Get-Content -Raw -LiteralPath $Admission | ConvertFrom-Json
if ($admissionData.status -ne 'native-bash-test-utilities-qualified' -or
    $admissionData.runtime_sha256 -ne $expectedRuntimeHash) {
    throw 'Utility admission does not match the qualified d70 stage'
}
$manifestData = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json
$manifestFiles = $manifestData.files.PSObject.Properties

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists: $OutputDirectory"
}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$sourceDirectory = Join-Path $OutputDirectory 'sources'
New-Item -ItemType Directory -Path $sourceDirectory | Out-Null
$gmpArchive = Join-Path $sourceDirectory 'gmp-6.3.0.tar.xz'
Invoke-WebRequest -Uri $gmpSourceUrl -OutFile $gmpArchive
Assert-FileHash -Path $gmpArchive -Expected $gmpSourceHash
$gmpExtract = Join-Path $sourceDirectory 'gmp'
New-Item -ItemType Directory -Path $gmpExtract | Out-Null
& tar -xf $gmpArchive -C $gmpExtract
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to extract the pinned GMP source archive'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$template = Get-Content -Raw -LiteralPath (
    Join-Path $repoRoot 'arm64-git-recovery\native-packaging\qualified-utility\PKGBUILD.in'
)
$archiveRecords = @()
$payloadManifests = @()

foreach ($package in $packages) {
    $packageRoot = Join-Path $OutputDirectory $package.name
    $payloadRoot = Join-Path $packageRoot 'payload'
    New-Item -ItemType Directory -Path $payloadRoot | Out-Null
    $selected = @($manifestFiles | Where-Object {
        $candidate = $_.Name
        @($package.files | Where-Object { $candidate -like $_ }).Count -gt 0
    })
    foreach ($entry in $selected) {
        $source = Join-Path $Stage ($entry.Name -replace '/', '\')
        Assert-FileHash -Path $source -Expected $entry.Value.sha256
        $destination = Join-Path $payloadRoot ($entry.Name -replace '/', '\')
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }

    $licenseDirectory = Join-Path $payloadRoot "usr\share\licenses\$($package.name)"
    New-Item -ItemType Directory -Force -Path $licenseDirectory | Out-Null
    if ($package.license_kind -eq 'stage') {
        $licenseEntry = $manifestFiles | Where-Object Name -eq $package.license_path
        if ($null -eq $licenseEntry) {
            throw "Qualified license is missing for $($package.name)"
        }
        $licenseSource = Join-Path $Stage ($package.license_path -replace '/', '\')
        Assert-FileHash -Path $licenseSource -Expected $licenseEntry.Value.sha256
        Copy-Item -LiteralPath $licenseSource -Destination (Join-Path $licenseDirectory 'LICENSE')
    }
    else {
        $gmpRoot = Join-Path $gmpExtract 'gmp-6.3.0'
        foreach ($name in 'COPYINGv2', 'COPYINGv3', 'COPYING.LESSERv3') {
            Copy-Item -LiteralPath (Join-Path $gmpRoot $name) -Destination $licenseDirectory
        }
    }

    $payloadRows = @(
        Get-ChildItem -LiteralPath $payloadRoot -File -Recurse | Sort-Object FullName | ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($payloadRoot.Length + 1).Replace('\', '/')
                sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
                bytes = $_.Length
            }
        }
    )
    $payloadManifestPath = Join-Path $packageRoot 'payload-manifest.json'
    [ordered]@{
        schema = 1
        package = $package.name
        version = "$($package.version)-$($package.release)"
        runtime_sha256 = $expectedRuntimeHash
        files = $payloadRows
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $payloadManifestPath -Encoding utf8NoBOM
    $payloadManifests += [ordered]@{
        package = $package.name
        path = $payloadManifestPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $payloadManifestPath).Hash.ToLowerInvariant()
        files = $payloadRows.Count
    }

    $depends = ($package.depends | ForEach-Object { "'$_'" }) -join ' '
    $pkgbuild = $template.
        Replace('@@PACKAGE_NAME@@', $package.name).
        Replace('@@PACKAGE_VERSION@@', $package.version).
        Replace('@@PACKAGE_RELEASE@@', $package.release).
        Replace('@@PACKAGE_EPOCH@@', '').
        Replace('@@PACKAGE_DESCRIPTION@@', $package.description).
        Replace('@@PACKAGE_URL@@', $package.url).
        Replace('@@PACKAGE_LICENSE@@', $package.license).
        Replace('@@PACKAGE_DEPENDS@@', $depends).
        Replace('@@PACKAGE_PROVIDES@@', '').
        Replace('@@PAYLOAD_ROOT@@', (Convert-ToMsysPath -Path $payloadRoot)).
        Replace("`r`n", "`n")
    Set-Content -LiteralPath (Join-Path $packageRoot 'PKGBUILD') -Value $pkgbuild -Encoding utf8NoBOM

    $packageOutput = Join-Path $packageRoot 'packages'
    $makepkgBuild = Join-Path $packageRoot 'makepkg-build'
    New-Item -ItemType Directory -Path $packageOutput, $makepkgBuild | Out-Null
    $oldPath = $env:PATH
    try {
        $env:PATH = Split-Path -Parent $Bash
        $command = @"
export PKGDEST='$(Convert-ToMsysPath -Path $packageOutput)'
export BUILDDIR='$(Convert-ToMsysPath -Path $makepkgBuild)'
cd '$(Convert-ToMsysPath -Path $packageRoot)'
/usr/bin/makepkg --config '$(Convert-ToMsysPath -Path $MakepkgConfig)' --force --cleanbuild --noconfirm
"@
        & $Bash --noprofile --norc -c ($command.Replace("`r`n", "`n")) | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "makepkg failed for $($package.name) with exit code $LASTEXITCODE"
        }
    }
    finally {
        $env:PATH = $oldPath
    }
    $archive = Get-ChildItem -LiteralPath $packageOutput -File -Filter '*.pkg.tar.zst'
    if (@($archive).Count -ne 1) {
        throw "Expected one $($package.name) archive, found $(@($archive).Count)"
    }
    $archiveRecords += [ordered]@{
        path = $archive.FullName
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive.FullName).Hash.ToLowerInvariant()
    }
}

$readbackRoot = Join-Path $OutputDirectory 'native-readback'
$readbackBin = Join-Path $readbackRoot 'usr\bin'
New-Item -ItemType Directory -Force -Path $readbackBin | Out-Null
$utilityData = Get-Content -Raw -LiteralPath $UtilityExport | ConvertFrom-Json
foreach ($name in 'gawk', 'grep') {
    $row = $utilityData.packages | Where-Object { $_.path -match "\\$name-" }
    & tar -xf $row.path -C $readbackRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract $name for native library readback"
    }
}
foreach ($record in $archiveRecords) {
    & tar -xf $record.path -C $readbackRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract $($record.path) for native library readback"
    }
}
foreach ($dll in @(
    'msys-2.0.dll',
    'msys-iconv-2.dll',
    'msys-intl-8.dll',
    'msys-ncursesw6.dll',
    'msys-readline8.dll'
)) {
    Copy-Item -LiteralPath (Join-Path $Stage "usr\bin\$dll") -Destination $readbackBin
}

$probe = Join-Path $readbackRoot 'probe.txt'
[IO.File]::WriteAllText($probe, "first`nneedle`nthird`n", [Text.UTF8Encoding]::new($false))
$oldPath = $env:PATH
try {
    $env:PATH = "$readbackBin;$oldPath"
    $gawkOutput = @(& (Join-Path $readbackBin 'gawk.exe') 'BEGIN { print 6 * 7 }' 2>&1)
    if ($LASTEXITCODE -ne 0 -or ($gawkOutput -join "`n").Trim() -ne '42') {
        throw "GMP/MPFR native readback failed: $($gawkOutput -join "`n")"
    }
    $grepOutput = @(& (Join-Path $readbackBin 'grep.exe') 'needle' $probe 2>&1)
    if ($LASTEXITCODE -ne 0 -or ($grepOutput -join "`n").Trim() -ne 'needle') {
        throw "libpcre native readback failed: $($grepOutput -join "`n")"
    }
}
finally {
    $env:PATH = $oldPath
}

$export = [ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-utility-libraries-exported'
    provider = 'native-msys-qualified-utility-libraries'
    version = 'v1'
    runtime_cohort = [ordered]@{
        sha256 = $expectedRuntimeHash
        compatibility_with_current_d70_runtime_claimed = $true
    }
    packages = $archiveRecords
}
$exportPath = Join-Path $OutputDirectory 'export.json'
$export | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $exportPath -Encoding utf8NoBOM

$handoff = [ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-utility-libraries'
    provider_export = [ordered]@{
        path = $exportPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $exportPath).Hash.ToLowerInvariant()
    }
    admission = [ordered]@{
        path = $Admission
        sha256 = $expectedAdmissionHash
    }
    source_manifest = [ordered]@{
        path = $Manifest
        sha256 = $expectedManifestHash
    }
    gmp_source = [ordered]@{
        url = $gmpSourceUrl
        path = $gmpArchive
        sha256 = $gmpSourceHash
        pinned_recipe = 'msys2/MSYS2-packages gmp 6.3.0-2'
    }
    payload_manifests = $payloadManifests
    native_readbacks = @(
        [ordered]@{
            packages = @('gmp', 'mpfr')
            consumer = 'gawk.exe'
            output = $gawkOutput
            native_process = $true
            host_architecture = 'arm64'
            runtime_sha256 = $expectedRuntimeHash
        },
        [ordered]@{
            packages = @('libpcre')
            consumer = 'grep.exe'
            output = $grepOutput
            native_process = $true
            host_architecture = 'arm64'
            runtime_sha256 = $expectedRuntimeHash
        }
    )
    controls = [ordered]@{
        producer_stage_hashes_verified = $true
        packaged_binary_bytes_unchanged = $true
        full_runtime_licenses_present = $true
        producer_stage_modified = $false
        shared_prefixes_modified = $false
    }
}
$handoffPath = Join-Path $OutputDirectory 'handoff.json'
$handoff | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath $exportPath, $handoffPath | Select-Object FullName, Length
