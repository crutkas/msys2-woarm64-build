[CmdletBinding()]
param(
    [string]$Root = 'C:\ap11-native-provider-intake',
    [string]$OutputPath = 'C:\ap11-native-provider-intake\input-v16-revoked-free.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$priorInput = Join-Path $Root 'input-v15-revoked-free.json'
$priorAudit = Join-Path $Root 'audit-v15-revoked-free.json'
$libiconvExport = Join-Path $Root 'libiconv-current-d70-v1\export.json'
$libiconvHandoff = Join-Path $Root 'libiconv-current-d70-v1\handoff.json'
$pins = [ordered]@{
    $priorInput = '01440b9b82277043ebe0d86b9e89c9a4b55b4017dcf406c2319c4a3c2fe583ed'
    $priorAudit = 'ae102e3497dc4aee3af03566a1a31d69108200d61b8ac0d5f2fe3173a2f9d627'
    $libiconvExport = '54c677f8e3610c03b188ac62b01638a70d1336736e3bf4b6b4ea702835a68a51'
    $libiconvHandoff = '3955846147778fe7e8f2d428e4948f122ffb9f69e34b5c4afc42bfa2b0bff295'
}
foreach ($entry in $pins.GetEnumerator()) {
    if ((Get-Hash $entry.Key) -ne $entry.Value) {
        throw "Pinned audit input changed: $($entry.Key)"
    }
}
if (Test-Path -LiteralPath $OutputPath) {
    throw "Versioned audit input already exists: $OutputPath"
}

$input = Get-Content -Raw -LiteralPath $priorInput | ConvertFrom-Json
$providers = @($input.provider_exports) + @(
    [ordered]@{
        role = 'native-msys-libiconv'
        path = $libiconvExport
        sha256 = Get-Hash $libiconvExport
    }
)

[ordered]@{
    schema = 1
    status = 'revoked-gettext-free-incomplete-provider-audit-input-v16'
    tls = $input.tls
    git_handoff = $input.git_handoff
    network_export = $input.network_export
    provider_exports = $providers
    intake_disposition = $input.intake_disposition
    utilities_disposition = $input.utilities_disposition
    bash_intake = $input.bash_intake
    gettext_runtime_intake = $input.gettext_runtime_intake
    libiconv_intake = [ordered]@{
        handoff = [ordered]@{
            path = $libiconvHandoff
            sha256 = Get-Hash $libiconvHandoff
        }
        iconv_tool_admitted = $false
    }
    excluded_provider_exports = @(
        [ordered]@{
            component = 'native-msys-iconv-full'
            reason = (
                'libiconv runtime is admitted separately; iconv.exe remains ' +
                'excluded because it embeds the private host-bootstrap locale path.'
            )
        }
    )
    superseded_audit = [ordered]@{
        path = $priorAudit
        sha256 = Get-Hash $priorAudit
        reason = 'Qualified current-d70 libiconv runtime provider added.'
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $OutputPath -Encoding utf8NoBOM

Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
