[CmdletBinding()]
param(
    [string]$Root = 'C:\ap11-native-provider-intake',
    [string]$OutputPath = 'C:\ap11-native-provider-intake\input-v15-revoked-free.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$priorInput = Join-Path $Root 'input-v14-revoked-free.json'
$priorAudit = Join-Path $Root 'audit-v14-revoked-free.json'
if ((Get-Hash $priorInput) -ne
    '6c995bc310b6dec863d85542af28f0673f642cffff600ef20d5843b9a040c0c6') {
    throw 'Audit input v14 changed.'
}
if ((Get-Hash $priorAudit) -ne
    'baa7eda07eeb2c7fc80dd53aa4c25300cafe6a2e7d6d700f85966dceb72e7649') {
    throw 'Audit v14 changed.'
}
if (Test-Path -LiteralPath $OutputPath) {
    throw "Versioned audit input already exists: $OutputPath"
}

$input = Get-Content -Raw -LiteralPath $priorInput | ConvertFrom-Json
[ordered]@{
    schema = 1
    status = 'revoked-gettext-free-incomplete-provider-audit-input-v15'
    tls = $input.tls
    git_handoff = $input.git_handoff
    network_export = $input.network_export
    provider_exports = $input.provider_exports
    intake_disposition = $input.intake_disposition
    utilities_disposition = $input.utilities_disposition
    bash_intake = $input.bash_intake
    gettext_runtime_intake = $input.gettext_runtime_intake
    excluded_provider_exports = $input.excluded_provider_exports
    superseded_audit = [ordered]@{
        path = $priorAudit
        sha256 = Get-Hash $priorAudit
        reason = (
            'The audit indexed DLL providers only and therefore reported ' +
            'qualified Bash loadables importing bash.exe as unresolved.'
        )
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $OutputPath -Encoding utf8NoBOM

Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
