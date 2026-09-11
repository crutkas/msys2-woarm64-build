[CmdletBinding()]
param(
    [string]$ChainHandoff = 'C:\ag-readline-e138-01\chain-handoff-01\handoff.json',
    [string]$ReadlineHandoff = 'C:\ag-readline-e138-01\readline-handoff-01\handoff.json',
    [string]$ReadlineInventory = 'C:\ag-readline-e138-01\readline-01\stage.inventory.json',
    [string]$ReadlineStage = 'C:\ag-readline-e138-01\readline-01\stage',
    [string]$LibeditHandoff = 'C:\ag-readline-e138-01\libedit-handoff-01\handoff.json',
    [string]$LibeditInventory = 'C:\ag-readline-e138-01\libedit-static-01\stage.inventory.json',
    [string]$LibeditStage = 'C:\ag-readline-e138-01\libedit-static-01\stage',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\terminal-libraries-v2',
    [string]$Bash = 'C:\ag-readline-e138-01\bootstrap\msys64\usr\bin\bash.exe',
    [string]$MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedHashes = @{
    $ChainHandoff = 'c5d0024793e88f90008aec126344116c961542dca9aa69f2051d9a7b9e3b4969'
    $ReadlineHandoff = '4fa5aeb8f7e86288e86f8076789c7a30a0475905319b97d235f1278c16261cb2'
    $ReadlineInventory = 'd35cc71c3aee6626a0fafbcc3012174ae260c0c6f8b0d1cc72e77ae7cf24d5c3'
    $LibeditHandoff = 'b39c05d1201511d76545251af977d8417fd0bbc7c9140d0d716a69919e7427ff'
    $LibeditInventory = 'ed33e6b9ed80563341f6b82399e8ca709a63a805c6ac1ec30b6c865d8d6ea286'
}

foreach ($path in $expectedHashes.Keys) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required input is missing: $path"
    }
    if (-not (Test-Path -LiteralPath $MakepkgConfig -PathType Leaf)) {
        throw "ARM64 makepkg configuration is missing: $MakepkgConfig"
    }

    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHashes[$path]) {
        throw "Hash mismatch for ${path}: expected $($expectedHashes[$path]), got $actualHash"
    }
}

function Test-StageInventory {
    param(
        [Parameter(Mandatory)]
        [string]$Stage,
        [Parameter(Mandatory)]
        [string]$Inventory
    )

    if (-not (Test-Path -LiteralPath $Stage -PathType Container)) {
        throw "Qualified stage is missing: $Stage"
    }

    $inventoryData = Get-Content -Raw -LiteralPath $Inventory | ConvertFrom-Json
    $expectedFiles = @($inventoryData.files.PSObject.Properties)
    $actualFiles = @(Get-ChildItem -LiteralPath $Stage -Recurse -File)
    if ($actualFiles.Count -ne $expectedFiles.Count) {
        throw "Stage file count mismatch for ${Stage}: expected $($expectedFiles.Count), got $($actualFiles.Count)"
    }

    foreach ($entry in $expectedFiles) {
        $path = Join-Path $Stage ($entry.Name -replace '/', '\')
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Inventory file is missing: $($entry.Name)"
        }

        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($actualHash -ne $entry.Value.sha256) {
            throw "Stage hash mismatch for $($entry.Name): expected $($entry.Value.sha256), got $actualHash"
        }
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

function Invoke-PackageBuild {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [string]$Stage,
        [Parameter(Mandatory)]
        [string]$Template
    )

    $buildRoot = Join-Path $OutputDirectory "build-$Name"
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    $privateStage = Join-Path $buildRoot 'qualified-stage'
    Copy-Item -LiteralPath $Stage -Destination $privateStage -Recurse
    $metadataDisposition = $null
    if ($Name -eq 'libedit') {
        $libtoolPath = Join-Path $privateStage 'usr\lib\libedit.la'
        $original = [IO.File]::ReadAllText($libtoolPath)
        $originalDependency = "dependency_libs=' -L=C:/ag-readline-e138-01/ncurses-static-cxx-01/stage/usr/lib -lncurses'"
        if (($original.Split($originalDependency).Count - 1) -ne 1) {
            throw 'Qualified libedit.la does not contain the single expected producer-private dependency path'
        }
        $metadataDisposition = [ordered]@{
            path = 'usr/lib/libedit.la'
            original_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Stage 'usr\lib\libedit.la')).Hash.ToLowerInvariant()
            producer_private_dependency_search_path = '-L=C:/ag-readline-e138-01/ncurses-static-cxx-01/stage/usr/lib'
            disposition = 'excluded-from-package'
            dependency_preserved_by_package = 'ncurses-devel'
        }
        Remove-Item -LiteralPath $libtoolPath
    }

    $stagePath = Convert-ToMsysPath -Path $privateStage
    $packageBuild = (Get-Content -Raw -LiteralPath $Template).
        Replace('@@STAGE_ROOT@@', $stagePath).
        Replace("`r`n", "`n")
    Set-Content -LiteralPath (Join-Path $buildRoot 'PKGBUILD') -Value $packageBuild -Encoding utf8NoBOM

    $packageOutput = Join-Path $buildRoot 'packages'
    $sourceOutput = Join-Path $buildRoot 'sources'
    $sourcePackageOutput = Join-Path $buildRoot 'source-packages'
    $logOutput = Join-Path $buildRoot 'logs'
    $makepkgBuildOutput = Join-Path $buildRoot 'makepkg-build'
    New-Item -ItemType Directory -Force -Path @(
        $packageOutput,
        $sourceOutput,
        $sourcePackageOutput,
        $logOutput,
        $makepkgBuildOutput
    ) | Out-Null

    $msysBuildRoot = Convert-ToMsysPath -Path $buildRoot
    $msysPackageOutput = Convert-ToMsysPath -Path $packageOutput
    $msysSourceOutput = Convert-ToMsysPath -Path $sourceOutput
    $msysSourcePackageOutput = Convert-ToMsysPath -Path $sourcePackageOutput
    $msysLogOutput = Convert-ToMsysPath -Path $logOutput
    $msysMakepkgBuildOutput = Convert-ToMsysPath -Path $makepkgBuildOutput
    $msysMakepkgConfig = Convert-ToMsysPath -Path $MakepkgConfig
    $oldPath = $env:PATH
    try {
        $env:PATH = Split-Path -Parent $Bash
        $command = @"
export PKGDEST='$msysPackageOutput'
export SRCDEST='$msysSourceOutput'
export SRCPKGDEST='$msysSourcePackageOutput'
export LOGDEST='$msysLogOutput'
export BUILDDIR='$msysMakepkgBuildOutput'
cd '$msysBuildRoot'
/usr/bin/makepkg --config '$msysMakepkgConfig' --force --cleanbuild --noconfirm
"@
        & $Bash --noprofile --norc -c ($command.Replace("`r`n", "`n")) |
            Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "makepkg failed for $Name with exit code $LASTEXITCODE"
        }
    }
    finally {
        $env:PATH = $oldPath
    }

    return [ordered]@{
        archives = @(Get-ChildItem -LiteralPath $packageOutput -File -Filter '*.pkg.tar.zst' | Sort-Object Name)
        metadata_disposition = $metadataDisposition
    }
}

function Test-LibeditRelocation {
    param(
        [Parameter(Mandatory)]
        [string]$Archive
    )

    $proofRoot = Join-Path $OutputDirectory 'libedit-relocation-proof'
    New-Item -ItemType Directory -Path $proofRoot | Out-Null
    & tar -xf $Archive -C $proofRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract $Archive for relocation proof"
    }

    $libtoolPath = Join-Path $proofRoot 'usr\lib\libedit.la'
    if (Test-Path -LiteralPath $libtoolPath) {
        throw 'Relocated libedit-devel package unexpectedly contains libedit.la'
    }
    $pkgconfigPath = Join-Path $proofRoot 'usr\lib\pkgconfig\libedit.pc'
    $pkgconfig = [IO.File]::ReadAllText($pkgconfigPath)
    if ($pkgconfig -match '(?i)ag-readline-e138-01|[A-Z]:[/\\].*ncurses-static') {
        throw 'Relocated libedit.pc retained a producer-private path'
    }
    if ($pkgconfig -notmatch '(?m)^prefix=/usr$') {
        throw 'Relocated libedit.pc does not use the canonical /usr prefix'
    }
    $pkginfo = [IO.File]::ReadAllText((Join-Path $proofRoot '.PKGINFO'))
    if ($pkginfo -notmatch '(?m)^depend = ncurses-devel$') {
        throw 'Relocated libedit-devel package omitted its ncurses-devel dependency'
    }

    $receipt = [ordered]@{
        schema = 1
        status = 'verified'
        archive = $Archive
        archive_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
        libtool_metadata = 'excluded'
        producer_private_path_absent = $true
        pkgconfig_prefix = '/usr'
        ncurses_dependency_preserved_by_package = $true
    }
    $receiptPath = Join-Path $proofRoot 'receipt.json'
    $receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptPath -Encoding utf8NoBOM
    return [ordered]@{
        path = $receiptPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $receiptPath).Hash.ToLowerInvariant()
    }
}

Test-StageInventory -Stage $ReadlineStage -Inventory $ReadlineInventory
Test-StageInventory -Stage $LibeditStage -Inventory $LibeditInventory

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists: $OutputDirectory"
}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$readlineTemplate = Join-Path $repoRoot 'arm64-git-recovery\native-packaging\readline\PKGBUILD.in'
$libeditTemplate = Join-Path $repoRoot 'arm64-git-recovery\native-packaging\libedit\PKGBUILD.in'

$readlineBuild = Invoke-PackageBuild -Name 'readline' -Stage $ReadlineStage -Template $readlineTemplate
$libeditBuild = Invoke-PackageBuild -Name 'libedit' -Stage $LibeditStage -Template $libeditTemplate
$archives = @($readlineBuild.archives) + @($libeditBuild.archives)
$expectedArchives = @(
    'libedit-20240808_3.1-1-aarch64.pkg.tar.zst',
    'libedit-devel-20240808_3.1-1-aarch64.pkg.tar.zst',
    'libreadline-8.3.003-1-aarch64.pkg.tar.zst',
    'libreadline-devel-8.3.003-1-aarch64.pkg.tar.zst'
)
$archiveDifference = @(
    Compare-Object $expectedArchives @($archives.Name)
)
if ($archiveDifference.Count -ne 0) {
    throw "Unexpected terminal library package set: $($archives.Name -join ', ')"
}

$packageDirectory = Join-Path $OutputDirectory 'packages'
New-Item -ItemType Directory -Path $packageDirectory | Out-Null
$packageRecords = foreach ($archive in $archives) {
    $destination = Join-Path $packageDirectory $archive.Name
    Copy-Item -LiteralPath $archive.FullName -Destination $destination
    [ordered]@{
        path = $destination
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
    }
}
$libeditDevelArchive = $archives |
    Where-Object Name -eq 'libedit-devel-20240808_3.1-1-aarch64.pkg.tar.zst' |
    Select-Object -First 1
$relocationProof = Test-LibeditRelocation -Archive $libeditDevelArchive.FullName

$chainData = Get-Content -Raw -LiteralPath $ChainHandoff | ConvertFrom-Json
$export = [ordered]@{
    schema = 1
    status = 'admitted-qualified-native-msys-terminal-libraries-exported'
    provider = 'native-msys-qualified-terminal-libraries'
    version = 'v2'
    runtime_cohort = [ordered]@{
        sha256 = $chainData.runtime_sha256
        compatibility_with_current_d70_runtime_claimed = $false
    }
    packages = $packageRecords
}
$exportPath = Join-Path $OutputDirectory 'export.json'
$export | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $exportPath -Encoding utf8NoBOM

$handoff = [ordered]@{
    schema = 1
    status = 'qualified-native-msys-packages'
    provider_export = $exportPath
    provider_export_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $exportPath).Hash.ToLowerInvariant()
    source_handoffs = @(
        [ordered]@{
            path = $ReadlineHandoff
            sha256 = $expectedHashes[$ReadlineHandoff]
            inventory = $ReadlineInventory
            inventory_sha256 = $expectedHashes[$ReadlineInventory]
        },
        [ordered]@{
            path = $LibeditHandoff
            sha256 = $expectedHashes[$LibeditHandoff]
            inventory = $LibeditInventory
            inventory_sha256 = $expectedHashes[$LibeditInventory]
        }
    )
    controls = [ordered]@{
        fresh_private_roots = $true
        producer_stage_hashes_verified = $true
        native_binary_bytes_unchanged = $true
        package_ownership = 'Pinned MSYS2 readline and libedit split-package rules.'
        stage_status_preserved = @(
            $chainData.packages.readline.status,
            $chainData.packages.libedit.status
        )
        runtime_cohort = $chainData.runtime_sha256
        compatibility_with_current_d70_runtime_claimed = $false
        producer_prefix_modified = $false
        metadata_disposition = $libeditBuild.metadata_disposition
        relocation_proof = $relocationProof
    }
}
$handoffPath = Join-Path $OutputDirectory 'handoff.json'
$handoff | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath $exportPath, $handoffPath | Select-Object FullName, Length
