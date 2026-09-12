#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\cohort-inventory.ps1"
$source = (Resolve-Path -LiteralPath $SourceDirectory).ProviderPath.TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) { throw 'Prepared xmlto recipe output must be new.' }
if ($output.StartsWith("$source\", [StringComparison]::OrdinalIgnoreCase)) { throw 'Prepared recipe must be outside its source.' }
$expected = 'b916ae391da896bb7246fe6e4747c2f48fa2aa3e9cacb7251e7096a658c1880e'
if ((Get-FileHash -LiteralPath "$source\PKGBUILD").Hash.ToLowerInvariant() -cne $expected) {
    throw 'Only the pinned xmlto 0.0.28-2 recipe is supported.'
}
$files = @(Get-CohortInventory $source)
$patch = [IO.Path]::GetFullPath("$PSScriptRoot\..\..\patches\xmlto\0001-explicit-int.patch")
$patchHash = (Get-FileHash -LiteralPath $patch).Hash.ToLowerInvariant()
$text = [IO.File]::ReadAllText("$source\PKGBUILD").Replace("`r`n", "`n")
$prepare = @'
source+=('0001-explicit-int.patch')
sha256sums+=('@PATCH_SHA256@')

prepare() {
  cd "${srcdir}/${pkgname}-${pkgver}"
  patch --batch --forward -p1 -i "${srcdir}/0001-explicit-int.patch"
}

build() {
'@
foreach ($token in 'pkgrel=2', 'build() {') {
    if ([regex]::Matches($text, [regex]::Escape($token)).Count -ne 1) { throw 'Unexpected pinned xmlto recipe structure.' }
}
$text = $text.Replace('pkgrel=2', 'pkgrel=3').Replace('build() {', $prepare.Replace('@PATCH_SHA256@', $patchHash)).Replace("`r`n", "`n")
Copy-Item -LiteralPath $source -Destination $output -Recurse
Copy-Item -LiteralPath $patch -Destination "$output\0001-explicit-int.patch"
[IO.File]::WriteAllText("$output\PKGBUILD", $text, [Text.UTF8Encoding]::new($false))
Assert-CohortInventory $source $files
[ordered]@{
    Source=$source;Output=$output;OriginalRecipeSHA256=$expected
    RecipeSHA256=(Get-FileHash -LiteralPath "$output\PKGBUILD").Hash.ToLowerInvariant()
    Patch=@{Path=$patch;SHA256=$patchHash};Version='0.0.28-3'
    Change='Explicit int for ifsense and main in scanner source and generated C; no language/warning downgrade'
    Preserved='Original release archive/hash, MSYS architecture declaration, dependencies, compiler defaults, build/install functions'
}
