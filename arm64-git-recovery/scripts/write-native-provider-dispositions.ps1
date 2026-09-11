[CmdletBinding()]
param(
    [string]$Root = 'C:\ap11-native-provider-intake',
    [string]$Strings = 'C:\agtc-libs-01\sdk\bin\aarch64-pc-cygwin-strings.exe'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$runtimeD70 = 'd70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d'
$oldLibraryRuntime = '1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16'

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
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($actual -ne $Expected) {
        throw "Hash mismatch for ${Path}: expected $Expected, got $actual"
    }
}

function Get-Hash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
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

function Resolve-PackagePath {
    param(
        [Parameter(Mandatory)]
        [string]$ExportPath,
        [Parameter(Mandatory)]
        [string]$PackagePath
    )

    if ([IO.Path]::IsPathRooted($PackagePath)) {
        return $PackagePath
    }
    return Join-Path (Split-Path -Parent $ExportPath) $PackagePath
}

function Get-PackageRows {
    param(
        [Parameter(Mandatory)]
        [string]$ExportPath,
        [Parameter(Mandatory)]
        [hashtable]$Names
    )

    $export = Get-Content -Raw -LiteralPath $ExportPath | ConvertFrom-Json
    $rows = @()
    foreach ($row in $export.packages) {
        $path = Resolve-PackagePath -ExportPath $ExportPath -PackagePath $row.path
        $leaf = Split-Path -Leaf $path
        $name = $Names[$leaf]
        if (-not $name) {
            $property = $row.PSObject.Properties['name']
            if ($null -ne $property) {
                $name = [string]$property.Value
            }
        }
        if (-not $name) {
            throw "No package identity mapping for $leaf"
        }
        Assert-FileHash -Path $path -Expected $row.sha256
        $rows += [ordered]@{
            name = $name
            path = $path
            sha256 = [string]$row.sha256
        }
    }
    return $rows
}

function Get-OperationalPathHits {
    param(
        [Parameter(Mandatory)]
        [object]$Package,
        [Parameter(Mandatory)]
        [string]$ScratchRoot
    )

    $destination = Join-Path $ScratchRoot $Package.name
    New-Item -ItemType Directory -Path $destination | Out-Null
    & tar -xf $Package.path -C $destination
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract $($Package.path)"
    }
    $hits = @()
    foreach ($file in Get-ChildItem -LiteralPath $destination -Recurse -File |
            Where-Object { $_.Extension -in '.exe', '.dll' }) {
        $matches = @(
            & $Strings -a $file.FullName |
                Select-String -Pattern (
                    '(?i)[A-Z]:[/\\][ -~]{1,512}' +
                    '(?:msys64[/\\]usr|mingwarm64)[/\\][ -~]{0,256}'
                ) |
                ForEach-Object { $_.Matches.Value } |
                Sort-Object -Unique
        )
        if ($matches.Count -ne 0) {
            $hits += [ordered]@{
                file = $file.FullName.Substring($destination.Length + 1).
                    Replace('\', '/')
                paths = $matches
            }
        }
    }
    return $hits
}

if (-not (Test-Path -LiteralPath $Strings -PathType Leaf)) {
    throw "Required strings tool is missing: $Strings"
}

$utilitiesV1 = Join-Path $Root 'qualified-utilities-v1\export.json'
$utilitiesHandoffV1 = Join-Path $Root 'qualified-utilities-v1\handoff.json'
$iconvV1 = Join-Path $Root 'iconv-full-v1\export.json'
$iconvHandoffV1 = Join-Path $Root 'iconv-full-v1\handoff.json'
$gettextV1 = Join-Path $Root 'gettext-runtime-v1\export.json'
$gettextHandoffV1 = Join-Path $Root 'gettext-runtime-v1\handoff.json'
$makeExport = Join-Path $Root 'qualified-make-d70-v1\export.json'
$makeHandoff = Join-Path $Root 'qualified-make-d70-v1\handoff.json'
$makeRejection = Join-Path $Root 'qualified-make-d70-v1\rejection.json'
$gccExport = Join-Path $Root 'gcc-libs-v1\export.json'
$gccHandoff = Join-Path $Root 'gcc-libs-v1\handoff.json'

Assert-FileHash -Path $utilitiesV1 -Expected '0e2cdcb4b06130289a0722a13d8694ca7630cca06776589d4fd2988a09d32866'
Assert-FileHash -Path $utilitiesHandoffV1 -Expected '050dae35d8488b0c482f484f486af4af94ec70b703b909606eb88f7154cd6cb8'
Assert-FileHash -Path $iconvV1 -Expected '9ae43a6882b04154f9cd7dd25d04cfb5122ab9e131724ffae57df5239f02de7d'
Assert-FileHash -Path $iconvHandoffV1 -Expected '35219aab23206560d08ddca20356939b94c0eb3f1ea85392a3ac0163e157cb81'
Assert-FileHash -Path $gettextV1 -Expected '5d4a7554227f618620f22747f8c44de51abbe277667ea6d827454c0f4d5c6629'
Assert-FileHash -Path $gettextHandoffV1 -Expected 'b68e2d5fa22694ed3be56c2bd846227582f936199d757f4341d2e7e95551a4c9'
Assert-FileHash -Path $makeExport -Expected 'a4b12fe4afc672d05cc9518a013359e72c0c28fe1a8ae2e68a475268ab4f4a71'
Assert-FileHash -Path $makeHandoff -Expected '815209785ce76c5991971564acbae150c473d94757bf83207ec62a3775f62dc6'
Assert-FileHash -Path $makeRejection -Expected '3ba67a0209ecd5151f4e93f62ccd173b9f4754dc9c0aece1fa3b56b79303f97a'
Assert-FileHash -Path $gccExport -Expected '2e7f2b7c8432344c8faa650e7a6a89903947719da75e938ed7d2802ec81a5bbc'
Assert-FileHash -Path $gccHandoff -Expected 'f5049294a9d6d63faad21e80e52a0f0f6a1b61f49b3d12b137aa05def9a07efc'

$utilityNames = @{
    'diffutils-3.12-1-aarch64.pkg.tar.zst' = 'diffutils'
    'findutils-4.11.0-2-aarch64.pkg.tar.zst' = 'findutils'
    'gawk-5.4.1-1-aarch64.pkg.tar.zst' = 'gawk'
    'grep-1~3.0-7-aarch64.pkg.tar.zst' = 'grep'
    'sed-4.9-1-aarch64.pkg.tar.zst' = 'sed'
}
$utilityRows = Get-PackageRows -ExportPath $utilitiesV1 -Names $utilityNames
$iconvRows = Get-PackageRows -ExportPath $iconvV1 -Names @{}
$gettextRows = Get-PackageRows -ExportPath $gettextV1 -Names @{}

$scratchRoot = Join-Path $Root 'provider-disposition-scan-temp'
if (Test-Path -LiteralPath $scratchRoot) {
    Remove-Item -LiteralPath $scratchRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $scratchRoot | Out-Null
try {
    $allRows = @($utilityRows) + @($iconvRows) + @($gettextRows)
    $scan = @{}
    foreach ($row in $allRows) {
        $key = "$($row.name):$($row.sha256)"
        $packageScratch = Join-Path $scratchRoot (
            $row.name + '-' + $row.sha256.Substring(0, 12)
        )
        New-Item -ItemType Directory -Path $packageScratch | Out-Null
        $scan[$key] = @(
            Get-OperationalPathHits -Package $row -ScratchRoot $packageScratch
        )
    }
}
finally {
    if (Test-Path -LiteralPath $scratchRoot) {
        Remove-Item -LiteralPath $scratchRoot -Recurse -Force
    }
}

$expectedAffected = @{
    findutils = $true
    sed = $true
    iconv = $true
    libintl = $true
}
foreach ($row in @($utilityRows) + @($iconvRows) + @($gettextRows)) {
    $hasHits = $scan["$($row.name):$($row.sha256)"].Count -ne 0
    $shouldHaveHits = $expectedAffected.ContainsKey($row.name)
    if ($hasHits -ne $shouldHaveHits) {
        throw "Unexpected operational-prefix result for $($row.name): hits=$hasHits"
    }
}

$utilitiesV2Root = Join-Path $Root 'qualified-utilities-v2'
$iconvV2Root = Join-Path $Root 'iconv-full-v2'
$gettextV2Root = Join-Path $Root 'gettext-runtime-v2'
foreach ($path in $utilitiesV2Root, $iconvV2Root, $gettextV2Root) {
    if (Test-Path -LiteralPath $path) {
        throw "Versioned disposition output already exists: $path"
    }
    New-Item -ItemType Directory -Path $path | Out-Null
}

$cleanUtilities = @($utilityRows | Where-Object {
    $_.name -in 'diffutils', 'gawk', 'grep'
})
$excludedUtilities = @($utilityRows | Where-Object {
    $_.name -in 'findutils', 'sed'
})
$utilitiesExportPath = Join-Path $utilitiesV2Root 'export.json'
Write-Json -Path $utilitiesExportPath -Value ([ordered]@{
    schema = 1
    status = 'qualified-current-d70-native-utility-packages-selective-exported'
    provider = 'native-msys-qualified-utilities'
    version = 'v2'
    supersedes = [ordered]@{
        path = $utilitiesV1
        sha256 = Get-Hash $utilitiesV1
    }
    runtime_cohort = [ordered]@{
        sha256 = $runtimeD70
        compatibility_with_current_d70_runtime_claimed = $true
    }
    packages = $cleanUtilities
})
$utilitiesDispositionPath = Join-Path $utilitiesV2Root 'provider-disposition.json'
Write-Json -Path $utilitiesDispositionPath -Value ([ordered]@{
    schema = 1
    status = 'qualified-utilities-v1-selectively-superseded'
    source_handoff = [ordered]@{
        path = $utilitiesHandoffV1
        sha256 = Get-Hash $utilitiesHandoffV1
    }
    provider_export = [ordered]@{
        path = $utilitiesExportPath
        sha256 = Get-Hash $utilitiesExportPath
    }
    retained_unchanged = $cleanUtilities
    excluded = @(
        $excludedUtilities | ForEach-Object {
            [ordered]@{
                name = $_.name
                archive = $_
                evidence = $scan["$($_.name):$($_.sha256)"]
                reason = 'compiled-private-operational-prefix'
            }
        }
    )
    remaining_producer_handoffs = @(
        [ordered]@{
            component = 'findutils'
            version = '4.11.0-2'
            requirements = @(
                'Build with installed locale lookup rooted at /usr/share/locale.',
                'Build locate with the package-owned database path /var/locatedb.',
                'Publish source/recipe hashes, installed payload manifest, current d70 runtime binding, and native find/locate/xargs readbacks.'
            )
        },
        [ordered]@{
            component = 'sed'
            version = '4.9-1'
            requirements = @(
                'Build with installed locale lookup rooted at /usr/share/locale.',
                'Publish source/recipe hashes, installed payload manifest, current d70 runtime binding, and native sed readback.'
            )
        }
    )
    controls = [ordered]@{
        package_archives_modified = $false
        producer_stages_modified = $false
        release_archive_emitted = $false
    }
})

$cleanIconv = $iconvRows | Where-Object { $_.name -eq 'libiconv' }
$iconvCandidatePath = Join-Path $iconvV2Root 'candidate-export.json'
Write-Json -Path $iconvCandidatePath -Value ([ordered]@{
    schema = 1
    status = 'clean-native-msys-libiconv-candidate-current-d70-unverified'
    provider = 'native-msys-iconv'
    version = 'v2-candidate'
    source_export = [ordered]@{
        path = $iconvV1
        sha256 = Get-Hash $iconvV1
    }
    runtime_cohort = [ordered]@{
        qualified_sha256 = $oldLibraryRuntime
        current_d70_compatibility_claimed = $false
    }
    packages = @($cleanIconv)
})
$iconvDispositionPath = Join-Path $iconvV2Root 'provider-disposition.json'
$affectedIconv = $iconvRows | Where-Object { $_.name -eq 'iconv' }
$iconvDevel = $iconvRows | Where-Object { $_.name -eq 'libiconv-devel' }
Write-Json -Path $iconvDispositionPath -Value ([ordered]@{
    schema = 1
    status = 'iconv-full-v1-not-currently-admitted'
    source_handoff = [ordered]@{
        path = $iconvHandoffV1
        sha256 = Get-Hash $iconvHandoffV1
    }
    clean_candidate = [ordered]@{
        path = $iconvCandidatePath
        sha256 = Get-Hash $iconvCandidatePath
    }
    excluded = @(
        [ordered]@{
            name = 'iconv'
            archive = $affectedIconv
            evidence = $scan["iconv:$($affectedIconv.sha256)"]
            reason = 'compiled-private-locale-prefix'
        },
        [ordered]@{
            name = 'libiconv-devel'
            archive = $iconvDevel
            reason = 'development-split-not-shipped'
        }
    )
    remaining_producer_handoff = [ordered]@{
        component = 'iconv'
        version = '1.19-1'
        requirements = @(
            'Replace the iconv executable with bytes whose locale lookup is rooted at /usr/share/locale.',
            'Requalify libiconv and iconv against runtime d70 as one package cohort.',
            'Publish source/recipe hashes, complete split ownership, exact payload hashes, and native iconv conversion readback.'
        )
    }
    release_admitted = $false
})

$cleanGettext = $gettextRows | Where-Object { $_.name -eq 'libasprintf' }
$gettextCandidatePath = Join-Path $gettextV2Root 'candidate-export.json'
Write-Json -Path $gettextCandidatePath -Value ([ordered]@{
    schema = 1
    status = 'clean-native-msys-libasprintf-candidate-current-d70-unverified'
    provider = 'native-msys-gettext-runtime'
    version = 'v2-candidate'
    source_export = [ordered]@{
        path = $gettextV1
        sha256 = Get-Hash $gettextV1
    }
    runtime_cohort = [ordered]@{
        qualified_sha256 = $oldLibraryRuntime
        current_d70_compatibility_claimed = $false
    }
    packages = @($cleanGettext)
})
$gettextDispositionPath = Join-Path $gettextV2Root 'provider-disposition.json'
$affectedGettext = $gettextRows | Where-Object { $_.name -eq 'libintl' }
Write-Json -Path $gettextDispositionPath -Value ([ordered]@{
    schema = 1
    status = 'gettext-runtime-v1-not-currently-admitted'
    source_handoff = [ordered]@{
        path = $gettextHandoffV1
        sha256 = Get-Hash $gettextHandoffV1
    }
    clean_candidate = [ordered]@{
        path = $gettextCandidatePath
        sha256 = Get-Hash $gettextCandidatePath
    }
    excluded = @(
        [ordered]@{
            name = 'libintl'
            archive = $affectedGettext
            evidence = $scan["libintl:$($affectedGettext.sha256)"]
            reason = 'compiled-private-locale-prefix'
        }
    )
    remaining_producer_handoff = [ordered]@{
        component = 'gettext-runtime'
        version = '0.22.5-1'
        requirements = @(
            'Replace msys-intl-8.dll with bytes whose locale lookup is rooted at /usr/share/locale.',
            'Requalify libintl and libasprintf against runtime d70 as one package cohort.',
            'Publish source/recipe hashes, complete split ownership, exact payload hashes, and native libintl/libasprintf consumer readbacks.'
        )
    }
    release_admitted = $false
})

$makeDispositionPath = Join-Path $Root (
    'qualified-make-d70-v1\rejection-superseding-disposition-v1.json'
)
if (Test-Path -LiteralPath $makeDispositionPath) {
    throw "Make disposition already exists: $makeDispositionPath"
}
$makeArchive = (Get-Content -Raw -LiteralPath $makeExport | ConvertFrom-Json).packages[0]
Write-Json -Path $makeDispositionPath -Value ([ordered]@{
    schema = 1
    status = 'provisional-make-relocation-rejection-superseded'
    superseded_rejection = [ordered]@{
        path = $makeRejection
        sha256 = Get-Hash $makeRejection
    }
    reason = (
        'The rejected strings are source/compiler provenance, not private ' +
        'operational installation prefixes. The maintained policy now blocks ' +
        'private msys64/usr and mingwarm64 roots while allowing source paths.'
    )
    admitted_provider = [ordered]@{
        export = [ordered]@{
            path = $makeExport
            sha256 = Get-Hash $makeExport
        }
        handoff = [ordered]@{
            path = $makeHandoff
            sha256 = Get-Hash $makeHandoff
        }
        archive = $makeArchive
    }
    controls = [ordered]@{
        original_rejection_modified = $false
        binary_rebuilt = $false
        current_d70_readback_passed = $true
        release_archive_emitted = $false
    }
})

$sourceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourcePaths = @(
    'arm64-git-recovery/scripts/assemble-full-release.py',
    'arm64-git-recovery/contracts/full-release-v1.json',
    'arm64-git-recovery/docs/FULL-RELEASE-ASSEMBLY.md',
    'arm64-git-recovery/tests/test_assemble_full_release.py',
    'arm64-git-recovery/scripts/package-qualified-native-make.ps1',
    'arm64-git-recovery/scripts/package-qualified-native-gcc-libs.ps1',
    'arm64-git-recovery/scripts/write-native-provider-dispositions.ps1',
    'arm64-git-recovery/scripts/prepare-revoked-free-audit-input.ps1'
)
$enforcementV2 = Join-Path $Root 'provider-rejection-enforcement-v2.json'
$enforcementV3 = Join-Path $Root 'provider-rejection-enforcement-v3.json'
if (Test-Path -LiteralPath $enforcementV3) {
    throw "Provider enforcement v3 already exists: $enforcementV3"
}
Write-Json -Path $enforcementV3 -Value ([ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'current-native-provider-intake-dispositions-enforced'
    supersedes_enforcement_receipt = [ordered]@{
        path = $enforcementV2
        sha256 = Get-Hash $enforcementV2
    }
    hard_rejections = @(
        [ordered]@{
            component = 'mingw-w64-aarch64-gettext'
            archive_sha256 = '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46'
            evidence = [ordered]@{
                path = 'C:\ap12-ca5f\gettext-identity-rejection-01\rejection.json'
                sha256 = '9cfced0a3234bd363d7543476079604e6853aeeb476692ffd0d55484bbeb3f36'
            }
        },
        [ordered]@{
            component = 'mingw-w64-aarch64-pcre2'
            candidate_archive_sha256 = '7460d0061581ce54d25a046860f6ce02bcde899256b58825a4b4ceb1fcfeac34'
            evidence = [ordered]@{
                path = Join-Path $Root 'network-pcre2-10.48-3-v1\admission-rejection.json'
                sha256 = '6e6eb54119a9bfc38c2803a74a59b422703f01e0697435bce9fe5c4e00d89ed7'
            }
            disposition = 'Future Git must be rebuilt against libpcre2-8-0.dll; no alias or rename is admitted.'
        }
    )
    admitted_current_d70_exports = @(
        [ordered]@{
            component = 'make'
            export = [ordered]@{
                path = $makeExport
                sha256 = Get-Hash $makeExport
            }
            disposition = [ordered]@{
                path = $makeDispositionPath
                sha256 = Get-Hash $makeDispositionPath
            }
        },
        [ordered]@{
            component = 'gcc-libs'
            export = [ordered]@{
                path = $gccExport
                sha256 = Get-Hash $gccExport
            }
            handoff = [ordered]@{
                path = $gccHandoff
                sha256 = Get-Hash $gccHandoff
            }
        },
        [ordered]@{
            component = 'qualified-utilities'
            export = [ordered]@{
                path = $utilitiesExportPath
                sha256 = Get-Hash $utilitiesExportPath
            }
            disposition = [ordered]@{
                path = $utilitiesDispositionPath
                sha256 = Get-Hash $utilitiesDispositionPath
            }
        }
    )
    candidate_only_old_runtime_exports = @(
        [ordered]@{
            component = 'libiconv'
            candidate = [ordered]@{
                path = $iconvCandidatePath
                sha256 = Get-Hash $iconvCandidatePath
            }
            disposition = [ordered]@{
                path = $iconvDispositionPath
                sha256 = Get-Hash $iconvDispositionPath
            }
        },
        [ordered]@{
            component = 'libasprintf'
            candidate = [ordered]@{
                path = $gettextCandidatePath
                sha256 = Get-Hash $gettextCandidatePath
            }
            disposition = [ordered]@{
                path = $gettextDispositionPath
                sha256 = Get-Hash $gettextDispositionPath
            }
        }
    )
    maintained_source = @(
        $sourcePaths | ForEach-Object {
            $path = Join-Path $sourceRoot ($_ -replace '/', '\')
            [ordered]@{
                path = $_
                sha256 = Get-Hash $path
            }
        }
    )
    controls = [ordered]@{
        focused_tests_expected = 27
        make_provisional_rejection_preserved = $true
        selective_archives_reused_unchanged = $true
        old_runtime_compatibility_not_inferred = $true
        authoritative_combined_input = $null
        release_archive_emitted = $false
    }
    reason_no_authoritative_combined_input = (
        'The truthful MinGW gettext 1.0-1 replacement and current-d70 ' +
        'native libintl/iconv cohorts are not yet sealed; real release ' +
        'providers and approvals also remain missing.'
    )
})

Get-Item -LiteralPath (
    $utilitiesExportPath,
    $utilitiesDispositionPath,
    $iconvCandidatePath,
    $iconvDispositionPath,
    $gettextCandidatePath,
    $gettextDispositionPath,
    $makeDispositionPath,
    $enforcementV3
) | Select-Object FullName, Length
