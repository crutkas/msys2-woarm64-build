[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ExpectedV6Hash,
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

$v6 = Join-Path $Root 'provider-rejection-enforcement-v6.json'
$input = Join-Path $Root 'input-v13-revoked-free.json'
$audit = Join-Path $Root 'audit-v13-revoked-free.json'
Assert-FileHash -Path $v6 -Expected $ExpectedV6Hash

$inputData = Get-Content -Raw -LiteralPath $input | ConvertFrom-Json
$auditData = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
if ($inputData.intake_disposition.sha256 -ne $ExpectedV6Hash -or
    $auditData.status -ne 'incomplete' -or
    $auditData.shipping_payload_status -ne 'incomplete' -or
    @($auditData.blockers).Count -eq 0) {
    throw 'Audit v13 did not preserve the incomplete-release and enforcement gates'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourcePaths = @(
    'arm64-git-recovery/scripts/assemble-full-release.py',
    'arm64-git-recovery/contracts/full-release-v1.json',
    'arm64-git-recovery/docs/FULL-RELEASE-ASSEMBLY.md',
    'arm64-git-recovery/tests/test_assemble_full_release.py',
    'arm64-git-recovery/scripts/package-qualified-native-grep-v2.ps1',
    'arm64-git-recovery/scripts/write-qualified-utilities-v4.ps1',
    'arm64-git-recovery/scripts/prepare-audit-input-v13.ps1',
    'arm64-git-recovery/scripts/write-provider-enforcement-v6.ps1',
    'arm64-git-recovery/scripts/write-provider-enforcement-v7.ps1',
    'arm64-git-recovery/native-packaging/compression-policy/makepkg-compression-policy.sh',
    'arm64-git-recovery/native-packaging/compression-policy/makepkg-compression.sh',
    'arm64-git-recovery/native-packaging/compression-policy/with-makepkg-compression.sh'
)

$output = Join-Path $Root 'provider-rejection-enforcement-v7.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'current-native-provider-audit-v13-incomplete-enforced'
    supersedes = [ordered]@{
        path = $v6
        sha256 = Get-Hash $v6
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
        blocker_count = @($auditData.blockers).Count
        shipping_complete = $false
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
    remaining_producer_handoffs = @(
        'Truthful signed-source gettext 1.0-1 replacement and consistent network/Python closure supersessions.',
        'Current Git cohort rebuilt against the genuine libpcre2-8-0.dll provider.',
        'Pinned-source libcurl rebuilt without the private operational CURL_BINDIR.',
        'Pinned-source Tcl rebuilt without private compiled installation roots.',
        'Current d70-qualified replacements for findutils, sed, iconv, and gettext-runtime surfaces.',
        'Final qualified Bash/Coreutils provider handoffs after their owners complete acceptance.',
        'User-approved managed GCM admission evidence and remaining self-hosting providers.'
    )
    controls = [ordered]@{
        release_archive_emitted = $false
        incomplete_input_reported_as_complete = $false
        failed_gettext_attempt_promoted = $false
        pcre2_dll_renamed_or_aliased = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
