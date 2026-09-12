#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\cohort-inventory.ps1"
$source = (Resolve-Path -LiteralPath $SourceDirectory).ProviderPath.TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) { throw 'Prepared Expat recipe output must be new.' }
if ($output.StartsWith("$source\", [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Prepared recipe must be outside its immutable source.'
}
$pkgbuild = Join-Path $source 'PKGBUILD'
$expected = '126c496ed77fa60cf251d222044604d8f2968393d5fe5444d902092c75086a61'
if ((Get-FileHash -LiteralPath $pkgbuild).Hash.ToLowerInvariant() -cne $expected) {
    throw 'Only the pinned Expat 2.8.4-2 recipe is supported by this mapping.'
}
$files = @(Get-CohortInventory $source)
$before = [IO.File]::ReadAllText($pkgbuild).Replace("`r`n", "`n")
$original = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64')"
$mapped = "mingw_arch=('mingw32' 'mingw64' 'ucrt64' 'clang64' 'clangarm64' 'mingwarm64')"
$permissiveCheck = 'ctest --test-dir build-${MSYSTEM} --output-on-failure || true'
$strictCheck = 'ctest --test-dir build-${MSYSTEM} --output-on-failure'
foreach ($token in $original, $permissiveCheck) {
    if ([regex]::Matches($before, [regex]::Escape($token)).Count -ne 1) { throw 'Unexpected pinned recipe structure.' }
}
$after = $before.Replace($original, $mapped).Replace($permissiveCheck, $strictCheck)
Copy-Item -LiteralPath $source -Destination $output -Recurse
[IO.File]::WriteAllText((Join-Path $output 'PKGBUILD'), $after, [Text.UTF8Encoding]::new($false))
Assert-CohortInventory $source $files
foreach ($entry in $files | Where-Object Path -CNE 'PKGBUILD') {
    if ((Get-FileHash -LiteralPath (Join-Path $output $entry.Path)).Hash.ToLowerInvariant() -cne $entry.SHA256) {
        throw "Recipe companion changed: $($entry.Path)"
    }
}
[ordered]@{
    Status = 'namespace-and-strict-check-prepared-not-package-admitted'
    Source = $source; Output = $output; BeforeSHA256 = $expected
    AfterSHA256 = (Get-FileHash -LiteralPath (Join-Path $output 'PKGBUILD')).Hash.ToLowerInvariant()
    Changes = @('Declare project MINGWARM64 environment', 'Propagate real CTest failure')
    Preserved = 'Pinned version, sources, signatures, compiler/CMake/Ninja requirements, shared and static builds, installation layout'
}
