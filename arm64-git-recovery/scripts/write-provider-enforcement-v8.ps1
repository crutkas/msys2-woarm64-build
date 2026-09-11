[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ExpectedV7Hash,
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

$v7 = Join-Path $Root 'provider-rejection-enforcement-v7.json'
$input = Join-Path $Root 'input-v13-revoked-free.json'
$audit = Join-Path $Root 'audit-v13-revoked-free.json'
$attemptDisposition = Join-Path $Root 'qualified-grep-attempts-v1\disposition.json'

Assert-FileHash -Path $v7 -Expected $ExpectedV7Hash
Assert-FileHash -Path $input -Expected 'b203df815d45c0ca4e6b83be642afef13564db1234b52a4d5da6e1c794a5bbe4'
Assert-FileHash -Path $audit -Expected '107945ceb42bd4359512e1a429a46fc2363ea969cb0bb203bb4ecf8f7b739779'

$auditData = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
$disposition = Get-Content -Raw -LiteralPath $attemptDisposition | ConvertFrom-Json
if ($auditData.status -ne 'incomplete' -or
    @($auditData.blockers).Count -ne 96 -or
    $auditData.selected_package_count -ne 60 -or
    $disposition.controls.only_final_v4_provider_admitted -ne $true) {
    throw 'Final audit or grep-attempt disposition does not match the completed intake'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourceFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'arm64-git-recovery\scripts') -File |
        Where-Object Extension -in '.ps1', '.py'
    Get-Item -LiteralPath (
        Join-Path $repoRoot 'arm64-git-recovery\contracts\full-release-v1.json'
    )
    Get-Item -LiteralPath (
        Join-Path $repoRoot 'arm64-git-recovery\docs\FULL-RELEASE-ASSEMBLY.md'
    )
    Get-Item -LiteralPath (
        Join-Path $repoRoot 'arm64-git-recovery\tests\test_assemble_full_release.py'
    )
    Get-ChildItem -LiteralPath (
        Join-Path $repoRoot 'arm64-git-recovery\native-packaging\compression-policy'
    ) -File
    Get-ChildItem -LiteralPath (
        Join-Path $repoRoot 'arm64-git-recovery\native-packaging\qualified-utility'
    ) -File
)

$output = Join-Path $Root 'provider-rejection-enforcement-v8.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'native-provider-intake-v13-incomplete-finally-enforced'
    supersedes = [ordered]@{
        path = $v7
        sha256 = Get-Hash $v7
    }
    current_audit = [ordered]@{
        input = [ordered]@{
            path = $input
            sha256 = Get-Hash $input
        }
        report = [ordered]@{
            path = $audit
            sha256 = Get-Hash $audit
        }
        blockers = @($auditData.blockers).Count
        selected_packages = $auditData.selected_package_count
        payload_files = $auditData.payload_file_count
        native_arm64_pes = $auditData.classification_counts.native_pe_arm64
        shipping_status = $auditData.shipping_payload_status
    }
    grep_attempt_disposition = [ordered]@{
        path = $attemptDisposition
        sha256 = Get-Hash $attemptDisposition
    }
    maintained_source = @(
        $sourceFiles | Sort-Object FullName -Unique | ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($repoRoot.Length + 1).Replace('\', '/')
                sha256 = Get-Hash $_.FullName
            }
        }
    )
    controls = [ordered]@{
        release_archive_emitted = $false
        incomplete_input_reported_as_complete = $false
        failed_gettext_attempt_promoted = $false
        rejected_grep_attempt_admitted = $false
        pcre2_dll_renamed_or_aliased = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
