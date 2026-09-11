[CmdletBinding()]
param(
    [string]$NetworkExport = 'C:\ap09-ca5f\curl-packages-v2\export-12\export.json',
    [string]$Pcre2Handoff = 'C:\ap07-pcre2-accd01\delivery-01\package-handoff.json',
    [string]$DependencyExport = 'C:\ap12-ca5f\python-provider-export-01\export.json',
    [string]$OutputDirectory = 'C:\ap11-native-provider-intake\network-pcre2-10.48-3-v1'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedNetworkExportHash = '546d8ca66282b89803d6423f36db1f562fadf759e8d4a7e11870cb485ea84dd8'
$expectedPcre2HandoffHash = '90b3ee317296786d8465b943a9dab703c81a5c482407677ee716e8572b1ea1ab'
$expectedDependencyExportHash = 'c9dda99aa3d0125da21f1a38e4b00c6f6f46d4423c3aa910dfb332be0a36de81'
$expectedOldPcre2Hash = '63ca004e570269889a30d4046a77946f09ddc6179a8be9b567e90cc9f4e3d7ec'
$expectedNewPcre2Hash = '7460d0061581ce54d25a046860f6ce02bcde899256b58825a4b4ceb1fcfeac34'
$packageName = 'mingw-w64-aarch64-pcre2'
$requiredGitRuntimeDll = 'mingwarm64/bin/libpcre2-8.dll'

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

function Get-PackageField {
    param(
        [Parameter(Mandatory)]
        [object]$Row,
        [Parameter(Mandatory)]
        [string[]]$Names
    )

    foreach ($name in $Names) {
        $property = $Row.PSObject.Properties[$name]
        if ($null -ne $property) {
            return $property.Value
        }
    }
    return $null
}

Assert-FileHash -Path $NetworkExport -Expected $expectedNetworkExportHash
Assert-FileHash -Path $Pcre2Handoff -Expected $expectedPcre2HandoffHash
Assert-FileHash -Path $DependencyExport -Expected $expectedDependencyExportHash

$network = Get-Content -Raw -LiteralPath $NetworkExport | ConvertFrom-Json
$pcre2 = Get-Content -Raw -LiteralPath $Pcre2Handoff | ConvertFrom-Json
$dependencyProvider = Get-Content -Raw -LiteralPath $DependencyExport | ConvertFrom-Json
$oldRows = @($network.packages | Where-Object name -eq $packageName)
if ($oldRows.Count -ne 1) {
    throw "Expected one existing $packageName row, found $($oldRows.Count)"
}
$oldRow = $oldRows[0]
if ($oldRow.version -ne '10.48-1' -or $oldRow.sha256 -ne $expectedOldPcre2Hash) {
    throw "Unexpected existing PCRE2 identity: $($oldRow.version) $($oldRow.sha256)"
}

$newArchive = $pcre2.Package.Archive.Path
if ($pcre2.Status -ne 'ready-for-pipeline-admission-native-mingw-pcre2' -or
    $pcre2.Package.Name -ne $packageName -or
    $pcre2.Package.Version -ne '10.48-3' -or
    $pcre2.Package.Archive.SHA256 -ne $expectedNewPcre2Hash) {
    throw 'Qualified PCRE2 handoff does not contain the expected admission identity'
}
Assert-FileHash -Path $newArchive -Expected $expectedNewPcre2Hash
$archiveEntries = @(& tar -tf $newArchive)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to list $newArchive"
}
if ($requiredGitRuntimeDll -notin $archiveEntries) {
    $actualRuntimeDlls = @(
        $archiveEntries |
        Where-Object { $_ -like 'mingwarm64/bin/libpcre2*.dll' } |
        Sort-Object
    )
    throw (
        "Qualified PCRE2 10.48-3 is not Git ABI-name compatible: required " +
        "$requiredGitRuntimeDll, package contains $($actualRuntimeDlls -join ', ')"
    )
}

$pkginfo = @(& tar -xOf $newArchive .PKGINFO)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read .PKGINFO from $newArchive"
}
$pkginfoValues = @{}
foreach ($line in $pkginfo) {
    if ($line -match '^([^#][^=]*?)\s*=\s*(.*)$') {
        $key = $Matches[1].Trim()
        if (-not $pkginfoValues.ContainsKey($key)) {
            $pkginfoValues[$key] = @()
        }
        $pkginfoValues[$key] += $Matches[2].Trim()
    }
}
if ([string]$pkginfoValues.pkgname[0] -ne $packageName -or
    [string]$pkginfoValues.pkgver[0] -ne '10.48-3' -or
    [string]$pkginfoValues.arch[0] -ne 'any') {
    throw 'PCRE2 archive metadata does not match the qualified handoff'
}
$expectedDependencies = @(
    'mingw-w64-aarch64-bzip2',
    'mingw-w64-aarch64-wineditline',
    'mingw-w64-aarch64-zlib'
)
$actualDependencies = @($pkginfoValues.depend | Sort-Object)
if (@(Compare-Object ($expectedDependencies | Sort-Object) $actualDependencies).Count -ne 0) {
    throw "Unexpected PCRE2 dependencies: $($actualDependencies -join ', ')"
}
$dependencyRows = @($dependencyProvider.packages)
$availableNames = @($network.packages.name) + @(
    $dependencyRows | ForEach-Object { Get-PackageField -Row $_ -Names @('packageName', 'name') }
)
foreach ($dependency in $actualDependencies) {
    if ($dependency -notin $availableNames) {
        throw "The bound combined input does not contain PCRE2 dependency $dependency"
    }
    $dependencyRow = $dependencyRows | Where-Object {
        (Get-PackageField -Row $_ -Names @('packageName', 'name')) -eq $dependency
    } | Select-Object -First 1
    if ($null -ne $dependencyRow) {
        $archiveField = Get-PackageField -Row $dependencyRow -Names @('archive')
        $dependencyPath = if ($archiveField) {
            Join-Path (Split-Path -Parent $DependencyExport) $archiveField
        }
        else {
            Get-PackageField -Row $dependencyRow -Names @('path')
        }
        Assert-FileHash -Path $dependencyPath -Expected (Get-PackageField -Row $dependencyRow -Names @('sha256'))
    }
}

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory already exists: $OutputDirectory"
}
$packageDirectory = Join-Path $OutputDirectory 'packages'
New-Item -ItemType Directory -Path $packageDirectory | Out-Null

$newRows = foreach ($row in $network.packages) {
    $sourcePath = $row.path
    $expectedHash = $row.sha256
    if ($row.name -eq $packageName) {
        $sourcePath = $newArchive
        $expectedHash = $expectedNewPcre2Hash
    }
    Assert-FileHash -Path $sourcePath -Expected $expectedHash
    $destination = Join-Path $packageDirectory (Split-Path -Leaf $sourcePath)
    Copy-Item -LiteralPath $sourcePath -Destination $destination

    if ($row.name -eq $packageName) {
        [ordered]@{
            name = $packageName
            version = '10.48-3'
            path = $destination
            sha256 = $expectedNewPcre2Hash
            files = [int]$pcre2.Package.PayloadFiles
            bytes = [int64]$pkginfoValues.size[0]
            depends = $actualDependencies
            provides = @()
            conflicts = @()
        }
    }
    else {
        $copy = [ordered]@{}
        foreach ($property in $row.PSObject.Properties) {
            $copy[$property.Name] = $property.Value
        }
        $copy.path = $destination
        $copy
    }
}

$export = [ordered]@{
    schema = 1
    status = 'relocatable-native-network-packages-pcre2-10.48-3-exported'
    generated_utc = [DateTime]::UtcNow.ToString('o')
    target = $network.target
    pinned_recipe = $network.pinned_recipe
    immutable_admission = $network.immutable_admission
    supersedes = [ordered]@{
        export = [ordered]@{
            path = $NetworkExport
            sha256 = $expectedNetworkExportHash
        }
        package = [ordered]@{
            name = $packageName
            old_version = '10.48-1'
            old_sha256 = $expectedOldPcre2Hash
            new_version = '10.48-3'
            new_sha256 = $expectedNewPcre2Hash
            qualified_handoff = [ordered]@{
                path = $Pcre2Handoff
                sha256 = $expectedPcre2HandoffHash
            }
        }
    }
    packages = $newRows
}
$exportPath = Join-Path $OutputDirectory 'export.json'
$export | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $exportPath -Encoding utf8NoBOM

$handoff = [ordered]@{
    schema = 1
    status = 'qualified-network-export-single-pcre2-supersession'
    provider_export = [ordered]@{
        path = $exportPath
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $exportPath).Hash.ToLowerInvariant()
    }
    source_export = [ordered]@{
        path = $NetworkExport
        sha256 = $expectedNetworkExportHash
    }
    pcre2_handoff = [ordered]@{
        path = $Pcre2Handoff
        sha256 = $expectedPcre2HandoffHash
    }
    dependency_export = [ordered]@{
        path = $DependencyExport
        sha256 = $expectedDependencyExportHash
    }
    controls = [ordered]@{
        packages = $newRows.Count
        replaced_package_rows = 1
        duplicate_package_names = @($newRows | Group-Object name | Where-Object Count -ne 1).Count
        unchanged_archives = $newRows.Count - 1
        all_archive_hashes_verified = $true
        selected_pcre2_dependencies = $actualDependencies
        dependency_packages_present = $true
        producer_archives_modified = $false
        shared_prefixes_modified = $false
    }
}
$handoffPath = Join-Path $OutputDirectory 'handoff.json'
$handoff | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $handoffPath -Encoding utf8NoBOM

Get-Item -LiteralPath $exportPath, $handoffPath | Select-Object FullName, Length
