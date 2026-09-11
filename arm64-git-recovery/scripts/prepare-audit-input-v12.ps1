[CmdletBinding()]
param(
    [string]$PriorInput = 'C:\ap11-native-provider-intake\input-v11-revoked-free.json',
    [string]$OutputPath = 'C:\ap11-native-provider-intake\input-v12-revoked-free.json'
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

Assert-FileHash -Path $PriorInput -Expected '8245a14d138e9b60689d2900300854638598039a1a0838868497861043dbb0b8'
if (Test-Path -LiteralPath $OutputPath) {
    throw "Versioned audit input already exists: $OutputPath"
}

$utilitiesExport = 'C:\ap11-native-provider-intake\qualified-utilities-v3\export.json'
$utilitiesDisposition = (
    'C:\ap11-native-provider-intake\qualified-utilities-v3\' +
    'provider-disposition.json'
)
$input = Get-Content -Raw -LiteralPath $PriorInput | ConvertFrom-Json
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

[ordered]@{
    schema = 1
    status = 'revoked-gettext-free-incomplete-provider-audit-input-v12'
    tls = $input.tls
    git_handoff = $input.git_handoff
    network_export = $input.network_export
    provider_exports = $providers
    intake_disposition = $input.intake_disposition
    utilities_disposition = [ordered]@{
        path = $utilitiesDisposition
        sha256 = Get-Hash $utilitiesDisposition
    }
    excluded_provider_exports = $input.excluded_provider_exports
} | ConvertTo-Json -Depth 12 |
    Set-Content -LiteralPath $OutputPath -Encoding utf8NoBOM

Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
