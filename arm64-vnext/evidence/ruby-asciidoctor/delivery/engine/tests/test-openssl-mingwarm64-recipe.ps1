#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$prepare = "$PSScriptRoot\..\.github\scripts\prepare-openssl-mingwarm64-recipe.ps1"
$arguments = @{SourceDirectory=$SourceDirectory;RecipeInventory=$RecipeInventory;OutputDirectory=$OutputDirectory}
$null = & $prepare @arguments
$before = [IO.File]::ReadAllText("$SourceDirectory\PKGBUILD").Replace("`r`n","`n")
$after = [IO.File]::ReadAllText("$OutputDirectory\PKGBUILD")
$oldCheck = [regex]::Match($before,'(?ms)^check\(\) \{.*?^\}').Value
$newCheck = [regex]::Match($after,'(?ms)^check\(\) \{.*?^\}').Value
if (-not $newCheck.Contains('/usr/bin/perl "$PWD/util/wrap.pl" /bin/bash "$native_exec"') -or
    -not $newCheck.Contains('make VERBOSE=1 test TESTS=') -or
    -not $newCheck.Contains('export EXE_SHELL HARNESS_JOBS="$jobs"')) {
    throw 'OpenSSL native checks lost wrapper setup, full selection, or job bound.'
}
$dependencyFlags = @'
  CPPFLAGS="${CPPFLAGS:+${CPPFLAGS} }-idirafter ${MINGW_PREFIX}/include" \
  LDFLAGS="${LDFLAGS:+${LDFLAGS} }-L${MINGW_PREFIX}/lib" \
  MSYS2_ARG_CONV_EXCL="--prefix=" \
'@
$dependencyFlags = $dependencyFlags.Replace("`r`n","`n")
if (-not $after.Contains($dependencyFlags)) { throw 'Separate native dependency root is missing.' }
$reversed = $after.Replace($newCheck,$oldCheck).
    Replace('"perl" "make" "${MINGW_PACKAGE_PREFIX}-zlib"','"${MINGW_PACKAGE_PREFIX}-autotools"').
    Replace($dependencyFlags,'  MSYS2_ARG_CONV_EXCL="--prefix=" \').
    Replace(" 'mingwarm64')",")")
if ($reversed -cne $before) { throw 'OpenSSL source/features/build/install were changed outside the declared repair.' }
'PASS: original OpenSSL source/features/build/install preserved with explicit generator and native-test boundaries'
$rejected = $false
try { $null = & $prepare @arguments } catch {
    if ($_.Exception.Message -cne 'Prepared recipe output must be new.') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Existing prepared recipe was overwritten.' }
'PASS: existing recipe output is preserved'
