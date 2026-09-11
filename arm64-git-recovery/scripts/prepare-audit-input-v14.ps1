[CmdletBinding()]
param(
    [string]$Root = 'C:\ap11-native-provider-intake',
    [string]$OutputPath = 'C:\ap11-native-provider-intake\input-v14-revoked-free.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    $actual = Get-Hash $Path
    if ($actual -ne $Expected) {
        throw "Hash mismatch for ${Path}: expected $Expected, got $actual"
    }
}

$priorInput = Join-Path $Root 'input-v13-revoked-free.json'
$enforcement = Join-Path $Root 'provider-rejection-enforcement-v9.json'
$bashExport = Join-Path $Root 'bash-qualified-d70-v1\export.json'
$bashHandoff = Join-Path $Root 'bash-qualified-d70-v1\handoff.json'
$bashSupersession = Join-Path $Root (
    'bash-qualified-d70-v1\rejection-superseding-disposition.json'
)
$gettextExport = Join-Path $Root 'gettext-runtime-relocatable-v2\export.json'
$gettextHandoff = Join-Path $Root 'gettext-runtime-relocatable-v2\handoff.json'

Assert-FileHash $priorInput 'b203df815d45c0ca4e6b83be642afef13564db1234b52a4d5da6e1c794a5bbe4'
Assert-FileHash $enforcement '4bc2af5b2b9c5cbf517ba04b97e09c23d7012ae9e6f06fe9635848afd063163f'
Assert-FileHash $bashExport 'f485f6e2b0ee76fe44fc1b416354367c1325d46a9d30efa39a884d7f472c747c'
Assert-FileHash $bashHandoff 'a78223dc8f0bd93c8ec567e08b877a15cf4545946214df55fe78a1ea1c27e0f2'
Assert-FileHash $bashSupersession 'e7d413ec32e97fe389706482eaa75cbd415c0d987ff86a31ad72b15061255389'
Assert-FileHash $gettextExport '0bda655a0c112d96b5c9d05b8a1968877855b8b3b445a427857a51d21b36f07b'
Assert-FileHash $gettextHandoff '76e5b6701d4c1ad246a564db530e3406d9dc58a9e0af0be5f7a1fac03d7d5c4a'
if (Test-Path -LiteralPath $OutputPath) {
    throw "Versioned audit input already exists: $OutputPath"
}

$input = Get-Content -Raw -LiteralPath $priorInput | ConvertFrom-Json
$providers = @($input.provider_exports) + @(
    [ordered]@{
        role = 'native-msys-bash'
        path = $bashExport
        sha256 = Get-Hash $bashExport
    },
    [ordered]@{
        role = 'native-msys-gettext-runtime'
        path = $gettextExport
        sha256 = Get-Hash $gettextExport
    }
)
$roles = @($providers | ForEach-Object { $_.role })
if (@($roles | Group-Object | Where-Object Count -ne 1).Count -ne 0) {
    throw 'Provider roles are not unique in audit input v14.'
}

[ordered]@{
    schema = 1
    status = 'revoked-gettext-free-incomplete-provider-audit-input-v14'
    tls = $input.tls
    git_handoff = $input.git_handoff
    network_export = $input.network_export
    provider_exports = $providers
    intake_disposition = [ordered]@{
        path = $enforcement
        sha256 = Get-Hash $enforcement
    }
    utilities_disposition = $input.utilities_disposition
    bash_intake = [ordered]@{
        handoff = [ordered]@{
            path = $bashHandoff
            sha256 = Get-Hash $bashHandoff
        }
        rejection_supersession = [ordered]@{
            path = $bashSupersession
            sha256 = Get-Hash $bashSupersession
        }
    }
    gettext_runtime_intake = [ordered]@{
        handoff = [ordered]@{
            path = $gettextHandoff
            sha256 = Get-Hash $gettextHandoff
        }
        native_msys_only = $true
        revoked_mingw_gettext_replacement_claimed = $false
    }
    excluded_provider_exports = @(
        $input.excluded_provider_exports | Where-Object {
            $_.component -ne 'native-msys-gettext-runtime'
        }
    )
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $OutputPath -Encoding utf8NoBOM

Get-Item -LiteralPath $OutputPath |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
