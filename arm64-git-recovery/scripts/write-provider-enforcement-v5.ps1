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

$v4 = Join-Path $Root 'provider-rejection-enforcement-v4.json'
$audit = Join-Path $Root 'audit-v12-revoked-free.json'
$input = Join-Path $Root 'input-v12-revoked-free.json'
$prefixLineage = Join-Path $Root 'operational-prefix-lineage-v1.json'
$failure = 'C:\ap12-ca5f\gettext-native-02\failure-receipt.json'
$compressionHandoff = 'C:\ap06-2160\compression-policy-handoff-20260909-01\handoff.json'

Assert-FileHash -Path $v4 -Expected '982fa489b952621f466537bc8a85df823319f48e64446e24e7cc4df700372d4e'
Assert-FileHash -Path $audit -Expected '7afd380831d93cbdb7b66751fbb1e991cb1b9a64bf6bf2ed78b99ff4dd134938'
Assert-FileHash -Path $input -Expected 'ba09e870c6262701d295b1cf47247ef27f42dfb30cce29d2354b22b76f5f7618'
Assert-FileHash -Path $prefixLineage -Expected 'b6741cedc7f502822638e9dee22740310f51cdd7eda9bdeec0b8a26e2dae6332'
Assert-FileHash -Path $failure -Expected 'c1c38afa150a3f41cf6a6513158ae1e7efd411577677fb9bc131d4fbb2c79d78'
Assert-FileHash -Path $compressionHandoff -Expected '406b2632c55b136be368d12609c55649a98b1d852d7f65b506149523b9ddd9dc'

$failureData = Get-Content -Raw -LiteralPath $failure | ConvertFrom-Json
if ($failureData.status -ne 'gettext-1.0-canonical-build-failed-arm64-seh' -or
    $failureData.attempt.configureCompleted -ne $true -or
    $failureData.attempt.buildCompleted -ne $false -or
    $failureData.attempt.checksStarted -ne $false -or
    $failureData.attempt.installStarted -ne $false -or
    $failureData.failure.file -ne 'gettext-tools/gnulib-lib/libxml/xpath.c' -or
    [int]$failureData.failure.line -ne 2662) {
    throw 'Gettext failure receipt does not match the reported pre-qualification failure'
}
foreach ($log in $failureData.logs) {
    Assert-FileHash -Path $log.path -Expected $log.sha256
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourcePaths = @(
    'arm64-git-recovery/scripts/assemble-full-release.py',
    'arm64-git-recovery/contracts/full-release-v1.json',
    'arm64-git-recovery/docs/FULL-RELEASE-ASSEMBLY.md',
    'arm64-git-recovery/tests/test_assemble_full_release.py',
    'arm64-git-recovery/scripts/package-qualified-native-gcc-libs.ps1',
    'arm64-git-recovery/scripts/package-qualified-native-grep-v2.ps1',
    'arm64-git-recovery/scripts/write-operational-prefix-lineage.ps1',
    'arm64-git-recovery/scripts/write-provider-enforcement-v5.ps1',
    'arm64-git-recovery/native-packaging/compression-policy/makepkg-compression-policy.sh',
    'arm64-git-recovery/native-packaging/compression-policy/makepkg-compression.sh',
    'arm64-git-recovery/native-packaging/compression-policy/with-makepkg-compression.sh'
)

$output = Join-Path $Root 'provider-rejection-enforcement-v5.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'current-provider-audit-incomplete-gettext-corrective-build-required'
    supersedes = [ordered]@{
        path = $v4
        sha256 = Get-Hash $v4
    }
    current_audit = [ordered]@{
        input = [ordered]@{
            path = $input
            sha256 = Get-Hash $input
        }
        report = [ordered]@{
            path = $audit
            sha256 = Get-Hash $audit
        }
    }
    gettext = [ordered]@{
        rejected_archive_sha256 = '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46'
        signed_source_receipt = [ordered]@{
            path = 'C:\ap12-ca5f\gettext-source-01\source-receipt.json'
            sha256 = '9e534ee1ebcabc9df87066f131227bf342f311ce727243c8eea215c45091e173'
        }
        failed_attempt = [ordered]@{
            path = $failure
            sha256 = Get-Hash $failure
            phase = 'make-before-checks-or-install'
            source_file = $failureData.failure.file
            source_line = $failureData.failure.line
            error = $failureData.failure.message
        }
        success_export = $null
        old_revocation_remains_controlling = $true
        corrective_attempt_requirements = @(
            'Use the same signed official GNU gettext 1.0 extraction.',
            'Add -fno-omit-frame-pointer for the proven ARM64 SEH code-generation failure.',
            'Add source/build prefix maps so no private __FILE__ or debug path is emitted.',
            'Run build, full checks, install, package transaction, complete hash/import inventory, compiled consumers, and exact Git consumer proof.',
            'Replace only the rejected archive in both network and Python closure exports.'
        )
    }
    operational_prefix_lineage = [ordered]@{
        path = $prefixLineage
        sha256 = Get-Hash $prefixLineage
        curl_and_tcl_require_source_rebuilds = $true
    }
    pending_provider_packaging = [ordered]@{
        component = 'grep 1:3.0-7'
        action = 'hash-gated egrep/fgrep shebang-only repack'
        source_rebuild = $false
        execution_state = 'held-until-window-closed'
        compression_policy = [ordered]@{
            handoff = [ordered]@{
                path = $compressionHandoff
                sha256 = Get-Hash $compressionHandoff
            }
            imported_source_hashes_match = $true
            jobs = 1
            installed_makepkg_modified = $false
        }
    }
    maintained_source = @(
        $sourcePaths | ForEach-Object {
            $path = Join-Path $repoRoot ($_ -replace '/', '\')
            [ordered]@{
                path = $_
                sha256 = Get-Hash $path
            }
        }
    )
    controls = [ordered]@{
        failed_gettext_attempt_promoted = $false
        revoked_gettext_re_admitted = $false
        curl_or_tcl_repack_claimed = $false
        heavy_provider_jobs = 0
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
