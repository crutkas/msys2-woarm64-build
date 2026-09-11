[CmdletBinding()]
param(
    [string]$Root = 'C:\ap11-native-provider-intake'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

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

function Write-Json {
    param(
        [Parameter(Mandatory)]
        [object]$Value,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $Value | ConvertTo-Json -Depth 16 |
        Set-Content -LiteralPath $Path -Encoding utf8NoBOM
}

$v3Export = Join-Path $Root 'qualified-utilities-v3\export.json'
$v3Disposition = Join-Path $Root 'qualified-utilities-v3\provider-disposition.json'
$grepExportPath = Join-Path $Root 'qualified-grep-v4\export.json'
$grepHandoffPath = Join-Path $Root 'qualified-grep-v4\handoff.json'
$grepPayloadManifestPath = Join-Path $Root 'qualified-grep-v4\payload-manifest.json'

Assert-FileHash -Path $v3Export -Expected 'a3872466c175bd47e87ee2efb7d812a3fdbf90aea42709166fd13ab399fd89c4'
Assert-FileHash -Path $v3Disposition -Expected 'a3f53bd2919ef40f6428cc0bf4ce3edd838b0a7ebf3053d1c7e6a914bebf80dd'

$v3 = Get-Content -Raw -LiteralPath $v3Export | ConvertFrom-Json
$grepExport = Get-Content -Raw -LiteralPath $grepExportPath | ConvertFrom-Json
$grepHandoff = Get-Content -Raw -LiteralPath $grepHandoffPath | ConvertFrom-Json
$grepPayloadManifest = (
    Get-Content -Raw -LiteralPath $grepPayloadManifestPath | ConvertFrom-Json
)
if ($grepExport.status -ne 'qualified-current-d70-native-grep-wrapper-relocation-exported' -or
    $grepExport.provider -ne 'native-msys-grep' -or
    $grepExport.version -ne 'v4' -or
    @($grepExport.packages).Count -ne 1 -or
    $grepExport.packages[0].name -ne 'grep' -or
    $grepExport.runtime_cohort.sha256 -ne $v3.runtime_cohort.sha256 -or
    $grepPayloadManifest.wrapper_transforms[0].package_sha256 -ne '50496c34633635bf3fe9c108ae26c26f8871ffc35f741b9e1426897a1e65f263' -or
    $grepPayloadManifest.wrapper_transforms[1].package_sha256 -ne 'a35795589500118708cb879c5678c1daa0dc3c636c7dbad172a6a5918ae91c5b') {
    throw 'Qualified grep export does not match the bounded wrapper-only repair contract'
}
$grepPackage = $grepExport.packages[0]
Assert-FileHash -Path $grepPackage.path -Expected $grepPackage.sha256
if ($grepHandoff.provider_export.sha256 -ne (Get-Hash $grepExportPath) -or
    $grepHandoff.package.sha256 -ne $grepPackage.sha256 -or
    $grepHandoff.controls.source_rebuilt -ne $false -or
    $grepHandoff.controls.grep_binary_modified -ne $false -or
    @($grepHandoff.current_runtime_readback.wrappers).Count -ne 2) {
    throw 'Qualified grep handoff is inconsistent with its export or controls'
}

$v4Root = Join-Path $Root 'qualified-utilities-v4'
if (Test-Path -LiteralPath $v4Root) {
    throw "Versioned output already exists: $v4Root"
}
New-Item -ItemType Directory -Path $v4Root | Out-Null

$packages = @($v3.packages) + @(
    [ordered]@{
        name = $grepPackage.name
        path = $grepPackage.path
        sha256 = $grepPackage.sha256
    }
)
$exportPath = Join-Path $v4Root 'export.json'
Write-Json -Path $exportPath -Value ([ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-utility-packages-wrapper-repair-exported'
    provider = 'native-msys-qualified-utilities'
    version = 'v4'
    supersedes = [ordered]@{
        path = $v3Export
        sha256 = Get-Hash $v3Export
    }
    runtime_cohort = $v3.runtime_cohort
    packages = $packages
})

$dispositionPath = Join-Path $v4Root 'provider-disposition.json'
Write-Json -Path $dispositionPath -Value ([ordered]@{
    schema = 1
    status = 'qualified-utilities-v3-superseded-by-bounded-grep-wrapper-repair'
    superseded_export = [ordered]@{
        path = $v3Export
        sha256 = Get-Hash $v3Export
    }
    superseded_disposition = [ordered]@{
        path = $v3Disposition
        sha256 = Get-Hash $v3Disposition
    }
    provider_export = [ordered]@{
        path = $exportPath
        sha256 = Get-Hash $exportPath
    }
    retained_unchanged = @($v3.packages)
    admitted_grep = [ordered]@{
        provider_export = [ordered]@{
            path = $grepExportPath
            sha256 = Get-Hash $grepExportPath
        }
        handoff = [ordered]@{
            path = $grepHandoffPath
            sha256 = Get-Hash $grepHandoffPath
        }
        archive = $grepPackage
        transforms = $grepPayloadManifest.wrapper_transforms
        unchanged_payload_manifest = [ordered]@{
            path = $grepPayloadManifestPath
            sha256 = Get-Hash $grepPayloadManifestPath
        }
    }
    still_excluded = @(
        [ordered]@{
            name = 'findutils'
            reason = 'compiled private locale and locatedb operational paths'
        },
        [ordered]@{
            name = 'sed'
            reason = 'compiled private locale operational path'
        }
    )
    controls = [ordered]@{
        grep_binary_rebuilt = $false
        grep_binary_bytes_changed = $false
        source_provider_prefix_modified = $false
        release_archive_emitted = $false
    }
})

Get-Item -LiteralPath $exportPath, $dispositionPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
