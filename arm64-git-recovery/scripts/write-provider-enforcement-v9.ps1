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

$v8 = Join-Path $Root 'provider-rejection-enforcement-v8.json'
$input = Join-Path $Root 'input-v13-revoked-free.json'
$audit = Join-Path $Root 'audit-v13-revoked-free.json'
$bashRejection = Join-Path $Root 'bash-packaged-candidate-v5\admission-rejection.json'
$attemptDisposition = Join-Path $Root 'bash-package-attempts-v1\disposition.json'
$auditAttemptDisposition = Join-Path $Root 'bash-audit-attempt-v1\disposition.json'

Assert-FileHash -Path $v8 -Expected 'f6bf7b9e1e9d8f2002bf0284e073ba1dc3a4e31723c77b73cd89459614e42c41'
Assert-FileHash -Path $input -Expected 'b203df815d45c0ca4e6b83be642afef13564db1234b52a4d5da6e1c794a5bbe4'
Assert-FileHash -Path $audit -Expected '107945ceb42bd4359512e1a429a46fc2363ea969cb0bb203bb4ecf8f7b739779'
Assert-FileHash -Path $bashRejection -Expected '11bf138053d4fc0aca50c4de72332d987fe9cb683b9a9fb6e03aae9861e25dd0'

$auditData = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
$rejection = Get-Content -Raw -LiteralPath $bashRejection | ConvertFrom-Json
if ($auditData.status -ne 'incomplete' -or
    $auditData.shipping_payload_status -ne 'incomplete' -or
    @($auditData.blockers | Where-Object { $_ -eq 'provider-not-supplied:bash' }).Count -ne 1 -or
    $rejection.controls.failed_candidate_admitted -ne $false) {
    throw 'Current audit or Bash package rejection no longer preserves the admission gate'
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

$output = Join-Path $Root 'provider-rejection-enforcement-v9.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'native-provider-audit-v13-bash-candidate-excluded-enforced'
    supersedes = [ordered]@{
        path = $v8
        sha256 = Get-Hash $v8
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
    }
    bash_candidate = [ordered]@{
        rejection = [ordered]@{
            path = $bashRejection
            sha256 = Get-Hash $bashRejection
        }
        attempt_disposition = [ordered]@{
            path = $attemptDisposition
            sha256 = Get-Hash $attemptDisposition
        }
        package_bytes_preserved = $true
        release_eligible = $false
        required_rebuild_change = 'canonical /usr/share/locale localedir'
    }
    rejected_audit_attempt = [ordered]@{
        path = $auditAttemptDisposition
        sha256 = Get-Hash $auditAttemptDisposition
        assembler_gate_preserved = $true
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
        private_locale_prefix_waived = $false
        bash_executable_rewritten = $false
        bash_candidate_reported_as_qualified = $false
        rejected_bash_export_supplied_to_current_audit = $false
        failed_gettext_attempt_promoted = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
