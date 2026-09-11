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

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required file is missing: $Path"
    }
    $actual = Get-Hash $Path
    if ($actual -ne $Expected) {
        throw "Hash mismatch for ${Path}: expected $Expected, got $actual"
    }
}

$v9 = Join-Path $Root 'provider-rejection-enforcement-v9.json'
$input = Join-Path $Root 'input-v16-revoked-free.json'
$audit = Join-Path $Root 'audit-v16-revoked-free.json'
$bashRoot = Join-Path $Root 'bash-qualified-d70-v1'
$gettextV1 = Join-Path $Root 'gettext-runtime-relocatable-v1'
$gettextV2 = Join-Path $Root 'gettext-runtime-relocatable-v2'
$libiconvRoot = Join-Path $Root 'libiconv-current-d70-v1'
$revocation = Join-Path $Root 'current-admission-revocation-v1.json'
$pcre2Rejection = Join-Path $Root 'network-pcre2-10.48-3-v1\admission-rejection.json'

$pins = [ordered]@{
    $v9 = '4bc2af5b2b9c5cbf517ba04b97e09c23d7012ae9e6f06fe9635848afd063163f'
    $input = '6d5f7e9c90656b37223684f69937f4d69af846ad967c81ab509273d4ebfd6093'
    $audit = '8cc6e5fc3ded391e545c699a1717f4245a714034573cf643fc6b04dd5880f3f1'
    (Join-Path $bashRoot 'export.json') = 'f485f6e2b0ee76fe44fc1b416354367c1325d46a9d30efa39a884d7f472c747c'
    (Join-Path $bashRoot 'handoff.json') = 'a78223dc8f0bd93c8ec567e08b877a15cf4545946214df55fe78a1ea1c27e0f2'
    (Join-Path $bashRoot 'rejection-superseding-disposition.json') = 'e7d413ec32e97fe389706482eaa75cbd415c0d987ff86a31ad72b15061255389'
    (Join-Path $gettextV2 'export.json') = '0bda655a0c112d96b5c9d05b8a1968877855b8b3b445a427857a51d21b36f07b'
    (Join-Path $gettextV2 'handoff.json') = '76e5b6701d4c1ad246a564db530e3406d9dc58a9e0af0be5f7a1fac03d7d5c4a'
    (Join-Path $libiconvRoot 'export.json') = '54c677f8e3610c03b188ac62b01638a70d1336736e3bf4b6b4ea702835a68a51'
    (Join-Path $libiconvRoot 'handoff.json') = '3955846147778fe7e8f2d428e4948f122ffb9f69e34b5c4afc42bfa2b0bff295'
    $revocation = '206cffaff0a16fc2b0453d74c923b7830fa62c0d7715327cb5a61d8e35421894'
    $pcre2Rejection = '6e6eb54119a9bfc38c2803a74a59b422703f01e0697435bce9fe5c4e00d89ed7'
}
foreach ($entry in $pins.GetEnumerator()) {
    Assert-Hash $entry.Key $entry.Value
}

$packagePins = [ordered]@{
    (Join-Path $bashRoot 'package\packages\bash-5.3.015-2-aarch64.pkg.tar.zst') =
        'c5e117fe9879bb68461db887da49e75415c2b27189272160a0da0b22e1179a90'
    (Join-Path $bashRoot 'package\packages\bash-devel-5.3.015-2-aarch64.pkg.tar.zst') =
        'd099a5a0a1cce462b4b5fb25dda479a3412bb1816cfd2408728e432db1f97189'
    (Join-Path $gettextV2 'packages\libintl-0.22.5-1-aarch64.pkg.tar.zst') =
        'ec05ffff9330db25713ff605f2272dc03aefadf6de8599f4c24a781d9f3d3f11'
    (Join-Path $gettextV2 'packages\libasprintf-0.22.5-1-aarch64.pkg.tar.zst') =
        '92efa14a5a0e63cc070b39e6e25040319d14db76040e254f0180cb6e859b3096'
    (Join-Path $libiconvRoot 'packages\libiconv-1.19-1-aarch64.pkg.tar.zst') =
        '9621c32e676ea91c73f2eba4d1adf76fc7dd40d7d0009557dcc894f4b871fa7a'
}
foreach ($entry in $packagePins.GetEnumerator()) {
    Assert-Hash $entry.Key $entry.Value
}

$failedAttemptPins = [ordered]@{
    (Join-Path $gettextV1 'packages\libintl-0.22.5-1-aarch64.pkg.tar.zst') =
        'e8bce1239bc1cb1d8e177af030bfa9d0219a86850d57e48c8525bbb5e0a0e4b7'
    (Join-Path $gettextV1 'packages\libasprintf-0.22.5-1-aarch64.pkg.tar.zst') =
        '36765a4051636b63565549c524dbdf5dbdce15a331f0bbfb3a2bd55568af3c5f'
}
foreach ($entry in $failedAttemptPins.GetEnumerator()) {
    Assert-Hash $entry.Key $entry.Value
}

$auditData = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
if ($auditData.status -ne 'incomplete' -or
    $auditData.shipping_payload_status -ne 'incomplete' -or
    $auditData.selected_package_count -ne 63 -or
    $auditData.payload_file_count -ne 16632 -or
    $auditData.classification_counts.native_pe_arm64 -ne 266 -or
    @($auditData.blockers).Count -ne 82 -or
    @($auditData.blockers | Where-Object {
        $_ -like 'missing-dll:usr/lib/bash/*:bash.exe'
    }).Count -ne 0 -or
    @($auditData.blockers | Where-Object {
        $_ -like '*:msys-iconv-2.dll'
    }).Count -ne 0 -or
    @($auditData.blockers | Where-Object {
        $_ -eq 'provider-not-supplied:iconv'
    }).Count -ne 1 -or
    @($auditData.blockers | Where-Object {
        $_ -eq 'provider-not-supplied:mingw-w64-aarch64-gettext'
    }).Count -ne 1) {
    throw 'Audit v16 no longer preserves the qualified providers and real remaining gates.'
}

$failedDisposition = Join-Path $Root 'gettext-runtime-relocatable-v1-disposition.json'
if (Test-Path -LiteralPath $failedDisposition) {
    throw "Versioned failed-attempt disposition already exists: $failedDisposition"
}
[ordered]@{
    schema = 1
    status = 'gettext-runtime-intake-v1-stopped-on-exact-metadata-expectation'
    attempt_root = $gettextV1
    packages = @(
        $failedAttemptPins.GetEnumerator() | ForEach-Object {
            [ordered]@{
                path = $_.Key
                sha256 = $_.Value
            }
        }
    )
    failure = (
        'The packager expected license = LGPL-2.1-or-later, while makepkg ' +
        'truthfully emitted license = spdx:LGPL-2.1-or-later.'
    )
    package_payload_bytes_rejected = $false
    export_written = $false
    handoff_written = $false
    admitted_to_audit = $false
    superseded_by = [ordered]@{
        path = Join-Path $gettextV2 'handoff.json'
        sha256 = Get-Hash (Join-Path $gettextV2 'handoff.json')
    }
} | ConvertTo-Json -Depth 10 |
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
$output = Join-Path $Root 'provider-rejection-enforcement-v10.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}

[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'native-provider-audit-v16-qualified-bash-gettext-libiconv-enforced'
    supersedes = [ordered]@{
        path = $v9
        sha256 = Get-Hash $v9
    }
    current_audit = [ordered]@{
        input = [ordered]@{ path = $input; sha256 = Get-Hash $input }
        report = [ordered]@{ path = $audit; sha256 = Get-Hash $audit }
        blockers = @($auditData.blockers).Count
        selected_packages = $auditData.selected_package_count
        payload_files = $auditData.payload_file_count
        native_arm64_pes = $auditData.classification_counts.native_pe_arm64
        release_complete = $false
    }
    admitted_providers = [ordered]@{
        bash = [ordered]@{
            export = [ordered]@{
                path = Join-Path $bashRoot 'export.json'
                sha256 = Get-Hash (Join-Path $bashRoot 'export.json')
            }
            handoff = [ordered]@{
                path = Join-Path $bashRoot 'handoff.json'
                sha256 = Get-Hash (Join-Path $bashRoot 'handoff.json')
            }
            rejection_supersession = [ordered]@{
                path = Join-Path $bashRoot 'rejection-superseding-disposition.json'
                sha256 = Get-Hash (
                    Join-Path $bashRoot 'rejection-superseding-disposition.json'
                )
            }
            packages = @(
                $packagePins.GetEnumerator() | Where-Object {
                    $_.Key.StartsWith($bashRoot)
                } | ForEach-Object {
                    [ordered]@{ path = $_.Key; sha256 = $_.Value }
                }
            )
        }
        gettext_runtime = [ordered]@{
            export = [ordered]@{
                path = Join-Path $gettextV2 'export.json'
                sha256 = Get-Hash (Join-Path $gettextV2 'export.json')
            }
            handoff = [ordered]@{
                path = Join-Path $gettextV2 'handoff.json'
                sha256 = Get-Hash (Join-Path $gettextV2 'handoff.json')
            }
            packages = @(
                $packagePins.GetEnumerator() | Where-Object {
                    $_.Key.StartsWith($gettextV2)
                } | ForEach-Object {
                    [ordered]@{ path = $_.Key; sha256 = $_.Value }
                }
            )
            failed_v1_attempt = [ordered]@{
                path = $failedDisposition
                sha256 = Get-Hash $failedDisposition
            }
            replaces_revoked_mingw_gettext = $false
        }
        libiconv = [ordered]@{
            export = [ordered]@{
                path = Join-Path $libiconvRoot 'export.json'
                sha256 = Get-Hash (Join-Path $libiconvRoot 'export.json')
            }
            handoff = [ordered]@{
                path = Join-Path $libiconvRoot 'handoff.json'
                sha256 = Get-Hash (Join-Path $libiconvRoot 'handoff.json')
            }
            package = [ordered]@{
                path = (
                    Join-Path $libiconvRoot 'packages\libiconv-1.19-1-aarch64.pkg.tar.zst'
                )
                sha256 = $packagePins[
                    (Join-Path $libiconvRoot 'packages\libiconv-1.19-1-aarch64.pkg.tar.zst')
                ]
            }
            iconv_executable_admitted = $false
        }
    }
    inherited_rejections = [ordered]@{
        revoked_gettext_archive = [ordered]@{
            path = $revocation
            sha256 = Get-Hash $revocation
        }
        incompatible_pcre2 = [ordered]@{
            path = $pcre2Rejection
            sha256 = Get-Hash $pcre2Rejection
        }
    }
    exact_remaining_handoffs = [ordered]@{
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
        mingw_gettext_dll_closure = @(
            $auditData.blockers | Where-Object {
                $_ -like 'missing-dll:*:libintl-8.dll'
            }
        )
        operational_rebuilds = @(
            $auditData.blockers | Where-Object {
                $_ -like 'private-runtime-path:*'
            }
        )
        iconv_tool = (
            'Fresh qualified iconv 1.19-1 package input whose iconv.exe uses ' +
            'canonical /usr/share/locale; current DLL package remains admitted.'
        )
        managed_gcm = (
            'Actual user-approved managed component evidence; admission remains gated.'
        )
        native_self_hosting = 'Native self-hosting evidence required by the contract.'
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
        assembler_completion_gate_waived = $false
        revoked_gettext_readmitted = $false
        incompatible_pcre2_aliased_or_renamed = $false
        private_iconv_executable_admitted = $false
        private_curl_or_tcl_paths_waived = $false
        unshipped_gettext_tools_or_devel_claimed = $false
        source_rebuilt_by_intake = $false
    }
} | ConvertTo-Json -Depth 20 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $failedDisposition, $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
