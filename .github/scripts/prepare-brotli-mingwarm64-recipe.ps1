#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if ((Get-FileHash -LiteralPath (Join-Path $SourceDirectory 'PKGBUILD')).Hash.ToLowerInvariant() -cne
    '5062248b53ecd7a70027732630874cb9e8cf113be49975a9eb561a631121aea6') {
    throw 'Only the pinned Brotli 1.2.0-1 recipe is supported.'
}
$result = & "$PSScriptRoot\prepare-pinned-mingwarm64-recipe.ps1" @PSBoundParameters
$path = Join-Path $OutputDirectory 'PKGBUILD'
$text = [IO.File]::ReadAllText($path)
$old = '${MINGW_PREFIX}/bin/ctest . || warning "Tests failed"'
$new = '${MINGW_PREFIX}/bin/ctest --output-on-failure --no-tests=error --parallel "${WOARM64_JOBS:?}"'
if ([regex]::Matches($text,[regex]::Escape($old)).Count -ne 2) { throw 'Unexpected pinned Brotli test structure.' }
$text = $text.Replace($old,$new).Replace("`r`n","`n")
[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))
$result.Status = 'namespace-and-strict-brotli-checks-prepared-not-package-admitted'
$result.RecipeSHA256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$result.Change = 'Declare MINGWARM64 and require bounded, nonempty, successful CTest runs for both static/shared profiles'
$result.Preserved = 'Original source/checksum, both package splits, library/tool/testdata build and install operations'
$result
