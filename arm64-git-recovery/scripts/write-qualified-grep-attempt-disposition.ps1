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

$attempts = @(
    [ordered]@{
        version = 'qualified-grep-v2'
        archive = Join-Path $Root (
            'qualified-grep-v2\package\packages\grep-1~3.0-7-aarch64.pkg.tar.zst'
        )
        sha256 = 'a57e36cbfd68e6fdbfc1f0f3220fbd79fe41928be6767c2668c816dbe36e3134'
        failure = 'qualification verifier incorrectly expected uncompressed man-page paths'
    },
    [ordered]@{
        version = 'qualified-grep-v3'
        archive = Join-Path $Root (
            'qualified-grep-v3\package\packages\grep-1~3.0-7-aarch64.pkg.tar.zst'
        )
        sha256 = 'b1927455e6510a03e5cf5aae8a6e9cf077a7d96c5523973f96c9e4c740c89ed0'
        failure = 'qualification verifier incorrectly expected colon-form epoch in .PKGINFO'
    }
)
foreach ($attempt in $attempts) {
    Assert-FileHash -Path $attempt.archive -Expected $attempt.sha256
}

$final = [ordered]@{
    package = Join-Path $Root (
        'qualified-grep-v4\package\packages\grep-1~3.0-7-aarch64.pkg.tar.zst'
    )
    package_sha256 = '86f320e25ad00fb3cff3b53dea4740e1b69d179b385d67e717ce8cb8bff6be17'
    export = Join-Path $Root 'qualified-grep-v4\export.json'
    export_sha256 = '3287360cbd4a04fc77709dbac86e2547f0415b04270e3f4d1dc426fb75083ab6'
    handoff = Join-Path $Root 'qualified-grep-v4\handoff.json'
    handoff_sha256 = '8e9ab6e1e54c24f7044ec2c25b6dfff116f54c9a3c18111f052c7941e8b51b25'
}
Assert-FileHash -Path $final.package -Expected $final.package_sha256
Assert-FileHash -Path $final.export -Expected $final.export_sha256
Assert-FileHash -Path $final.handoff -Expected $final.handoff_sha256

$outputRoot = Join-Path $Root 'qualified-grep-attempts-v1'
$output = Join-Path $outputRoot 'disposition.json'
if (Test-Path -LiteralPath $outputRoot) {
    throw "Versioned disposition already exists: $outputRoot"
}
New-Item -ItemType Directory -Path $outputRoot | Out-Null
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'grep-qualification-attempts-closed-final-v4-admitted'
    rejected_attempts = @(
        $attempts | ForEach-Object {
            [ordered]@{
                version = $_.version
                archive = [ordered]@{
                    path = $_.archive
                    sha256 = $_.sha256
                }
                failure = $_.failure
                provider_export_created = $false
                admitted = $false
            }
        }
    )
    admitted = [ordered]@{
        package = [ordered]@{
            path = $final.package
            sha256 = $final.package_sha256
        }
        provider_export = [ordered]@{
            path = $final.export
            sha256 = $final.export_sha256
        }
        handoff = [ordered]@{
            path = $final.handoff
            sha256 = $final.handoff_sha256
        }
    }
    controls = [ordered]@{
        rejected_attempt_archives_modified = $false
        rejected_attempts_rebound_to_final_proof = $false
        only_final_v4_provider_admitted = $true
    }
} | ConvertTo-Json -Depth 12 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
