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

function Assert-Hash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or
        (Get-Hash $Path) -ne $Expected) {
        throw "Pinned final receipt changed: $Path"
    }
}

$v11 = Join-Path $Root 'provider-rejection-enforcement-v11.json'
$input = Join-Path $Root 'input-v17-revoked-free.json'
$audit = Join-Path $Root 'audit-v17-revoked-free.json'
$iconvV1 = Join-Path $Root 'iconv-current-d70-v1'
$iconvV2 = Join-Path $Root 'iconv-current-d70-v2'
$iconvPackage = Join-Path $iconvV2 'packages\iconv-1.19-1-aarch64.pkg.tar.zst'
$iconvExport = Join-Path $iconvV2 'export.json'
$iconvHandoff = Join-Path $iconvV2 'handoff.json'
$iconvSupersession = Join-Path $iconvV2 'excluded-iconv-superseding-disposition.json'
$pins = [ordered]@{
    $v11 = '00752b291fbc4c64c9f44b04d94f1ea86277d49864dbe2723b88ca62487756b4'
    $input = 'd4b4e9b2cf98d5d387f47315c87d7e99ba0ee20ee341e0105d5dcfd62c0b57c9'
    $audit = 'd71f2c02617dbc24e338065f5d5ef5e44f08669240fc40b21a9ad82a8823fc47'
    $iconvPackage = 'dda09dbd593a8fb24ecdd2bf392f3816bda55f5785f63f31334bc98174def594'
    $iconvExport = '152cfe8c388d698473f4ea1c6e52e9bdf271576920ea01b107b30459f370244f'
    $iconvHandoff = '0714730e0435806540d790cbf9db1c7fa1f28b58bfccdf0c1141b79e48602f8a'
    $iconvSupersession = 'f03a23888d92051dca5868828746cb25a5d97f120b69e1ea6f2e0de4ca9ddae7'
    (Join-Path $iconvV1 'packages\iconv-1.19-1-aarch64.pkg.tar.zst') =
        'dfacff7ea2f57188f0d9a23546f3c6746397374d3e599830423c1d3c39bd8a33'
}
foreach ($entry in $pins.GetEnumerator()) {
    Assert-Hash $entry.Key $entry.Value
}

$auditData = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
if ($auditData.status -ne 'incomplete' -or
    $auditData.shipping_payload_status -ne 'incomplete' -or
    $auditData.selected_package_count -ne 64 -or
    $auditData.payload_file_count -ne 16633 -or
    $auditData.classification_counts.native_pe_arm64 -ne 267 -or
    @($auditData.blockers).Count -ne 81 -or
    @($auditData.blockers | Where-Object {
        $_ -eq 'provider-not-supplied:iconv'
    }).Count -ne 0 -or
    @($auditData.blockers | Where-Object {
        $_ -eq 'provider-not-supplied:mingw-w64-aarch64-gettext'
    }).Count -ne 1) {
    throw 'Audit v17 no longer preserves the canonical iconv result and real remaining gates.'
}

$failedDisposition = Join-Path $Root 'iconv-current-d70-v1-disposition.json'
if (Test-Path -LiteralPath $failedDisposition) {
    throw "Versioned failed-attempt disposition already exists: $failedDisposition"
}
[ordered]@{
    schema = 1
    status = 'iconv-intake-v1-stopped-before-export-on-roundtrip-comparison-api'
    attempt_root = $iconvV1
    package = [ordered]@{
        path = Join-Path $iconvV1 'packages\iconv-1.19-1-aarch64.pkg.tar.zst'
        sha256 = $pins[(Join-Path $iconvV1 'packages\iconv-1.19-1-aarch64.pkg.tar.zst')]
    }
    failure = (
        'PowerShell byte arrays do not expose the attempted AsSpan method; ' +
        'the intake stopped before writing export or handoff records.'
    )
    export_written = $false
    handoff_written = $false
    admitted_to_audit = $false
    superseded_by = [ordered]@{
        path = $iconvHandoff
        sha256 = Get-Hash $iconvHandoff
    }
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $failedDisposition -Encoding utf8NoBOM

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourceFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $repoRoot 'arm64-git-recovery') `
        -Recurse -File |
        Where-Object {
            $_.FullName -notmatch '\\__pycache__\\' -and
            $_.Extension -in '.ps1', '.py', '.json', '.md', '.in', '.sh'
        }
)
$output = Join-Path $Root 'provider-rejection-enforcement-v12.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}

[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'native-provider-audit-v17-canonical-iconv-enforced'
    supersedes = [ordered]@{
        path = $v11
        sha256 = Get-Hash $v11
    }
    current_audit = [ordered]@{
        input = [ordered]@{ path = $input; sha256 = Get-Hash $input }
        report = [ordered]@{ path = $audit; sha256 = Get-Hash $audit }
        blockers = 81
        selected_packages = 64
        payload_files = 16633
        native_arm64_pes = 267
        release_complete = $false
    }
    canonical_iconv_provider = [ordered]@{
        package = [ordered]@{
            path = $iconvPackage
            sha256 = Get-Hash $iconvPackage
        }
        export = [ordered]@{
            path = $iconvExport
            sha256 = Get-Hash $iconvExport
        }
        handoff = [ordered]@{
            path = $iconvHandoff
            sha256 = Get-Hash $iconvHandoff
        }
        excluded_predecessor_supersession = [ordered]@{
            path = $iconvSupersession
            sha256 = Get-Hash $iconvSupersession
        }
        failed_v1_attempt = [ordered]@{
            path = $failedDisposition
            sha256 = Get-Hash $failedDisposition
        }
        exact_iconv_exe_sha256 =
            '5fc974e03a6c2a4bd25850e23876ee3503565bb77c72118fe7dde0f8f10fbca5'
        excluded_iconv_exe_sha256 =
            '1354cb317c75b52db5f2e0d808d6612a561f93cbbafe0e2900d090e061acc8fc'
        existing_libiconv_package_superseded = $false
    }
    remaining_controlling_gaps = [ordered]@{
        provider_packages = @(
            $auditData.blockers | Where-Object {
                $_ -like 'provider-not-supplied:*'
            }
        )
        required_payload_files = @(
            $auditData.blockers | Where-Object {
                $_ -like 'payload-file-not-supplied:*'
            }
        )
        missing_imports = @(
            $auditData.blockers | Where-Object {
                $_ -like 'missing-dll:*'
            }
        )
        operational_rebuilds = @(
            $auditData.blockers | Where-Object {
                $_ -like 'private-runtime-path:*'
            }
        )
        managed_admission = @(
            $auditData.blockers | Where-Object {
                $_ -like 'managed-admission-not-supplied:*'
            }
        )
        native_self_hosting = @(
            $auditData.blockers | Where-Object {
                $_ -eq 'missing-native-self-hosting-evidence'
            }
        )
    }
    maintained_source = @(
        $sourceFiles | Sort-Object FullName -Unique | ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($repoRoot.Length + 1).Replace('\', '/')
                sha256 = Get-Hash $_.FullName
            }
        }
    )
    controls = [ordered]@{
        release_archive_emitted = $false
        audit_incomplete_status_preserved = $true
        old_excluded_iconv_reused_or_relabeled = $false
        existing_libiconv_archive_repacked = $false
        source_or_dependency_rebuild_performed_by_intake = $false
        revoked_mingw_gettext_readmitted = $false
    }
} | ConvertTo-Json -Depth 20 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $failedDisposition, $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
