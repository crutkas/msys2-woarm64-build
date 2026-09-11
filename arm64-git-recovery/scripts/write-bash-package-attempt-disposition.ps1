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

$failedAttempts = @(
    [ordered]@{
        root = Join-Path $Root 'bash-packaged-candidate-v1'
        packages = @(
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v1\package\packages\bash-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = 'c8d458d2f1eee5ac7cee89878c659f6b78eba0044a952021056fff22a38c7632'
            },
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v1\package\packages\bash-devel-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = 'ee173793431684bf17e5c0b9b29e3d83740f7ac1dd9702cea50b938c2877fc8d'
            }
        )
        failure = (
            'Archive verification expected staged usr/share/info/dir, which ' +
            'normal makepkg purges from packaged ownership.'
        )
    },
    [ordered]@{
        root = Join-Path $Root 'bash-packaged-candidate-v2'
        packages = @(
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v2\package\packages\bash-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = '6890eee4b8ba9c69e50723f5c2bc68171bf376fd5303c2faa89904f72cf162eb'
            },
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v2\package\packages\bash-devel-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = 'f825de0ca2f3ab453b57432d521363a69d0635571b053887989560adcb1e5bfc'
            }
        )
        failure = 'Isolated native readback root lacked the required /tmp directory fixture.'
    },
    [ordered]@{
        root = Join-Path $Root 'bash-packaged-candidate-v3'
        packages = @(
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v3\package\packages\bash-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = 'e1a4a7507fa3dead0b6a4890fa1383f9953f6acf7fcbab6a0f1fa4d4aaec89c6'
            },
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v3\package\packages\bash-devel-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = '19e32f8c47d4fd531f50af080ba0cd2a1a61b1cd203ffddb20b38f1a8f81f7a0'
            }
        )
        failure = (
            'The /tmp fixture was created beside bash.exe, but MSYS root ' +
            'selection follows the runtime DLL location.'
        )
    },
    [ordered]@{
        root = Join-Path $Root 'bash-packaged-candidate-v4'
        packages = @(
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v4\package\packages\bash-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = 'd93cddcb8a5464d2935feb5c893d7a6fc2e3be826500adf12df65c5edf262bf3'
            },
            [ordered]@{
                path = Join-Path $Root 'bash-packaged-candidate-v4\package\packages\bash-devel-5.3.015-2-aarch64.pkg.tar.zst'
                sha256 = '6c82c4571250cf56a74fdf0fc4b774656a28455fa7e10b36d3081a8c4055e350'
            }
        )
        failure = (
            'Dynamic-load readback used /c drive syntax while the admitted ' +
            'runtime cohort exposes the drive under /cygdrive/c.'
        )
    }
)
foreach ($attempt in $failedAttempts) {
    foreach ($package in $attempt.packages) {
        Assert-FileHash -Path $package.path -Expected $package.sha256
    }
}

$finalRoot = Join-Path $Root 'bash-packaged-candidate-v5'
$finalHandoff = Join-Path $finalRoot 'handoff.json'
$finalRejection = Join-Path $finalRoot 'admission-rejection.json'
if (-not (Test-Path -LiteralPath $finalHandoff -PathType Leaf)) {
    throw "Final Bash packaging handoff is missing: $finalHandoff"
}
if (-not (Test-Path -LiteralPath $finalRejection -PathType Leaf)) {
    throw "Final Bash admission rejection is missing: $finalRejection"
}

$outputRoot = Join-Path $Root 'bash-package-attempts-v1'
$output = Join-Path $outputRoot 'disposition.json'
if (Test-Path -LiteralPath $outputRoot) {
    throw "Versioned Bash package-attempt disposition exists: $outputRoot"
}
New-Item -ItemType Directory -Path $outputRoot | Out-Null
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'bash-package-attempt-closed-final-candidate-rejected'
    failed_attempts = @(
        $failedAttempts | ForEach-Object {
            [ordered]@{
                root = $_.root
                packages = $_.packages
                failure = $_.failure
                provider_export_created = $false
                admitted = $false
            }
        }
    )
    completed_attempt = [ordered]@{
        root = $finalRoot
        handoff = [ordered]@{
            path = $finalHandoff
            sha256 = Get-Hash $finalHandoff
        }
        rejection = [ordered]@{
            path = $finalRejection
            sha256 = Get-Hash $finalRejection
        }
        release_eligible = $false
    }
    controls = [ordered]@{
        failed_attempt_archives_modified = $false
        failed_attempt_rebound_to_final_evidence = $false
        private_locale_prefix_waived = $false
    }
} | ConvertTo-Json -Depth 12 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
