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

function Assert-Hash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or
        (Get-Hash $Path) -ne $Expected) {
        throw "Pinned final receipt changed: $Path"
    }
}

$v10 = Join-Path $Root 'provider-rejection-enforcement-v10.json'
$input = Join-Path $Root 'input-v16-revoked-free.json'
$audit = Join-Path $Root 'audit-v16-revoked-free.json'
Assert-Hash $v10 '161470f98727675cca608b4751a907e7c5f8df6291d7273f3b65895063400849'
Assert-Hash $input '6d5f7e9c90656b37223684f69937f4d69af846ad967c81ab509273d4ebfd6093'
Assert-Hash $audit '8cc6e5fc3ded391e545c699a1717f4245a714034573cf643fc6b04dd5880f3f1'

$auditData = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
if ($auditData.status -ne 'incomplete' -or
    @($auditData.blockers).Count -ne 82 -or
    $auditData.selected_package_count -ne 63 -or
    $auditData.payload_file_count -ne 16632 -or
    $auditData.classification_counts.native_pe_arm64 -ne 266) {
    throw 'Final audit v16 identity changed.'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourceFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'arm64-git-recovery') `
        -Recurse -File |
        Where-Object {
            $_.FullName -notmatch '\\__pycache__\\' -and
            $_.Extension -in '.ps1', '.py', '.json', '.md', '.in', '.sh'
        }
)
$output = Join-Path $Root 'provider-rejection-enforcement-v11.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}

[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'native-provider-audit-v16-final-source-and-validation-enforced'
    supersedes = [ordered]@{
        path = $v10
        sha256 = Get-Hash $v10
    }
    current_audit = [ordered]@{
        input = [ordered]@{ path = $input; sha256 = Get-Hash $input }
        report = [ordered]@{ path = $audit; sha256 = Get-Hash $audit }
        blockers = 82
        selected_packages = 63
        payload_files = 16632
        native_arm64_pes = 266
        release_complete = $false
    }
    validation = [ordered]@{
        focused_unittest_cases = 32
        focused_unittest_status = 'passed'
        python_compile_status = 'passed'
        powershell_parser_status = 'passed'
        compression_shell_parser_status = 'passed'
        git_diff_check_status = 'passed'
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
        audit_incomplete_status_preserved = $true
        source_or_dependency_rebuild_performed_by_intake = $false
        provider_package_bytes_mutated_after_seal = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
