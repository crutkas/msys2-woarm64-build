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

$input = Join-Path $Root 'input-v14-bash-candidate.json'
$bashExport = Join-Path $Root 'bash-packaged-candidate-v5\export.json'
if ((Get-Hash $input) -ne '126a08c3e2eba06126f87369a6392b9dc3c940473325cc91e17ab18b39dd548f') {
    throw 'Rejected Bash audit input hash changed'
}
if ((Get-Hash $bashExport) -ne 'd40fb7227ae08017a83cef856f062730e9a37a7a6eeb7003bb042f4bdddacb49') {
    throw 'Rejected Bash provider export hash changed'
}

$outputRoot = Join-Path $Root 'bash-audit-attempt-v1'
$output = Join-Path $outputRoot 'disposition.json'
if (Test-Path -LiteralPath $outputRoot) {
    throw "Versioned Bash audit disposition already exists: $outputRoot"
}
New-Item -ItemType Directory -Path $outputRoot | Out-Null
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'bash-candidate-audit-input-rejected-before-package-extraction'
    input = [ordered]@{
        path = $input
        sha256 = Get-Hash $input
    }
    rejected_provider_export = [ordered]@{
        path = $bashExport
        sha256 = Get-Hash $bashExport
        status = 'packaged-native-bash-candidate-rejected-private-locale-prefix'
    }
    assembler_error = 'Provider export is not admitted: export.json'
    audit_report_created = $false
    controlling_audit = [ordered]@{
        input = [ordered]@{
            path = Join-Path $Root 'input-v13-revoked-free.json'
            sha256 = 'b203df815d45c0ca4e6b83be642afef13564db1234b52a4d5da6e1c794a5bbe4'
        }
        report = [ordered]@{
            path = Join-Path $Root 'audit-v13-revoked-free.json'
            sha256 = '107945ceb42bd4359512e1a429a46fc2363ea969cb0bb203bb4ecf8f7b739779'
        }
    }
    controls = [ordered]@{
        assembler_admission_semantics_modified = $false
        rejected_status_disguised_as_admitted = $false
        rejected_candidate_added_to_controlling_audit = $false
    }
} | ConvertTo-Json -Depth 12 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
