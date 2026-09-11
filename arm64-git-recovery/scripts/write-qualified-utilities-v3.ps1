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

    $Value | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath $Path -Encoding utf8NoBOM
}

$v2Export = Join-Path $Root 'qualified-utilities-v2\export.json'
$v2Disposition = Join-Path $Root 'qualified-utilities-v2\provider-disposition.json'
$v1GrepArchive = Join-Path $Root (
    'qualified-utilities-v1\grep\packages\grep-1~3.0-7-aarch64.pkg.tar.zst'
)
$v1GrepManifest = Join-Path $Root 'qualified-utilities-v1\grep\payload-manifest.json'
$v1GrepPayload = Join-Path $Root 'qualified-utilities-v1\grep\payload'
$auditV11 = Join-Path $Root 'audit-v11-revoked-free.json'

Assert-FileHash -Path $v2Export -Expected 'ca6bd37fbc37e19dde851c1f02e4eb587807c691618dc82a401c5ada1837bbda'
Assert-FileHash -Path $v2Disposition -Expected 'e601a6fed1dbaa92fddeb31cd837bb1ed2335bc35786206cae9f4fc3bf1a3378'
Assert-FileHash -Path $v1GrepArchive -Expected '5e55eb0a1cfadf6c16e6c0be9d52ed5ccbf710df35c660ee75a01286a6b47c59'
Assert-FileHash -Path $v1GrepManifest -Expected '9b69aec1c40919880b3b14ea7046c04862f320a1a197cdff21077535a5516df5'
Assert-FileHash -Path $auditV11 -Expected 'c8262a3f61aa8bf1cb9913e2fa3287cbc22e4f0485cbed72b54629104b863b34'

$wrapperEvidence = @(
    [ordered]@{
        path = Join-Path $v1GrepPayload 'usr\bin\egrep'
        sha256 = '5fb6fffc64cea74659e50118403c6c190dac6c9cafd4bf0168a5fb2b7b027b0a'
        private_shebang = '#!/proc/cygdrive/c/ag-bash-e138-01/host-bootstrap-02/msys64/usr/bin/bash.exe'
        command = 'exec grep -E "$@"'
    },
    [ordered]@{
        path = Join-Path $v1GrepPayload 'usr\bin\fgrep'
        sha256 = '3e2eb9ac0bf277c07919f69d70d9c6d481b78a74b0ad6139b00107e49cf65563'
        private_shebang = '#!/proc/cygdrive/c/ag-bash-e138-01/host-bootstrap-02/msys64/usr/bin/bash.exe'
        command = 'exec grep -F "$@"'
    }
)
foreach ($wrapper in $wrapperEvidence) {
    Assert-FileHash -Path $wrapper.path -Expected $wrapper.sha256
    $lines = [IO.File]::ReadAllLines($wrapper.path)
    if ($lines.Count -ne 2 -or
        $lines[0] -ne $wrapper.private_shebang -or
        $lines[1] -ne $wrapper.command) {
        throw "Unexpected grep compatibility wrapper content: $($wrapper.path)"
    }
}

$source = Get-Content -Raw -LiteralPath $v2Export | ConvertFrom-Json
$retained = @($source.packages | Where-Object { $_.name -in 'diffutils', 'gawk' })
if ($retained.Count -ne 2) {
    throw "Expected two retained utility packages, found $($retained.Count)"
}
$grep = $source.packages | Where-Object { $_.name -eq 'grep' }
if ($null -eq $grep -or $grep.sha256 -ne (Get-Hash $v1GrepArchive)) {
    throw 'Utilities v2 grep identity is invalid'
}

$v3Root = Join-Path $Root 'qualified-utilities-v3'
if (Test-Path -LiteralPath $v3Root) {
    throw "Versioned output already exists: $v3Root"
}
New-Item -ItemType Directory -Path $v3Root | Out-Null

$exportPath = Join-Path $v3Root 'export.json'
Write-Json -Path $exportPath -Value ([ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-utility-packages-second-selective-exported'
    provider = 'native-msys-qualified-utilities'
    version = 'v3'
    supersedes = [ordered]@{
        path = $v2Export
        sha256 = Get-Hash $v2Export
    }
    runtime_cohort = $source.runtime_cohort
    packages = $retained
})

$dispositionPath = Join-Path $v3Root 'provider-disposition.json'
Write-Json -Path $dispositionPath -Value ([ordered]@{
    schema = 1
    status = 'qualified-utilities-v2-superseded-after-wrapper-relocation-audit'
    superseded_export = [ordered]@{
        path = $v2Export
        sha256 = Get-Hash $v2Export
    }
    superseded_disposition = [ordered]@{
        path = $v2Disposition
        sha256 = Get-Hash $v2Disposition
    }
    discovery_audit = [ordered]@{
        path = $auditV11
        sha256 = Get-Hash $auditV11
    }
    provider_export = [ordered]@{
        path = $exportPath
        sha256 = Get-Hash $exportPath
    }
    retained_unchanged = $retained
    newly_excluded = [ordered]@{
        name = 'grep'
        archive = $grep
        payload_manifest = [ordered]@{
            path = $v1GrepManifest
            sha256 = Get-Hash $v1GrepManifest
        }
        evidence = $wrapperEvidence
        reason = 'private-operational-shebangs-in-egrep-and-fgrep'
    }
    provider_packaging_action = [ordered]@{
        source_rebuild_required = $false
        binary_rebuild_required = $false
        requirements = @(
            'Repackage the exact grep.exe and data payload unchanged.',
            'For exact wrapper source hashes above, replace only the shebang with #!/usr/bin/sh.',
            'Preserve exec grep -E/-F behavior and the existing sh dependency.',
            'Publish changed-wrapper hashes, archive readback, and a current d70 grep/wrapper readback after the matrix window closes.'
        )
    }
    controls = [ordered]@{
        grep_archive_modified = $false
        producer_stage_modified = $false
        utility_export_v2_modified = $false
        release_archive_emitted = $false
    }
})

Get-Item -LiteralPath $exportPath, $dispositionPath |
    Select-Object FullName, Length
