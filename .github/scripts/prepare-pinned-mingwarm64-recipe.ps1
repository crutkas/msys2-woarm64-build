#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [switch] $BootstrapAutotools,
    [switch] $BootstrapMsysGenerators
)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\cohort-inventory.ps1"
$source = (Resolve-Path -LiteralPath $SourceDirectory).ProviderPath.TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) { throw 'Prepared recipe output must be new.' }
if ($output.StartsWith("$source\", [StringComparison]::OrdinalIgnoreCase)) { throw 'Prepared recipe must be outside its source.' }
$inventoryHash = 'f99983a3c4db4687811dd73dbadbafc55616dbc80789844234a23f1560292ebd'
if ((Get-FileHash -LiteralPath $RecipeInventory).Hash.ToLowerInvariant() -cne $inventoryHash) {
    throw 'Only the preserved pinned MINGW-packages inventory is accepted.'
}
$inventory = Get-Content -Raw -LiteralPath $RecipeInventory | ConvertFrom-Json -AsHashtable
$name = Split-Path -Leaf $source
$members = @($inventory.files.GetEnumerator() | Where-Object { $_.Key.StartsWith("$name/", [StringComparison]::Ordinal) } | ForEach-Object {
    @{Path=$_.Key.Substring($name.Length+1).Replace('/','\');SHA256=$_.Value.sha256}
})
Assert-CohortInventory $source $members
$before = [IO.File]::ReadAllText("$source\PKGBUILD").Replace("`r`n", "`n")
$declarations = [regex]::Matches($before, '(?m)^mingw_arch=\([^\r\n]*\)$')
if ($declarations.Count -ne 1 -or $declarations[0].Value.Contains("'mingwarm64'")) {
    throw 'Expected one unchanged upstream mingw_arch declaration.'
}
$old = $declarations[0].Value
$new = $old.Substring(0,$old.Length-1) + " 'mingwarm64')"
$text = $before.Replace($old,$new)
$bootstrapDependencies = @()
if ($BootstrapMsysGenerators -and -not $BootstrapAutotools) {
    throw 'MSYS host generators require the explicit autotools bootstrap route.'
}
if ($BootstrapAutotools) {
    if ($name -cnotin @('mingw-w64-gettext','mingw-w64-libiconv','mingw-w64-ncurses','mingw-w64-bzip2','mingw-w64-zlib')) {
        throw 'Direct bootstrap generator dependencies are not declared for this recipe.'
    }
    $aggregate = '"${MINGW_PACKAGE_PREFIX}-autotools"'
    if ([regex]::Matches($text,[regex]::Escape($aggregate)).Count -ne 1) { throw 'Expected one autotools build-dependency aggregate.' }
    $libtool = if ($BootstrapMsysGenerators) { "'libtool'" } else { '"${MINGW_PACKAGE_PREFIX}-libtool"' }
    $direct = @(
        "'autoconf'", "'automake'", "'make'",
        $libtool, '"${MINGW_PACKAGE_PREFIX}-pkgconf"'
    )
    $text = $text.Replace($aggregate,($direct -join ' '))
    $bootstrapDependencies = $direct
}
Copy-Item -LiteralPath $source -Destination $output -Recurse
[IO.File]::WriteAllText("$output\PKGBUILD", $text, [Text.UTF8Encoding]::new($false))
Assert-CohortInventory $source $members
foreach ($member in $members | Where-Object Path -CNE 'PKGBUILD') {
    if ((Get-FileHash -LiteralPath (Join-Path $output $member.Path)).Hash.ToLowerInvariant() -cne $member.SHA256) {
        throw "Prepared recipe companion changed: $($member.Path)"
    }
}
[ordered]@{
    Status='namespace-prepared-not-package-admitted';Source=$source;Output=$output
    Upstream=$inventory.source;InventorySHA256=$inventoryHash;SourceFiles=$members
    RecipeSHA256=(Get-FileHash -LiteralPath "$output\PKGBUILD").Hash.ToLowerInvariant()
    Preserved='All source pins, runtime dependencies, package splits, feature defaults and function bodies'
    BootstrapAutotools=[bool]$BootstrapAutotools;DirectGeneratorDependencies=$bootstrapDependencies
    BootstrapMsysGenerators=[bool]$BootstrapMsysGenerators
    GeneratorScope=$(if ($BootstrapMsysGenerators) {
        'Real installed MSYS host libtoolize/m4 generators; may be emulated x64, not a native target libtool/libltdl provider'
    } else { 'Existing native generator dependency convention' })
    Change=$(if ($BootstrapAutotools) {
        'Declare MINGWARM64 and replace circular autotools aggregate with real direct generator packages; no provider fabricated'
    } else { 'Declare project MINGWARM64 environment only; actual compiler/package acceptance remains required' })
}
