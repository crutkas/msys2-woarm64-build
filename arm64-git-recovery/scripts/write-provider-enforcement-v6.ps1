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

$v5 = Join-Path $Root 'provider-rejection-enforcement-v5.json'
$failure = 'C:\ap12-ca5f\gettext-native-02\failure-receipt.json'
$compressionHandoff = 'C:\ap06-2160\compression-policy-handoff-20260909-01\handoff.json'
$prefixLineage = Join-Path $Root 'operational-prefix-lineage-v1.json'
$grepExport = Join-Path $Root 'qualified-grep-v4\export.json'
$grepHandoff = Join-Path $Root 'qualified-grep-v4\handoff.json'
$utilitiesExport = Join-Path $Root 'qualified-utilities-v4\export.json'
$utilitiesDisposition = Join-Path $Root 'qualified-utilities-v4\provider-disposition.json'

Assert-FileHash -Path $v5 -Expected 'ea61cdaad43743b72b1aa5f0d2d901b41f6eec552458a114ee77824200d7f659'
Assert-FileHash -Path $failure -Expected 'c1c38afa150a3f41cf6a6513158ae1e7efd411577677fb9bc131d4fbb2c79d78'
Assert-FileHash -Path $compressionHandoff -Expected '406b2632c55b136be368d12609c55649a98b1d852d7f65b506149523b9ddd9dc'
Assert-FileHash -Path $prefixLineage -Expected 'b6741cedc7f502822638e9dee22740310f51cdd7eda9bdeec0b8a26e2dae6332'

$grep = Get-Content -Raw -LiteralPath $grepExport | ConvertFrom-Json
$handoff = Get-Content -Raw -LiteralPath $grepHandoff | ConvertFrom-Json
$utilities = Get-Content -Raw -LiteralPath $utilitiesExport | ConvertFrom-Json
if ($grep.status -ne 'qualified-current-d70-native-grep-wrapper-relocation-exported' -or
    $grep.version -ne 'v4' -or
    $handoff.controls.archive_payload_hash_compared_to_original -ne $true -or
    $handoff.controls.grep_binary_modified -ne $false -or
    @($handoff.current_runtime_readback.wrappers).Count -ne 2 -or
    $utilities.version -ne 'v4' -or
    @($utilities.packages | Where-Object name -eq 'grep').Count -ne 1) {
    throw 'Completed grep or utilities v4 provider evidence is invalid'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourcePaths = @(
    'arm64-git-recovery/scripts/assemble-full-release.py',
    'arm64-git-recovery/contracts/full-release-v1.json',
    'arm64-git-recovery/docs/FULL-RELEASE-ASSEMBLY.md',
    'arm64-git-recovery/tests/test_assemble_full_release.py',
    'arm64-git-recovery/scripts/package-qualified-native-gcc-libs.ps1',
    'arm64-git-recovery/scripts/package-qualified-native-grep-v2.ps1',
    'arm64-git-recovery/scripts/write-qualified-utilities-v4.ps1',
    'arm64-git-recovery/scripts/prepare-audit-input-v13.ps1',
    'arm64-git-recovery/scripts/write-operational-prefix-lineage.ps1',
    'arm64-git-recovery/scripts/write-provider-enforcement-v5.ps1',
    'arm64-git-recovery/scripts/write-provider-enforcement-v6.ps1',
    'arm64-git-recovery/native-packaging/compression-policy/makepkg-compression-policy.sh',
    'arm64-git-recovery/native-packaging/compression-policy/makepkg-compression.sh',
    'arm64-git-recovery/native-packaging/compression-policy/with-makepkg-compression.sh'
)

$output = Join-Path $Root 'provider-rejection-enforcement-v6.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'grep-provider-admitted-gettext-failure-and-rejections-enforced'
    supersedes = [ordered]@{
        path = $v5
        sha256 = Get-Hash $v5
    }
    completed_provider_intake = [ordered]@{
        grep_export = [ordered]@{
            path = $grepExport
            sha256 = Get-Hash $grepExport
        }
        grep_handoff = [ordered]@{
            path = $grepHandoff
            sha256 = Get-Hash $grepHandoff
        }
        utilities_export = [ordered]@{
            path = $utilitiesExport
            sha256 = Get-Hash $utilitiesExport
        }
        utilities_disposition = [ordered]@{
            path = $utilitiesDisposition
            sha256 = Get-Hash $utilitiesDisposition
        }
    }
    gettext_failure = [ordered]@{
        path = $failure
        sha256 = Get-Hash $failure
        success_export = $null
        old_revocation_remains_controlling = $true
    }
    operational_prefix_lineage = [ordered]@{
        path = $prefixLineage
        sha256 = Get-Hash $prefixLineage
        curl_and_tcl_require_source_rebuilds = $true
    }
    compression_policy = [ordered]@{
        handoff = [ordered]@{
            path = $compressionHandoff
            sha256 = Get-Hash $compressionHandoff
        }
        jobs = 1
        installed_makepkg_modified = $false
    }
    next_audit = [ordered]@{
        input = Join-Path $Root 'input-v13-revoked-free.json'
        report = Join-Path $Root 'audit-v13-revoked-free.json'
        expected_incomplete = $true
    }
    maintained_source = @(
        $sourcePaths | ForEach-Object {
            $path = Join-Path $repoRoot ($_ -replace '/', '\')
            [ordered]@{
                path = $_
                sha256 = Get-Hash $path
            }
        }
    )
    controls = [ordered]@{
        grep_binary_bytes_changed = $false
        failed_gettext_attempt_promoted = $false
        revoked_gettext_re_admitted = $false
        curl_or_tcl_repack_claimed = $false
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
