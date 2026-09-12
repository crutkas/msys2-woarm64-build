#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [switch] $BootstrapAutotools,
    [switch] $BootstrapMsysGenerators
)
$ErrorActionPreference = 'Stop'
if ((Get-FileHash -LiteralPath (Join-Path $SourceDirectory 'PKGBUILD')).Hash.ToLowerInvariant() -cne
    '8a4a54a964eab7efa313e2faa8267052bc237ef61f8adf82a55cc93f4028db8a') {
    throw 'Only the pinned zlib/minizip 1.3.2-2 recipe is supported.'
}
$patch = Join-Path $PSScriptRoot '..\..\patches\zlib\1165.patch'
$patchHash = '0774e1368851504115f732f66230ca4a8a9cd60d4ba014502f65cc19b0b4d8bc'
if ((Get-FileHash -LiteralPath $patch).Hash.ToLowerInvariant() -cne $patchHash) {
    throw 'Vendored zlib patch differs from the original upstream recipe checksum.'
}
$result = & "$PSScriptRoot\prepare-pinned-mingwarm64-recipe.ps1" @PSBoundParameters
$path = Join-Path $OutputDirectory 'PKGBUILD'
$text = [IO.File]::ReadAllText($path)
$url = 'https://patch-diff.githubusercontent.com/raw/madler/zlib/pull/1165.patch'
$layout = 'build-mz-${MSYSTEM}'
$configure = '  ../${_realname}-${pkgver}/contrib/minizip/configure \'
foreach ($anchor in @(@{Text=$url;Count=1},@{Text=$layout;Count=3},@{Text=$configure;Count=1})) {
    if ([regex]::Matches($text,[regex]::Escape($anchor.Text)).Count -ne $anchor.Count) {
        throw "Unexpected pinned zlib recipe anchor: $($anchor.Text)"
    }
}
$dependencyFlags = @'
  CPPFLAGS="${CPPFLAGS:+${CPPFLAGS} }-idirafter ${MINGW_PREFIX}/include" \
  LDFLAGS="${LDFLAGS:+${LDFLAGS} }-L${MINGW_PREFIX}/lib" \
  "${srcdir}/${_realname}-${pkgver}/contrib/minizip/configure" \
'@
Copy-Item -LiteralPath $patch -Destination (Join-Path $OutputDirectory '1165.patch')
# Minizip's own AM_LDFLAGS selects zlib two build directories above it.
$text = $text.Replace($url,"'1165.patch'").Replace($layout,'build-${MSYSTEM}/contrib/minizip').
    Replace($configure,$dependencyFlags).Replace("`r`n","`n")
[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))
$result.Status = 'pinned-zlib-minizip-layout-and-source-prepared-not-package-admitted'
$result.RecipeSHA256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$result.VendoredPatch = @{SHA256=$patchHash;Commit='36ff1be48ef696cc67b0855f7c8537ce0276210d';Change='Original exact nine-digit Git diff index format, not changed patch body/checksum'}
$result.Change = 'Declare MINGWARM64/bootstrap generators as requested; vendor exact pinned PR bytes; place minizip below the fresh zlib build and select actual bzip2 dependency include/library roots'
$result.Preserved = 'Original archive/signature/patch checksums, both package splits, static/shared libraries, minizip demos+bzip2 support, all checks/install operations'
$result
