#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
if ((Get-FileHash -LiteralPath (Join-Path $SourceDirectory 'PKGBUILD')).Hash.ToLowerInvariant() -cne
    '0f29edf384ee561bfe195608f4dbbb4231695af7958e326292034b264bc5faf1') {
    throw 'Only the pinned OpenSSL 3.6.4-1 recipe is supported.'
}
$result = & "$PSScriptRoot\prepare-pinned-mingwarm64-recipe.ps1" @PSBoundParameters
$path = Join-Path $OutputDirectory 'PKGBUILD'
$text = [IO.File]::ReadAllText($path)
$aggregate = '"${MINGW_PACKAGE_PREFIX}-autotools"'
$check = '  make VERBOSE=1 test'
$configure = '  MSYS2_ARG_CONV_EXCL="--prefix=" \'
foreach ($anchor in $aggregate, $check, $configure) {
    if ([regex]::Matches($text,[regex]::Escape($anchor)).Count -ne 1) {
        throw "Unexpected pinned OpenSSL recipe anchor: $anchor"
    }
}
$nativeCheck = @'
  local jobs=${WOARM64_JOBS:?} native_exec
  [[ $jobs =~ ^[1-9][0-9]*$ && $jobs -le 16 ]] || return 1
  native_exec=$(cygpath -u "${WOARM64_NATIVE_EXEC:?}")
  [[ -f util/wrap.pl && -x util/shlib_wrap.sh ]] || {
    error 'The original OpenSSL test environment wrappers are required.'
    return 1
  }
  printf -v EXE_SHELL '%q ' /usr/bin/perl "$PWD/util/wrap.pl" /bin/bash "$native_exec"
  export EXE_SHELL HARNESS_JOBS="$jobs"
  make VERBOSE=1 test TESTS=
'@
$dependencyFlags = @'
  CPPFLAGS="${CPPFLAGS:+${CPPFLAGS} }-idirafter ${MINGW_PREFIX}/include" \
  LDFLAGS="${LDFLAGS:+${LDFLAGS} }-L${MINGW_PREFIX}/lib" \
  MSYS2_ARG_CONV_EXCL="--prefix=" \
'@
# This recipe uses OpenSSL's Perl generator, not autoconf/automake/libtool.
$text = $text.Replace($aggregate,'"perl" "make" "${MINGW_PACKAGE_PREFIX}-zlib"').
    Replace($configure,$dependencyFlags).Replace($check,$nativeCheck).Replace("`r`n","`n")
[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))
$result.Status = 'namespace-and-native-test-relay-prepared-not-package-admitted'
$result.RecipeSHA256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$result.Change = 'Declare MINGWARM64, require actual Perl/Make generators and native zlib development input, select the separate dependency include/library root, and relay native test calls through original OpenSSL environment wrappers'
$result.Preserved = 'Pinned source/signature/patches, ARM64 assembly, all feature flags, shared libraries, full test selection, package metadata and install operations'
$result
