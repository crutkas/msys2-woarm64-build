[CmdletBinding()]
param(
    [string]$Admission = 'C:\ag-utils-e138-01\native-utilities-06\admission.json',
    [string]$Manifest = 'C:\ag-utils-e138-01\native-utilities-06\native-bash-test-utilities.manifest.json',
    [string]$Stage = 'C:\ag-utils-e138-01\native-utilities-06\stage',
    [string]$SourceRoot = 'C:\ag-utils-e138-01\native-utilities-05\source',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\qualified-utilities-v1',
    [string]$Bash = 'C:\ag-readline-e138-01\bootstrap\msys64\usr\bin\bash.exe',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedAdmissionHash = 'bbc0046280991ae12f14298c8886faf78706e97be3aaf98e4369702912c47445'
$expectedManifestHash = '300bda77f05606c6f49390297695d0507d769b2dc527843c746b0f6e1b72c9aa'
$expectedRuntimeHash = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'

$packages = @(
    [ordered]@{
        name = 'diffutils'
        version = '3.12'
        release = '1'
        epoch = ''
        description = 'Utility programs used for creating patch files'
        url = 'https://www.gnu.org/software/diffutils'
        license = 'GPL-3.0-or-later'
        source_directory = 'diffutils-3.12'
        license_sha256 = '8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903'
        depends = @('sh', 'libiconv', 'libintl')
        provides = @()
        patterns = @(
            'usr/bin/cmp.exe', 'usr/bin/diff.exe', 'usr/bin/diff3.exe', 'usr/bin/sdiff.exe',
            'usr/share/info/diffutils.info',
            'usr/share/man/man1/cmp.1', 'usr/share/man/man1/diff.1',
            'usr/share/man/man1/diff3.1', 'usr/share/man/man1/sdiff.1',
            'usr/share/locale/*/LC_MESSAGES/diffutils.mo'
        )
        readback = 'diff.exe'
    },
    [ordered]@{
        name = 'findutils'
        version = '4.11.0'
        release = '2'
        epoch = ''
        description = 'GNU utilities to locate files'
        url = 'https://www.gnu.org/software/findutils'
        license = 'GPL-3.0-or-later'
        source_directory = 'findutils-4.11.0'
        license_sha256 = '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
        depends = @('libiconv', 'libintl')
        provides = @()
        patterns = @(
            'usr/bin/find.exe', 'usr/bin/locate.exe', 'usr/bin/updatedb', 'usr/bin/xargs.exe',
            'usr/share/info/find.info', 'usr/share/info/find-maint.info',
            'usr/share/man/man1/find.1', 'usr/share/man/man1/locate.1',
            'usr/share/man/man1/updatedb.1', 'usr/share/man/man1/xargs.1',
            'usr/share/locale/*/LC_MESSAGES/findutils.mo'
        )
        readback = 'find.exe'
    },
    [ordered]@{
        name = 'gawk'
        version = '5.4.1'
        release = '1'
        epoch = ''
        description = 'GNU version of awk'
        url = 'https://www.gnu.org/software/gawk/'
        license = 'GPL-3.0-or-later'
        source_directory = 'gawk-5.4.1'
        license_sha256 = '8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903'
        depends = @('sh', 'mpfr', 'libintl', 'libreadline')
        provides = @('awk')
        patterns = @(
            'usr/bin/awk.exe', 'usr/bin/gawk.exe', 'usr/bin/gawk-5.4.1.exe', 'usr/bin/gawkbug',
            'usr/lib/awk/*', 'usr/lib/gawk/*', 'usr/share/awk/*',
            'usr/share/info/gawk*', 'usr/share/info/pm-gawk.info',
            'usr/share/man/man1/gawk.1', 'usr/share/man/man1/gawkbug.1',
            'usr/share/locale/*/LC_MESSAGES/gawk.mo'
        )
        readback = 'gawk.exe'
    },
    [ordered]@{
        name = 'grep'
        version = '3.0'
        release = '7'
        epoch = '1'
        description = 'A string search utility'
        url = 'https://www.gnu.org/software/grep/'
        license = 'GPL-3.0-or-later'
        source_directory = 'grep-3.0'
        license_sha256 = 'ca372a7d92560b1fa9f6d832b440e8bcd62d9adfa8870c98287deab66d98310e'
        depends = @('libiconv', 'libintl', 'libpcre', 'sh')
        provides = @()
        patterns = @(
            'usr/bin/grep.exe', 'usr/bin/egrep', 'usr/bin/fgrep',
            'usr/share/info/grep.info',
            'usr/share/man/man1/grep.1', 'usr/share/man/man1/egrep.1', 'usr/share/man/man1/fgrep.1',
            'usr/share/locale/*/LC_MESSAGES/grep.mo'
        )
        readback = 'grep.exe'
    },
    [ordered]@{
        name = 'sed'
        version = '4.9'
        release = '1'
        epoch = ''
        description = 'GNU stream editor'
        url = 'https://www.gnu.org/software/sed'
        license = 'GPL-3.0-or-later'
        source_directory = 'sed-4.9'
        license_sha256 = '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
        depends = @('libintl', 'sh')
        provides = @()
        patterns = @(
            'usr/bin/sed.exe', 'usr/share/info/sed.info', 'usr/share/man/man1/sed.1',
            'usr/share/locale/*/LC_MESSAGES/sed.mo'
        )
        readback = 'sed.exe'
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
$admissionData = Get-Content -Raw -LiteralPath $Admission | ConvertFrom-Json
if ($admissionData.status -ne 'native-bash-test-utilities-qualified' -or
    $admissionData.runtime_sha256 -ne $expectedRuntimeHash -or
    $admissionData.manifest_sha256 -ne $expectedManifestHash) {
    throw 'Utility admission does not match the qualified d70 stage'
}
$manifestData = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json
$manifestFiles = @($manifestData.files.PSObject.Properties)
if ($manifestFiles.Count -ne [int]$admissionData.file_count) {
    throw "Utility manifest file count does not match admission: $($manifestFiles.Count)"
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists: $OutputDirectory"
}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$templatePath = Join-Path $repoRoot 'arm64-git-recovery\native-packaging\qualified-utility\PKGBUILD.in'
$template = Get-Content -Raw -LiteralPath $templatePath
$claimedPaths = @{}
$archiveRecords = @()
$readbacks = @()
$packageManifests = @()

foreach ($package in $packages) {
    $packageRoot = Join-Path $OutputDirectory $package.name
    $payloadRoot = Join-Path $packageRoot 'payload'
    New-Item -ItemType Directory -Path $payloadRoot | Out-Null
    $selected = @($manifestFiles | Where-Object {
        $candidate = $_.Name
        @($package.patterns | Where-Object { $candidate -like $_ }).Count -gt 0
    })
    if ($selected.Count -eq 0) {
        throw "No files selected for $($package.name)"
    }
    foreach ($entry in $selected) {
        if ($claimedPaths.ContainsKey($entry.Name)) {
            throw "$($entry.Name) is selected by both $($claimedPaths[$entry.Name]) and $($package.name)"
        }
        $claimedPaths[$entry.Name] = $package.name
        $source = Join-Path $Stage ($entry.Name -replace '/', '\')
        Assert-FileHash -Path $source -Expected $entry.Value.sha256
        $destination = Join-Path $payloadRoot ($entry.Name -replace '/', '\')
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }

    $licenseSource = Join-Path (Join-Path $SourceRoot $package.source_directory) 'COPYING'
    Assert-FileHash -Path $licenseSource -Expected $package.license_sha256
    $licenseDestination = Join-Path $payloadRoot "usr\share\licenses\$($package.name)\COPYING"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $licenseDestination) | Out-Null
    Copy-Item -LiteralPath $licenseSource -Destination $licenseDestination

    $manifestRows = @(
        Get-ChildItem -LiteralPath $payloadRoot -File -Recurse | Sort-Object FullName | ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($payloadRoot.Length + 1).Replace('\', '/')
                sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
                bytes = $_.Length
            }
        }
    )
    $packageManifestPath = Join-Path $packageRoot 'payload-manifest.json'
    [ordered]@{
        schema = 1
        package = $package.name
        version = "$($package.version)-$($package.release)"
        runtime_sha256 = $expectedRuntimeHash
        files = $manifestRows
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $packageManifestPath -Encoding utf8NoBOM
    $packageManifests += [ordered]@{
        package = $package.name
        path = $packageManifestPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $packageManifestPath).Hash.ToLowerInvariant()
        files = $manifestRows.Count
    }

    $depends = ($package.depends | ForEach-Object { "'$_'" }) -join ' '
    $provides = if ($package.provides.Count -gt 0) {
        "provides=($(($package.provides | ForEach-Object { "'$_'" }) -join ' '))"
    }
    else {
        ''
    }
    $epoch = if ($package.epoch) { "epoch=$($package.epoch)" } else { '' }
    $pkgbuild = $template.
        Replace('@@PACKAGE_NAME@@', $package.name).
        Replace('@@PACKAGE_VERSION@@', $package.version).
        Replace('@@PACKAGE_RELEASE@@', $package.release).
        Replace('@@PACKAGE_EPOCH@@', $epoch).
        Replace('@@PACKAGE_DESCRIPTION@@', $package.description).
        Replace('@@PACKAGE_URL@@', $package.url).
        Replace('@@PACKAGE_LICENSE@@', $package.license).
        Replace('@@PACKAGE_DEPENDS@@', $depends).
        Replace('@@PACKAGE_PROVIDES@@', $provides).
        Replace('@@PAYLOAD_ROOT@@', (Convert-ToMsysPath -Path $payloadRoot)).
        Replace("`r`n", "`n")
    Set-Content -LiteralPath (Join-Path $packageRoot 'PKGBUILD') -Value $pkgbuild -Encoding utf8NoBOM

    $packageOutput = Join-Path $packageRoot 'packages'
    $makepkgBuild = Join-Path $packageRoot 'makepkg-build'
    New-Item -ItemType Directory -Path $packageOutput, $makepkgBuild | Out-Null
    $msysPackageRoot = Convert-ToMsysPath -Path $packageRoot
    $msysPackageOutput = Convert-ToMsysPath -Path $packageOutput
    $msysMakepkgBuild = Convert-ToMsysPath -Path $makepkgBuild
    $msysMakepkgConfig = Convert-ToMsysPath -Path $MakepkgConfig
    $oldPath = $env:PATH
    try {
        $env:PATH = Split-Path -Parent $Bash
        $command = @"
export PKGDEST='$msysPackageOutput'
export BUILDDIR='$msysMakepkgBuild'
cd '$msysPackageRoot'
/usr/bin/makepkg --config '$msysMakepkgConfig' --force --cleanbuild --noconfirm
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

    $readbackRoot = Join-Path $packageRoot 'readback'
    New-Item -ItemType Directory -Path $readbackRoot | Out-Null
    & tar -xf $archive.FullName -C $readbackRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract $($archive.FullName)"
    }
    $executable = Join-Path $readbackRoot "usr\bin\$($package.readback)"
    $stageExecutable = Join-Path $Stage "usr\bin\$($package.readback)"
    Assert-FileHash -Path $executable -Expected (
        Get-FileHash -Algorithm SHA256 -LiteralPath $stageExecutable
    ).Hash.ToLowerInvariant()

    $probeInput = Join-Path $readbackRoot 'probe.txt'
    [IO.File]::WriteAllText($probeInput, "first`nneedle`nthird`n", [Text.UTF8Encoding]::new($false))
    $oldPath = $env:PATH
    try {
        $env:PATH = "$(Join-Path $readbackRoot 'usr\bin');$(Join-Path $Stage 'usr\bin');$oldPath"
        $output = switch ($package.name) {
            'diffutils' { @(& $executable $probeInput $probeInput 2>&1) }
            'findutils' { @(& $executable $readbackRoot -name 'probe.txt' 2>&1) }
            'gawk' { @(& $executable 'BEGIN { print 6 * 7 }' 2>&1) }
            'grep' { @(& $executable 'needle' $probeInput 2>&1) }
            'sed' { @(& $executable '-n' '2p' $probeInput 2>&1) }
        }
        if ($LASTEXITCODE -ne 0) {
            throw "$($package.name) native readback failed with exit code ${LASTEXITCODE}: $($output -join "`n")"
        }
    }
    finally {
        $env:PATH = $oldPath
    }
    $readbacks += [ordered]@{
        package = $package.name
        executable = $package.readback
        executable_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $executable).Hash.ToLowerInvariant()
        native_process = $true
        host_architecture = 'arm64'
        runtime_sha256 = $expectedRuntimeHash
        exit_code = 0
        output = $output
    }
}

$export = [ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-utility-packages-exported'
    provider = 'native-msys-qualified-utilities'
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
    status = 'qualified-current-d70-native-utility-packages'
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
        files = $manifestFiles.Count
    }
    package_manifests = $packageManifests
    native_readbacks = $readbacks
    controls = [ordered]@{
        packages = $packages.Count
        selected_paths = $claimedPaths.Count
        active_bash_excluded = $true
        active_coreutils_excluded = $true
        producer_stage_hashes_verified = $true
        packaged_binary_bytes_unchanged = $true
        producer_stage_modified = $false
        shared_prefixes_modified = $false
    }
}
$handoffPath = Join-Path $OutputDirectory 'handoff.json'
$handoff | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath $exportPath, $handoffPath | Select-Object FullName, Length
