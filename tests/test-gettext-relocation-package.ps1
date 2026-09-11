#requires -Version 7.3
$ErrorActionPreference = 'Stop'
$script = [IO.File]::ReadAllText(
    "$PSScriptRoot\..\.github\scripts\prepare-gettext-relocation-package.ps1"
)
foreach ($required in @(
    "pkgver=1.0",
    "pkgrel=1",
    'mingw-w64-aarch64-libiconv',
    'dependencyPackages',
    'dependencyImportOwners',
    '2753811ebaef825701261cead50289472134122fd2b0fb87dc3599cf2a53c37a',
    'pinnedOwnershipRecipe',
    'old 0.19.8.1 source identity is not reused',
    'Get-PeImports',
    'pacman',
    "options=('staticlibs' '!strip' '!zipman' '!purge' '!debug')",
    'gettext.exe (GNU gettext-runtime) 1.0',
    'RuntimeDependencyBin',
    'BuildReceipt',
    '$buildReceiptFile = Get-Item -LiteralPath $BuildReceipt',
    'Test-ByteSequence',
    'priorMislabelledPackage',
    'stage-manifest.json',
    'includesEveryFileHash',
    'appliedPatches = @()',
    'tree-sitter-0.23.2\lib\src\unicode\LICENSE',
    'embed a private staging prefix',
    'cp -a "$startdir/payload/mingwarm64" "$pkgdir/"',
    "'.copilot'",
    "'session-state'"
)) {
    if (-not $script.Contains($required, [StringComparison]::Ordinal)) {
        throw "Gettext relocation preparer lost invariant: $required"
    }
}
if ($script.Contains("pkgver=0.26", [StringComparison]::Ordinal)) {
    throw 'Gettext relocation preparer retained the old false 0.26 identity.'
}

'PASS: gettext package preparation requires tested canonical 1.0 payload and rejects private paths'
