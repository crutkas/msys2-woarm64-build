[CmdletBinding()]
param(
    [string]$Root = 'C:\ap11-native-provider-intake',
    [string]$OutputPath = 'C:\ap11-native-provider-intake\input-v17-revoked-free.json'
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
        throw "Pinned audit input changed: $Path"
    }
}

$priorInput = Join-Path $Root 'input-v16-revoked-free.json'
$priorAudit = Join-Path $Root 'audit-v16-revoked-free.json'
$iconvExport = Join-Path $Root 'iconv-current-d70-v2\export.json'
$iconvHandoff = Join-Path $Root 'iconv-current-d70-v2\handoff.json'
$iconvSupersession = Join-Path $Root (
    'iconv-current-d70-v2\excluded-iconv-superseding-disposition.json'
)
Assert-Hash $priorInput '6d5f7e9c90656b37223684f69937f4d69af846ad967c81ab509273d4ebfd6093'
Assert-Hash $priorAudit '8cc6e5fc3ded391e545c699a1717f4245a714034573cf643fc6b04dd5880f3f1'
Assert-Hash $iconvExport '152cfe8c388d698473f4ea1c6e52e9bdf271576920ea01b107b30459f370244f'
Assert-Hash $iconvHandoff '0714730e0435806540d790cbf9db1c7fa1f28b58bfccdf0c1141b79e48602f8a'
Assert-Hash $iconvSupersession 'f03a23888d92051dca5868828746cb25a5d97f120b69e1ea6f2e0de4ca9ddae7'
if (Test-Path -LiteralPath $OutputPath) {
    throw "Versioned audit input already exists: $OutputPath"
}

$input = Get-Content -Raw -LiteralPath $priorInput | ConvertFrom-Json
$providers = @($input.provider_exports) + @(
    [ordered]@{
        role = 'native-msys-iconv'
        path = $iconvExport
        sha256 = Get-Hash $iconvExport
    }
)

[ordered]@{
    schema = 1
    status = 'revoked-gettext-free-incomplete-provider-audit-input-v17'
    tls = $input.tls
    git_handoff = $input.git_handoff
    network_export = $input.network_export
    provider_exports = $providers
    intake_disposition = $input.intake_disposition
    utilities_disposition = $input.utilities_disposition
    bash_intake = $input.bash_intake
    gettext_runtime_intake = $input.gettext_runtime_intake
    libiconv_intake = $input.libiconv_intake
    iconv_intake = [ordered]@{
        handoff = [ordered]@{
            path = $iconvHandoff
            sha256 = Get-Hash $iconvHandoff
        }
        excluded_predecessor_supersession = [ordered]@{
            path = $iconvSupersession
            sha256 = Get-Hash $iconvSupersession
        }
        existing_admitted_libiconv_superseded = $false
    }
    excluded_provider_exports = @()
    superseded_audit = [ordered]@{
        path = $priorAudit
        sha256 = Get-Hash $priorAudit
        reason = 'Fresh canonical current-d70 iconv provider added.'
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $OutputPath -Encoding utf8NoBOM

Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
