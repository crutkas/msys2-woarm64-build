#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $NewGettextPackage,
    [Parameter(Mandatory)][string] $GettextProviderExport,
    [Parameter(Mandatory)][string] $NetworkSourceExport,
    [Parameter(Mandatory)][string] $PythonSourceExport,
    [Parameter(Mandatory)][string] $CorrectedGitHandoff,
    [Parameter(Mandatory)][string] $CurrentIntakeAudit,
    [Parameter(Mandatory)][string] $OperationalPrefixLineage,
    [Parameter(Mandatory)][string] $ProviderRejectionEnforcement,
    [Parameter(Mandatory)][string] $OutputRoot
)

$ErrorActionPreference = 'Stop'
$oldGettextHash = '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46'
$sourceBindings = @{
    network = '3faec2f42d87e28236dcc451ab6f48c63b67bd54aee746e1ebdf9debf3f1f30f'
    python = 'b2c03126b1250757bd41a6f561e83fd9c0c9cb0f4d5bbf51c2be14ccc43c4677'
}

function Get-Hash([string] $Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-PackageMetadata([string] $Archive) {
    $requiredEntries = '.PKGINFO', '.BUILDINFO', '.MTREE'
    $entries = @(& "$env:SystemRoot\System32\tar.exe" --zstd -tf $Archive)
    if ($LASTEXITCODE -ne 0) { throw "Cannot list package archive: $Archive" }
    foreach ($entry in $requiredEntries) {
        if ($entry -cnotin $entries) { throw "Package archive is missing $entry`: $Archive" }
    }
    $lines = @(& "$env:SystemRoot\System32\tar.exe" --zstd -xOf $Archive .PKGINFO)
    if ($LASTEXITCODE -ne 0) { throw "Cannot read package metadata: $Archive" }
    $fields = @{}
    foreach ($line in $lines) {
        if ($line -notmatch '^([^#][^=]+?) = (.*)$') { continue }
        $key = $Matches[1].Trim()
        if (-not $fields.ContainsKey($key)) {
            $fields[$key] = [Collections.Generic.List[string]]::new()
        }
        $fields[$key].Add($Matches[2])
    }
    foreach ($required in 'pkgname', 'pkgver', 'arch') {
        if (-not $fields.ContainsKey($required) -or $fields[$required].Count -ne 1) {
            throw "Package archive has invalid $required metadata: $Archive"
        }
    }
    [ordered]@{
        packageName = $fields.pkgname[0]
        packageVersion = $fields.pkgver[0]
        architecture = $fields.arch[0]
        depends = if ($fields.ContainsKey('depend')) { @($fields.depend) } else { @() }
        provides = if ($fields.ContainsKey('provides')) { @($fields.provides) } else { @() }
        conflicts = if ($fields.ContainsKey('conflict')) { @($fields.conflict) } else { @() }
        replaces = if ($fields.ContainsKey('replaces')) { @($fields.replaces) } else { @() }
        fileCount = @($entries | Where-Object {
            $_ -and $_ -cnotin $requiredEntries -and -not $_.EndsWith('/')
        }).Count
    }
}

function Resolve-ArchivePath([string] $ExportPath, [string] $ArchivePath) {
    if ([IO.Path]::IsPathRooted($ArchivePath)) { return $ArchivePath }
    Join-Path (Split-Path $ExportPath) $ArchivePath.Replace('/', '\')
}

function Set-Property([object] $Object, [string] $Name, $Value) {
    if ($Object.PSObject.Properties.Name -contains $Name) {
        $Object.$Name = $Value
    } else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function Export-SupersededClosure(
    [ValidateSet('network', 'python')][string] $Role,
    [string] $SourceExport,
    [string] $Destination
) {
    $source = Get-Item -LiteralPath $SourceExport
    if ((Get-Hash $source.FullName) -cne $sourceBindings[$Role]) {
        throw "$Role source export hash changed."
    }
    $document = Get-Content $source.FullName -Raw | ConvertFrom-Json
    if (@($document.packages | Where-Object {
        $_.name -ceq 'mingw-w64-aarch64-gettext' -or $_.sha256 -ceq $oldGettextHash
    }).Count -ne 0) {
        throw "$Role revoked-free baseline unexpectedly contains the rejected gettext archive."
    }
    if ($document.rejected_archive.sha256 -cne $oldGettextHash) {
        throw "$Role revoked-free baseline does not bind the exact rejected gettext archive."
    }

    New-Item -ItemType Directory -Path "$Destination\packages" | Out-Null
    foreach ($package in $document.packages) {
        $sourceArchive = Resolve-ArchivePath $source.FullName $package.path
        if (-not (Test-Path -LiteralPath $sourceArchive -PathType Leaf)) {
            throw "$Role closure package is missing: $sourceArchive"
        }
        if ((Get-Hash $sourceArchive) -cne $package.sha256) {
            throw "$Role immutable package hash changed: $($package.name)"
        }
        $destinationArchive = Join-Path "$Destination\packages" (Split-Path $sourceArchive -Leaf)
        Copy-Item -LiteralPath $sourceArchive -Destination $destinationArchive
        $copiedHash = Get-Hash $destinationArchive
        if ($copiedHash -cne $package.sha256) {
            throw "$Role copied package hash mismatch: $($package.name)"
        }

        $relativeArchive = "packages/$(Split-Path $destinationArchive -Leaf)"
        Set-Property $package 'path' $relativeArchive
    }

    $gettextDestination = Join-Path "$Destination\packages" $gettextArchive.Name
    Copy-Item $gettextArchive.FullName $gettextDestination
    if ((Get-Hash $gettextDestination) -cne $gettextHash) {
        throw "$Role replacement gettext copy hash mismatch."
    }
    $document.packages = @($document.packages) + [pscustomobject][ordered]@{
        name = $gettextMetadata.packageName
        path = "packages/$($gettextArchive.Name)"
        sha256 = $gettextHash
        packageName = $gettextMetadata.packageName
        packageVersion = $gettextMetadata.packageVersion
        architecture = $gettextMetadata.architecture
        archive = "packages/$($gettextArchive.Name)"
        bytes = $gettextArchive.Length
        depends = @($gettextMetadata.depends)
        provides = @($gettextMetadata.provides)
        conflicts = @($gettextMetadata.conflicts)
        replaces = @($gettextMetadata.replaces)
        fileCount = $gettextMetadata.fileCount
        hasPkgInfo = $true
        hasBuildInfo = $true
        hasMtree = $true
        reusedUnchanged = $false
    }
    $missingClosureDependencies = @(
        $gettextMetadata.depends | Where-Object { $_ -cnotin $document.packages.name }
    )
    if ($missingClosureDependencies.Count) {
        throw "$Role revoked-free baseline lacks replacement gettext dependencies: " +
            ($missingClosureDependencies -join ', ')
    }
    if ($Role -ceq 'network') {
        $document.status = 'network-provider-revoked-gettext-replaced-complete'
        $document.generated_utc = [DateTime]::UtcNow.ToString('o')
    } else {
        $document.status = 'python-provider-revoked-gettext-replaced-complete'
        $document.generatedUtc = [DateTime]::UtcNow.ToString('o')
    }
    Set-Property $document 'packageCount' @($document.packages).Count
    Set-Property $document 'closure_complete' $true
    Set-Property $document 'missing_replacement' $null
    $document | Add-Member -NotePropertyName gettextSupersession -NotePropertyValue ([ordered]@{
        priorIdentity = 'mingw-w64-aarch64-gettext-0.26-1'
        priorArchiveSha256 = $oldGettextHash
        replacementIdentity = 'mingw-w64-aarch64-gettext-1.0-1'
        replacementArchiveSha256 = $gettextHash
        providerExportSha256 = $providerExportHash
        sourceExport = $source.FullName
        sourceExportSha256 = $sourceBindings[$Role]
        unchangedPackageArchives = @($document.packages).Count - 1
    })
    $document | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath "$Destination\export.json" -Encoding utf8
}

if (Test-Path -LiteralPath $OutputRoot) {
    throw 'Superseding gettext closure output must be new.'
}
$gettextArchive = Get-Item -LiteralPath $NewGettextPackage
$providerExport = Get-Item -LiteralPath $GettextProviderExport
$networkExport = Get-Item -LiteralPath $NetworkSourceExport
$pythonExport = Get-Item -LiteralPath $PythonSourceExport
$gitHandoff = Get-Item -LiteralPath $CorrectedGitHandoff
if ((Get-Hash $gitHandoff.FullName) -cne
    '947cdb44357f6e6639b0ff87c1b4299f53073477ff9cb5ed8e30b276ed54d911') {
    throw 'Corrected exact-15 Git handoff hash changed.'
}
$intakeAudit = Get-Item -LiteralPath $CurrentIntakeAudit
if ((Get-Hash $intakeAudit.FullName) -cne
    'd71f2c02617dbc24e338065f5d5ef5e44f08669240fc40b21a9ad82a8823fc47') {
    throw 'Current revoked-free intake audit hash changed.'
}
$operationalLineage = Get-Item -LiteralPath $OperationalPrefixLineage
if ((Get-Hash $operationalLineage.FullName) -cne
    'b6741cedc7f502822638e9dee22740310f51cdd7eda9bdeec0b8a26e2dae6332') {
    throw 'Operational-prefix lineage receipt hash changed.'
}
$rejectionEnforcement = Get-Item -LiteralPath $ProviderRejectionEnforcement
if ((Get-Hash $rejectionEnforcement.FullName) -cne
    '69818c620590f23bd38ba7921c515cdf6629d7d20a55c15fbe8427bf6f2779be') {
    throw 'Provider rejection enforcement receipt hash changed.'
}
$gettextHash = Get-Hash $gettextArchive.FullName
$providerExportHash = Get-Hash $providerExport.FullName
$gettextMetadata = Read-PackageMetadata $gettextArchive.FullName
if ($gettextMetadata.packageName -cne 'mingw-w64-aarch64-gettext' -or
    $gettextMetadata.packageVersion -cne '1.0-1' -or
    'mingw-w64-aarch64-libiconv' -cnotin $gettextMetadata.depends) {
    throw 'Replacement gettext package does not have the truthful required identity.'
}
$providerDocument = Get-Content $providerExport.FullName -Raw | ConvertFrom-Json
$providerPackage = @($providerDocument.packages | Where-Object {
    $_.name -ceq 'mingw-w64-aarch64-gettext'
})
if ($providerPackage.Count -ne 1 -or $providerPackage[0].sha256 -cne $gettextHash) {
    throw 'Gettext provider export does not bind the replacement archive.'
}

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
Copy-Item $providerExport.FullName "$OutputRoot\gettext-provider-export.json"
Export-SupersededClosure network $networkExport.FullName "$OutputRoot\network"
Export-SupersededClosure python $pythonExport.FullName "$OutputRoot\python"

$handoff = [ordered]@{
    schema = 1
    status = 'gettext-1.0-replacement-bound-to-network-and-python-closures'
    generatedUtc = [DateTime]::UtcNow.ToString('o')
    revocation = [ordered]@{
        path = 'C:\ap11-native-provider-intake\current-admission-revocation-v1.json'
        sha256 = '206cffaff0a16fc2b0453d74c923b7830fa62c0d7715327cb5a61d8e35421894'
    }
    currentIntakeBaseline = [ordered]@{
        path = $intakeAudit.FullName
        sha256 = 'd71f2c02617dbc24e338065f5d5ef5e44f08669240fc40b21a9ad82a8823fc47'
        policy = 'The replacement must add the MinGW gettext provider without reintroducing the revoked archive or conflating admitted native MSYS gettext splits with the MinGW namespace.'
    }
    correctedGit = [ordered]@{
        path = $gitHandoff.FullName
        sha256 = '947cdb44357f6e6639b0ff87c1b4299f53073477ff9cb5ed8e30b276ed54d911'
        policy = 'The exact 15 Git package archives remain unchanged; qualification binds their native libintl consumer.'
    }
    replacement = [ordered]@{
        identity = 'mingw-w64-aarch64-gettext-1.0-1'
        archive = $gettextArchive.FullName
        archiveSha256 = $gettextHash
        providerExport = (Get-Item "$OutputRoot\gettext-provider-export.json").FullName
        providerExportSha256 = Get-Hash "$OutputRoot\gettext-provider-export.json"
    }
    closures = @(
        [ordered]@{
            role = 'network'
            path = (Get-Item "$OutputRoot\network\export.json").FullName
            sha256 = Get-Hash "$OutputRoot\network\export.json"
        },
        [ordered]@{
            role = 'python'
            path = (Get-Item "$OutputRoot\python\export.json").FullName
            sha256 = Get-Hash "$OutputRoot\python\export.json"
        }
    )
    policy = @(
        'Only the revoked gettext archive is replaced.',
        'Every other package archive is copied byte-for-byte with its prior hash.',
        'No compatibility alias or 0.26 provider identity is emitted.',
        'The gettext replacement does not claim to clear unrelated operational-prefix blockers.'
    )
    independentBlockers = @(
        [ordered]@{
            path = 'mingwarm64/bin/libcurl-4.dll'
            sha256 = 'd060e2d1127b52b49f7956d5eee59681ae160cd79bdac2156a45c05fbdd46669'
            issue = 'Contains a private curl producer prefix.'
        },
        [ordered]@{
            path = 'mingwarm64/bin/tcl86.dll'
            sha256 = '28dfc8ae4069a3fbf31bd461aff0d1c01d9701fe219c70de199b0087943e22d9'
            issue = 'Contains private bootstrap bin, Tcl library, and manpage prefixes.'
        }
    )
    operationalPrefixLineage = [ordered]@{
        path = $operationalLineage.FullName
        sha256 = 'b6741cedc7f502822638e9dee22740310f51cdd7eda9bdeec0b8a26e2dae6332'
        disposition = 'Pinned-source canonical-prefix rebuilds required; archive-only remediation forbidden.'
    }
    failedProducerEnforcement = [ordered]@{
        path = $rejectionEnforcement.FullName
        sha256 = '69818c620590f23bd38ba7921c515cdf6629d7d20a55c15fbe8427bf6f2779be'
        failedAttemptReceipt = 'C:\ap12-ca5f\gettext-native-03\failure-receipt.json'
        failedAttemptSha256 = 'd0e624fa2e062a92ca8df971501a33b226dcd7e4c0d76cf8e678c685b07a24fd'
        policy = 'No failed bytes are admitted; full corrected build, checks, install, and qualification are required.'
    }
}
$handoff | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath "$OutputRoot\handoff.json" -Encoding utf8
$handoff
