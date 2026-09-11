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

$v3 = Join-Path $Root 'provider-rejection-enforcement-v3.json'
$input = Join-Path $Root 'input-v12-revoked-free.json'
$audit = Join-Path $Root 'audit-v12-revoked-free.json'
$utilities = Join-Path $Root 'qualified-utilities-v3\export.json'
$utilitiesDisposition = Join-Path $Root (
    'qualified-utilities-v3\provider-disposition.json'
)
$gccExport = Join-Path $Root 'gcc-libs-v1\export.json'
$gccHandoff = Join-Path $Root 'gcc-libs-v1\handoff.json'
$makeExport = Join-Path $Root 'qualified-make-d70-v1\export.json'
$makeDisposition = Join-Path $Root (
    'qualified-make-d70-v1\rejection-superseding-disposition-v1.json'
)

Assert-FileHash -Path $v3 -Expected '24679ffb759ef1eb3593b8f5d91113a603680d565d823fc59fae59f2483753c5'
Assert-FileHash -Path $input -Expected 'ba09e870c6262701d295b1cf47247ef27f42dfb30cce29d2354b22b76f5f7618'
Assert-FileHash -Path $audit -Expected '7afd380831d93cbdb7b66751fbb1e991cb1b9a64bf6bf2ed78b99ff4dd134938'
Assert-FileHash -Path $utilities -Expected 'a3872466c175bd47e87ee2efb7d812a3fdbf90aea42709166fd13ab399fd89c4'
Assert-FileHash -Path $utilitiesDisposition -Expected 'a3f53bd2919ef40f6428cc0bf4ce3edd838b0a7ebf3053d1c7e6a914bebf80dd'
Assert-FileHash -Path $gccExport -Expected '2e7f2b7c8432344c8faa650e7a6a89903947719da75e938ed7d2802ec81a5bbc'
Assert-FileHash -Path $gccHandoff -Expected 'f5049294a9d6d63faad21e80e52a0f0f6a1b61f49b3d12b137aa05def9a07efc'
Assert-FileHash -Path $makeExport -Expected 'a4b12fe4afc672d05cc9518a013359e72c0c28fe1a8ae2e68a475268ab4f4a71'
Assert-FileHash -Path $makeDisposition -Expected '2591dd687eb2fe170b3073ea530978ffbb5675ab928bc379d5458e2fcc4c1992'

$report = Get-Content -Raw -LiteralPath $audit | ConvertFrom-Json
if ($report.status -ne 'incomplete' -or
    $report.shipping_payload_status -ne 'incomplete' -or
    $report.native_build_self_hosting_status -ne 'missing' -or
    [int]$report.git_split_count -ne 15 -or
    [int]$report.selected_package_count -ne 58 -or
    [int]$report.payload_file_count -ne 16353 -or
    [int]$report.classification_counts.native_pe_arm64 -ne 219 -or
    @($report.blockers).Count -ne 97) {
    throw 'Audit v12 summary does not match the sealed incomplete result'
}

$privateBlockers = @($report.blockers | Where-Object { $_ -like 'private-*' })
$expectedPrivateBlockers = @(
    'private-runtime-path:mingwarm64/bin/libcurl-4.dll:C:/ap08-d207/curl-chain-01/variants/openssl/prefix/mingwarm64/bin',
    'private-runtime-path:mingwarm64/bin/tcl86.dll:C:/ap10-ca5f/git-full-01/bootstrap/mingwarm64/bin',
    'private-runtime-path:mingwarm64/bin/tcl86.dll:C:/ap10-ca5f/git-full-01/bootstrap/mingwarm64/lib/tcl8.6',
    'private-runtime-path:mingwarm64/bin/tcl86.dll:C:/ap10-ca5f/git-full-01/bootstrap/mingwarm64/share/man'
)
if (Compare-Object $privateBlockers $expectedPrivateBlockers) {
    throw 'Audit v12 private operational-prefix blocker set changed'
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$sourcePaths = @(
    'arm64-git-recovery/scripts/assemble-full-release.py',
    'arm64-git-recovery/contracts/full-release-v1.json',
    'arm64-git-recovery/docs/FULL-RELEASE-ASSEMBLY.md',
    'arm64-git-recovery/tests/test_assemble_full_release.py',
    'arm64-git-recovery/scripts/package-qualified-native-gcc-libs.ps1',
    'arm64-git-recovery/scripts/write-native-provider-dispositions.ps1',
    'arm64-git-recovery/scripts/prepare-revoked-free-audit-input.ps1',
    'arm64-git-recovery/scripts/write-qualified-utilities-v3.ps1',
    'arm64-git-recovery/scripts/prepare-audit-input-v12.ps1',
    'arm64-git-recovery/scripts/package-qualified-native-grep-v2.ps1',
    'arm64-git-recovery/scripts/write-provider-enforcement-v4.ps1'
)

$output = Join-Path $Root 'provider-rejection-enforcement-v4.json'
if (Test-Path -LiteralPath $output) {
    throw "Versioned enforcement receipt already exists: $output"
}
[ordered]@{
    schema = 1
    recorded_utc = [DateTime]::UtcNow.ToString('o')
    status = 'current-native-provider-audit-v12-incomplete-enforced'
    supersedes = [ordered]@{
        path = $v3
        sha256 = Get-Hash $v3
    }
    audit_input = [ordered]@{
        path = $input
        sha256 = Get-Hash $input
        revoked_gettext_absent_from_network_and_python_packages = $true
    }
    audit = [ordered]@{
        path = $audit
        sha256 = Get-Hash $audit
        status = $report.status
        shipping_payload_status = $report.shipping_payload_status
        native_build_self_hosting_status = $report.native_build_self_hosting_status
        git_splits = $report.git_split_count
        selected_packages = $report.selected_package_count
        payload_files = $report.payload_file_count
        native_arm64_pes = $report.classification_counts.native_pe_arm64
        blockers = @($report.blockers).Count
    }
    admitted_current_d70_exports = @(
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
            component = 'make'
            export = [ordered]@{
                path = $makeExport
                sha256 = Get-Hash $makeExport
            }
            disposition = [ordered]@{
                path = $makeDisposition
                sha256 = Get-Hash $makeDisposition
            }
        },
        [ordered]@{
            component = 'qualified-utilities'
            export = [ordered]@{
                path = $utilities
                sha256 = Get-Hash $utilities
            }
            disposition = [ordered]@{
                path = $utilitiesDisposition
                sha256 = Get-Hash $utilitiesDisposition
            }
            retained = @('diffutils', 'gawk')
        }
    )
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
            component = 'mingw-w64-aarch64-pcre2-10.48-3'
            archive_sha256 = '7460d0061581ce54d25a046860f6ce02bcde899256b58825a4b4ceb1fcfeac34'
            evidence = [ordered]@{
                path = Join-Path $Root 'network-pcre2-10.48-3-v1\admission-rejection.json'
                sha256 = '6e6eb54119a9bfc38c2803a74a59b422703f01e0697435bce9fe5c4e00d89ed7'
            }
            disposition = 'Current Git imports libpcre2-8.dll; future Git must rebuild against libpcre2-8-0.dll.'
        }
    )
    remaining_provider_handoffs = @(
        [ordered]@{
            owner = 'ca5'
            components = @(
                'mingw-w64-aarch64-gettext 1.0-1',
                'native MSYS libintl/libasprintf current-d70 cohort',
                'native MSYS iconv/libiconv current-d70 cohort',
                'MinGW libcurl without compiled private bin prefix',
                'MinGW Tcl without compiled bootstrap bin/lib/share paths'
            )
            requirements = @(
                'Replace the revoked gettext archive consistently in both network and Python exports.',
                'Bind signed source/recipe identity, exact package ownership, dependencies, and archive hashes.',
                'Publish current-cohort native consumer/readback evidence; do not rebind old-runtime proofs.',
                'Update corrected Git/network handoffs where their immutable provider references change.'
            )
        },
        [ordered]@{
            owner = 'efd'
            components = @('findutils 4.11.0-2', 'sed 4.9-1')
            requirements = @(
                'Use installed locale path /usr/share/locale.',
                'Use /var/locatedb for findutils locate database ownership.',
                'Publish exact source/recipe/payload hashes and current-d70 native readbacks.',
                'Do not overlap or promote provisional Bash/Coreutils.'
            )
        },
        [ordered]@{
            owner = 'provider-intake'
            components = @('grep 1:3.0-7')
            requirements = @(
                'Repackage exact grep.exe/data bytes unchanged.',
                'Relocate only the hash-bound egrep/fgrep shebangs to #!/usr/bin/sh.',
                'Preserve exec grep -E/-F and the sh dependency.',
                'Run archive and native wrapper readback after the exclusive matrix window closes.'
            )
        }
    )
    independent_release_gates = @(
        'real bash and sh packages',
        'real coreutils package',
        'OpenSSH and remaining native utilities',
        'Perl compatibility and modules',
        'managed GCM user approval evidence',
        'native self-hosting evidence'
    )
    private_operational_prefix_blockers = $privateBlockers
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
        focused_tests = 29
        false_toolchain_include_blockers_removed = $true
        source_and_stage_include_provenance_allowed = $true
        real_runtime_prefix_blockers_preserved = $true
        old_runtime_compatibility_not_inferred = $true
        release_archive_emitted = $false
    }
} | ConvertTo-Json -Depth 16 |
    Set-Content -LiteralPath $output -Encoding utf8NoBOM

Get-Item -LiteralPath $output |
    Select-Object FullName, Length, @{n = 'SHA256'; e = { Get-Hash $_.FullName }}
