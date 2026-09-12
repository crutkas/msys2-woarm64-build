#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if ((Get-FileHash -LiteralPath (Join-Path $SourceDirectory 'PKGBUILD')).Hash.ToLowerInvariant() -cne
    '49481956e1d6e9eaff828c5fbdc5738ec3a657ccf9d808b77a7b52eafea17d4e') {
    throw 'Only the pinned wineditline 2.208-1 recipe is supported.'
}
$result = & "$PSScriptRoot\prepare-pinned-mingwarm64-recipe.ps1" @PSBoundParameters
$path = Join-Path $OutputDirectory 'PKGBUILD'
$text = [IO.File]::ReadAllText($path)
$generator = '    -GNinja \'
foreach ($token in $generator, 'pkgrel=1') {
    if ([regex]::Matches($text,[regex]::Escape($token)).Count -ne 1) { throw 'Unexpected pinned wineditline recipe structure.' }
}
$text = $text.Replace($generator, $generator + "`n" + '    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \').Replace('pkgrel=1','pkgrel=2')
[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))
$result.Status = 'namespace-and-cmake-policy-prepared-not-package-admitted'
$result.RecipeSHA256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$result.Change = 'Declare MINGWARM64 and CMake4-supported minimum compatibility policy3.5; local package release2'
$result.Preserved = 'Original source/patch hashes, dependencies, shared/static libraries, sample executables and install layout'
$result
