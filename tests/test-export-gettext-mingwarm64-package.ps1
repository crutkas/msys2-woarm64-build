#requires -Version 7.3
$ErrorActionPreference = 'Stop'
$script = [IO.File]::ReadAllText(
    "$PSScriptRoot\..\.github\scripts\export-gettext-mingwarm64-package.ps1"
)
foreach ($required in @(
    'admitted-complete-exported-verified-native-gettext-provider',
    'mingw-w64-aarch64-gettext-0.26-1',
    '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46',
    'ce20122f2773a5ecde625db5cb58849daf8b66c7f7cff750fee8b5e1aa98fff3',
    'name = ''mingw-w64-aarch64-gettext''',
    'path = "packages/$($package.Name)"',
    'depend = mingw-w64-aarch64-libiconv',
    'signed-source-archive',
    'signature-verification-log',
    'package-recipe',
    'pinned-ownership-recipe',
    'stage-manifest',
    'PackageBuildReceipt',
    'makepkg-config',
    'makepkg-log',
    'startDirectory',
    'buildDirectory',
    'build-source-patch',
    'originalPatchSourceHashes',
    'patchedSourceHashes',
    'compilerPathPolicy',
    '$qualificationDocument.relocation',
    'ConvertTo-Json -Depth 20',
    'libtoolDependencyCacheOverride',
    'integrationCohort',
    'No compatibility alias',
    'licenses, locales, or documentation are omitted'
)) {
    if (-not $script.Contains($required, [StringComparison]::Ordinal)) {
        throw "Gettext exporter lost invariant: $required"
    }
}

'PASS: gettext exporter binds source, revocation, genuine package metadata, and explicit omissions'
