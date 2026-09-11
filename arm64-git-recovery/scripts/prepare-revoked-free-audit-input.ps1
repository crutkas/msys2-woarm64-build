[CmdletBinding()]
param(
    [string]$OutputRoot = 'C:\ap11-native-provider-intake\revoked-free-closures-v1',
    [string]$InputPath = 'C:\ap11-native-provider-intake\input-v11-revoked-free.json'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$revokedGettextHash = '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46'
$networkSource = 'C:\ap09-ca5f\curl-packages-v2\export-12\export.json'
$pythonSource = 'C:\ap12-ca5f\python-provider-export-02\export.json'
$gitHandoff = 'C:\ap12-ca5f\git-python-handoff-02\git-package-handoff.json'

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

function Write-Json {
    param(
        [Parameter(Mandatory)]
        [object]$Value,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $Value | ConvertTo-Json -Depth 16 |
        Set-Content -LiteralPath $Path -Encoding utf8NoBOM
}

function Resolve-ArchivePath {
    param(
        [Parameter(Mandatory)]
        [string]$ExportPath,
        [Parameter(Mandatory)]
        [object]$Row
    )

    $pathProperty = $Row.PSObject.Properties['path']
    $archiveProperty = $Row.PSObject.Properties['archive']
    $path = if ($null -ne $pathProperty) {
        [string]$pathProperty.Value
    }
    elseif ($null -ne $archiveProperty) {
        [string]$archiveProperty.Value
    }
    else {
        throw 'Provider package row has no archive path'
    }
    if (-not [IO.Path]::IsPathRooted($path)) {
        $path = Join-Path (Split-Path -Parent $ExportPath) $path
    }
    return $path
}

function Get-PackageName {
    param([Parameter(Mandatory)][object]$Row)

    foreach ($propertyName in 'packageName', 'name') {
        $property = $Row.PSObject.Properties[$propertyName]
        if ($null -ne $property -and [string]$property.Value) {
            return [string]$property.Value
        }
    }
    throw 'Provider package row has no package name'
}

function Select-RevokedFreePackages {
    param(
        [Parameter(Mandatory)]
        [string]$ExportPath,
        [Parameter(Mandatory)]
        [object]$Export
    )

    $result = @()
    $rejected = @()
    foreach ($row in $Export.packages) {
        $name = Get-PackageName -Row $row
        $archive = Resolve-ArchivePath -ExportPath $ExportPath -Row $row
        Assert-FileHash -Path $archive -Expected ([string]$row.sha256)
        $record = [ordered]@{
            name = $name
            path = $archive
            sha256 = [string]$row.sha256
        }
        if ($record.sha256 -eq $revokedGettextHash) {
            if ($name -ne 'mingw-w64-aarch64-gettext') {
                throw "Revoked hash has unexpected package identity: $name"
            }
            $rejected += $record
        }
        else {
            $result += $record
        }
    }
    if ($rejected.Count -ne 1) {
        throw "Expected exactly one revoked gettext row, found $($rejected.Count)"
    }
    return [ordered]@{
        retained = $result
        rejected = $rejected
    }
}

Assert-FileHash -Path $networkSource -Expected '546d8ca66282b89803d6423f36db1f562fadf759e8d4a7e11870cb485ea84dd8'
Assert-FileHash -Path $pythonSource -Expected 'ce20122f2773a5ecde625db5cb58849daf8b66c7f7cff750fee8b5e1aa98fff3'
Assert-FileHash -Path $gitHandoff -Expected '947cdb44357f6e6639b0ff87c1b4299f53073477ff9cb5ed8e30b276ed54d911'

if (Test-Path -LiteralPath $OutputRoot) {
    throw "Versioned output root already exists: $OutputRoot"
}
if (Test-Path -LiteralPath $InputPath) {
    throw "Versioned audit input already exists: $InputPath"
}
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

$network = Get-Content -Raw -LiteralPath $networkSource | ConvertFrom-Json
$python = Get-Content -Raw -LiteralPath $pythonSource | ConvertFrom-Json
$networkSelection = Select-RevokedFreePackages -ExportPath $networkSource -Export $network
$pythonSelection = Select-RevokedFreePackages -ExportPath $pythonSource -Export $python

$networkOutput = Join-Path $OutputRoot 'network-export.json'
Write-Json -Path $networkOutput -Value ([ordered]@{
    schema = 1
    status = 'network-provider-revoked-gettext-removed-incomplete'
    generated_utc = [DateTime]::UtcNow.ToString('o')
    target = $network.target
    pinned_recipe = $network.pinned_recipe
    source_export = [ordered]@{
        path = $networkSource
        sha256 = Get-Hash $networkSource
    }
    rejected_archive = $networkSelection.rejected[0]
    packages = $networkSelection.retained
    ownership_entries = $network.ownership_entries
    variant_policy = $network.variant_policy
    closure_complete = $false
    missing_replacement = 'truthful mingw-w64-aarch64-gettext 1.0-1'
})

$pythonOutput = Join-Path $OutputRoot 'python-export.json'
Write-Json -Path $pythonOutput -Value ([ordered]@{
    schema = 1
    status = 'python-provider-revoked-gettext-removed-incomplete'
    generatedUtc = [DateTime]::UtcNow.ToString('o')
    target = $python.target
    pinnedRecipe = $python.pinnedRecipe
    maintainedPatch = $python.maintainedPatch
    source_export = [ordered]@{
        path = $pythonSource
        sha256 = Get-Hash $pythonSource
    }
    rejected_archive = $pythonSelection.rejected[0]
    packages = $pythonSelection.retained
    packageCount = $pythonSelection.retained.Count
    closure_complete = $false
    missing_replacement = 'truthful mingw-w64-aarch64-gettext 1.0-1'
    policy = @(
        'All retained package archives are byte-for-byte source export identities.',
        'The rejected gettext archive is absent from this closure.',
        'Dependency gaps caused by its removal remain audit blockers.'
    )
})

$providers = @(
    [ordered]@{
        role = 'native-msys-qualified-archives'
        path = 'C:\ap11-native-provider-intake\qualified-archives-v1\export.json'
        sha256 = '096f070a7afc477c30505d5280b8fa592e566b9f05ef8e41872c25b58e8f5811'
    },
    [ordered]@{
        role = 'native-git-helpers'
        path = 'C:\ap11-dcb\git-helpers-01\export-04\export.json'
        sha256 = '43500ca143948e0295ec2c7becf2e2e3bda39e9304f8ed79b03e1b487212829e'
    },
    [ordered]@{
        role = 'native-msys-ncurses'
        path = 'C:\ap11-native-provider-intake\ncurses-v2\export.json'
        sha256 = '6857ba52e2004b0c7592baa2e2a517c824f54bbfbb7fe2c41b1f93b3415caafd'
    },
    [ordered]@{
        role = 'native-msys-terminal-libraries'
        path = 'C:\ap11-native-provider-intake\terminal-libraries-v2\export.json'
        sha256 = '87f290f0bfc7a2dca0c9fe613f8a9e966b3c167be38712ac7fcc4c440b774af7'
    },
    [ordered]@{
        role = 'native-python'
        path = $pythonOutput
        sha256 = Get-Hash $pythonOutput
    },
    [ordered]@{
        role = 'native-msys-runtime-d70'
        path = 'C:\ap11-native-provider-intake\msys2-runtime-d70-v3\export.json'
        sha256 = '7913b174303df04d4840516e3d1181e3ab7c67efb1b9e151cac09c8c456f0418'
    },
    [ordered]@{
        role = 'native-msys-qualified-utilities'
        path = 'C:\ap11-native-provider-intake\qualified-utilities-v2\export.json'
        sha256 = Get-Hash 'C:\ap11-native-provider-intake\qualified-utilities-v2\export.json'
    },
    [ordered]@{
        role = 'native-msys-qualified-utility-libraries'
        path = 'C:\ap11-native-provider-intake\qualified-utility-libraries-v1\export.json'
        sha256 = '358d5405fa1f5a07c5b2ee4e1e424b61385cbea017b71e32d82f5be71438e150'
    },
    [ordered]@{
        role = 'native-msys-make'
        path = 'C:\ap11-native-provider-intake\qualified-make-d70-v1\export.json'
        sha256 = 'a4b12fe4afc672d05cc9518a013359e72c0c28fe1a8ae2e68a475268ab4f4a71'
    },
    [ordered]@{
        role = 'native-msys-gcc-libs'
        path = 'C:\ap11-native-provider-intake\gcc-libs-v1\export.json'
        sha256 = Get-Hash 'C:\ap11-native-provider-intake\gcc-libs-v1\export.json'
    }
)
foreach ($provider in $providers) {
    Assert-FileHash -Path $provider.path -Expected $provider.sha256
}

Write-Json -Path $InputPath -Value ([ordered]@{
    schema = 1
    status = 'revoked-gettext-free-incomplete-provider-audit-input'
    tls = 'openssl'
    git_handoff = [ordered]@{
        path = $gitHandoff
        sha256 = Get-Hash $gitHandoff
    }
    network_export = [ordered]@{
        path = $networkOutput
        sha256 = Get-Hash $networkOutput
    }
    provider_exports = $providers
    intake_disposition = [ordered]@{
        path = 'C:\ap11-native-provider-intake\provider-rejection-enforcement-v3.json'
        sha256 = Get-Hash 'C:\ap11-native-provider-intake\provider-rejection-enforcement-v3.json'
    }
    excluded_provider_exports = @(
        [ordered]@{
            component = 'native-msys-iconv-full'
            reason = 'iconv.exe has a compiled private locale prefix and the clean libiconv split lacks current d70 qualification'
        },
        [ordered]@{
            component = 'native-msys-gettext-runtime'
            reason = 'msys-intl-8.dll has a compiled private locale prefix and the clean libasprintf split lacks current d70 qualification'
        }
    )
})

$handoffPath = Join-Path $OutputRoot 'handoff.json'
Write-Json -Path $handoffPath -Value ([ordered]@{
    schema = 1
    status = 'revoked-gettext-free-audit-input-prepared'
    input = [ordered]@{
        path = $InputPath
        sha256 = Get-Hash $InputPath
    }
    network_export = [ordered]@{
        path = $networkOutput
        sha256 = Get-Hash $networkOutput
        retained_packages = $networkSelection.retained.Count
    }
    python_export = [ordered]@{
        path = $pythonOutput
        sha256 = Get-Hash $pythonOutput
        retained_packages = $pythonSelection.retained.Count
    }
    removed_archive = $networkSelection.rejected[0]
    removed_consistently_from_network_and_python = $true
    authoritative_release_input = $false
    release_archive_emitted = $false
})

Get-Item -LiteralPath $networkOutput, $pythonOutput, $InputPath, $handoffPath |
    Select-Object FullName, Length
