#requires -Version 7.3
$ErrorActionPreference = 'Stop'

$script = Get-Content -LiteralPath "$PSScriptRoot\..\.github\scripts\export-git-helper-provider.ps1" -Raw
foreach ($required in @(
    'mingw-w64-aarch64-git-lfs',
    'mingw-w64-aarch64-git-extra',
    '91883E11E83DC29D14104DB4EDD44359093056EE',
    '21d6ed86c38d28e89c950c9e1e349b6edefd1afb',
    '8576a0499b93a7ddbc0f7c4ee3d9f44f5183b6c44f635561d8f31a622f350405',
    'mingwarm64/bin/git-lfs.exe',
    'mingwarm64/bin/git-askpass.exe',
    'mingwarm64/bin/git-askyesno.exe'
)) {
    if (-not $script.Contains($required)) {
        throw "Exporter is missing pinned contract value: $required"
    }
}
if ($script -notmatch 'Remove-Item.+git-credential-helper-selector\.exe') {
    throw 'Exporter must exclude the GCM-owned helper selector from git-extra.'
}
if ($script -notmatch 'Get-PeMachine' -or $script -notmatch '0xaa64') {
    throw 'Exporter must enforce native ARM64 PE payloads.'
}
if ($script -notmatch 'Assert-PackageSignature') {
    throw 'Exporter must verify the detached upstream package signatures.'
}
if ($script -notmatch 'sources/' -or $script -notmatch 'detached_signatures_verified') {
    throw 'Exporter must preserve hash-bound source packages and signatures.'
}
if ($script -notmatch 'git_extra_native_rebuild' -or $script -notmatch 'aarch64-w64-mingw32') {
    throw 'Exporter must record the native GCC git-extra rebuild.'
}

$verifier = Get-Content -LiteralPath "$PSScriptRoot\..\.github\scripts\test-git-helper-provider.ps1" -Raw
foreach ($required in @(
    'mingw-w64-aarch64-git-lfs',
    'mingw-w64-aarch64-git-extra',
    'git-credential-helper-selector.exe',
    '0xaa64',
    'GIT_CONFIG_NOSYSTEM',
    'version https://git-lfs.github.com/spec/v1',
    'network_used = $false'
)) {
    if (-not $verifier.Contains($required)) {
        throw "Verifier is missing admission control: $required"
    }
}

'PASS: Git helper exporter and verifier pin inputs, ARM64 payloads, ownership, and behavior'
