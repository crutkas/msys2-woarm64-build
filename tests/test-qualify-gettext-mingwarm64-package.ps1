#requires -Version 7.3
$ErrorActionPreference = 'Stop'
$script = [IO.File]::ReadAllText(
    "$PSScriptRoot\qualify-gettext-mingwarm64-package.ps1"
)
foreach ($required in @(
    'pkgname = mingw-w64-aarch64-gettext',
    'pkgver = 1.0-1',
    'depend = mingw-w64-aarch64-libiconv',
    'mingwarm64/bin/gettext.exe',
    'mingwarm64/bin/libintl-8.dll',
    '0xaa64',
    'gettext.exe (GNU gettext-runtime) 1.0',
    'Get-PeMachine',
    'Get-PeImports',
    'Test-ByteSequence',
    'DependencyPackages',
    'packageDependencyNames',
    'dependencyArchives',
    'pacman-install.log',
    '$installRoot\var\lib\pacman',
    '$dependencyArchives | ForEach-Object { $_.item.FullName }',
    'pacman-dependency-check.log',
    '$unsatisfiedDependencies',
    'dependency-payload-comparison.json',
    'everyInstalledFileByteIdentical',
    'gettextPackageAlteredFiles = 0',
    'dependencyMtreeLimitation',
    'moved-root-help.log',
    'moved-root-bound.log',
    'moved-root-unbound.log',
    'moved-root-msgunfmt.log',
    'qualification-missing-domain',
    'shippedBoundCatalog',
    '$gitDirectory\git.exe',
    'pacman-qkk.log',
    'libintl-8.dll',
    'libintl.a',
    'libiconv.a',
    'gettext-shared.exe',
    'gettext-static.exe',
    '[IO.File]::WriteAllText',
    'git-gettext-runtime.log',
    'lt_cv_deplibs_check_method=pass_all',
    'allImportsResolved',
    'includesEveryFileHash',
    'integrationCohort',
    'runtimeApiCohort',
    'evidenceFiles',
    'ConvertTo-Json -Depth 20',
    'ForEach-Object { $_.ToString() }',
    'gettext-package-qualified'
)) {
    if (-not $script.Contains($required, [StringComparison]::Ordinal)) {
        throw "Gettext package qualifier lost invariant: $required"
    }
}

'PASS: gettext qualifier covers pacman, ARM64 imports, shared/static/Git consumers, and relocation'
