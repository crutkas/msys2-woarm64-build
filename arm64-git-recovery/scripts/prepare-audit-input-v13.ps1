[CmdletBinding()]
param(
    [string]$Root = 'C:\ap11-native-provider-intake',
    [string]$OutputPath = 'C:\ap11-native-provider-intake\input-v13-revoked-free.json'
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

$priorInput = Join-Path $Root 'input-v12-revoked-free.json'
$utilitiesExport = Join-Path $Root 'qualified-utilities-v4\export.json'
$utilitiesDisposition = Join-Path $Root (
    'qualified-utilities-v4\provider-disposition.json'
)
$enforcement = Join-Path $Root 'provider-rejection-enforcement-v6.json'

Assert-FileHash -Path $priorInput -Expected 'ba09e870c6262701d295b1cf47247ef27f42dfb30cce29d2354b22b76f5f7618'
if (Test-Path -LiteralPath $OutputPath) {
    throw "Versioned audit input already exists: $OutputPath"
}

$input = Get-Content -Raw -LiteralPath $priorInput | ConvertFrom-Json
$providers = @(
    $input.provider_exports | ForEach-Object {
        if ($_.role -eq 'native-msys-qualified-utilities') {
            [ordered]@{
                role = $_.role
                path = $utilitiesExport
                sha256 = Get-Hash $utilitiesExport
            }
        }
        else {
            $_
        }
    }
)
$utilityRows = @($providers | Where-Object {
    $_.role -eq 'native-msys-qualified-utilities'
})
if ($utilityRows.Count -ne 1) {
    throw "Expected exactly one utilities provider, found $($utilityRows.Count)"
}

[ordered]@{
    schema = 1
    status = 'revoked-gettext-free-incomplete-provider-audit-input-v13'
    tls = $input.tls
    git_handoff = $input.git_handoff
    network_export = $input.network_export
    provider_exports = $providers
    intake_disposition = [ordered]@{
        path = $enforcement
        sha256 = Get-Hash $enforcement
    }
    utilities_disposition = [ordered]@{
        path = $utilitiesDisposition
        sha256 = Get-Hash $utilitiesDisposition
    }
    excluded_provider_exports = $input.excluded_provider_exports
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $OutputPath -Encoding utf8NoBOM

Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
