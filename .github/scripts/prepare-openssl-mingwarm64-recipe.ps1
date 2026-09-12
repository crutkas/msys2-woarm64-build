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
$lifecycleRepairName = '0001-native-test-relay-lifecycle.pl'
$stdinRepairName = '0002-windows-redirected-stdin-ready.patch'
$platformRepairName = '0003-native-mingw-test-platform.pl'
$rcuRepairName = '0004-native-mingw-rcu-memory-order.pl'
$lifecycleRepairSource = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\patches\openssl\$lifecycleRepairName")
)
$stdinRepairSource = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\patches\openssl\$stdinRepairName")
)
$platformRepairSource = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\patches\openssl\$platformRepairName")
)
$rcuRepairSource = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..\patches\openssl\$rcuRepairName")
)
$lifecycleRepairPath = Join-Path $OutputDirectory $lifecycleRepairName
$stdinRepairPath = Join-Path $OutputDirectory $stdinRepairName
$platformRepairPath = Join-Path $OutputDirectory $platformRepairName
$rcuRepairPath = Join-Path $OutputDirectory $rcuRepairName
Copy-Item -LiteralPath $lifecycleRepairSource -Destination $lifecycleRepairPath
Copy-Item -LiteralPath $stdinRepairSource -Destination $stdinRepairPath
Copy-Item -LiteralPath $platformRepairSource -Destination $platformRepairPath
Copy-Item -LiteralPath $rcuRepairSource -Destination $rcuRepairPath
foreach ($repairPath in $lifecycleRepairPath, $platformRepairPath, $rcuRepairPath) {
    $repairText = [IO.File]::ReadAllText($repairPath).Replace("`r`n", "`n")
    [IO.File]::WriteAllText($repairPath, $repairText, [Text.UTF8Encoding]::new($false))
}
$lifecycleRepairHash = (Get-FileHash -LiteralPath $lifecycleRepairPath -Algorithm SHA256).Hash.ToLowerInvariant()
$stdinRepairHash = (Get-FileHash -LiteralPath $stdinRepairPath -Algorithm SHA256).Hash.ToLowerInvariant()
$platformRepairHash = (Get-FileHash -LiteralPath $platformRepairPath -Algorithm SHA256).Hash.ToLowerInvariant()
$rcuRepairHash = (Get-FileHash -LiteralPath $rcuRepairPath -Algorithm SHA256).Hash.ToLowerInvariant()
$aggregate = '"${MINGW_PACKAGE_PREFIX}-autotools"'
$check = '  make VERBOSE=1 test'
$configure = '  MSYS2_ARG_CONV_EXCL="--prefix=" \'
$sourceAnchor = "        'pathtools.h')"
$checksumAnchor = "            '1585ef1b61cf53a2ca27049c11d49e0834683dfda798f03547761375df482a90')"
$prepareAnchor = "     004-arch-suffix.patch`n"
foreach ($anchor in $aggregate, $check, $configure, $sourceAnchor, $checksumAnchor, $prepareAnchor) {
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
  export EXE_SHELL HARNESS_JOBS="$jobs" OPENSSL_WIN32_UTF8=1 PERLIO=crlf
  export WOARM64_NATIVE_TARGET_OS=MSWin32
  export WOARM64_NATIVE_ARG_CONVERSION=paths
  make test TESTS=
'@
$dependencyFlags = @'
  CPPFLAGS="${CPPFLAGS:+${CPPFLAGS} }-idirafter ${MINGW_PREFIX}/include" \
  LDFLAGS="${LDFLAGS:+${LDFLAGS} }-L${MINGW_PREFIX}/lib" \
  MSYS2_ARG_CONV_EXCL="--prefix=" \
'@
$text = $text.Replace(
        $sourceAnchor,
        "        'pathtools.h'`n" +
        "        '$lifecycleRepairName'`n" +
        "        '$stdinRepairName'`n" +
        "        '$platformRepairName'`n" +
        "        '$rcuRepairName')"
    ).Replace(
        $checksumAnchor,
        "            '1585ef1b61cf53a2ca27049c11d49e0834683dfda798f03547761375df482a90'`n" +
        "            '$lifecycleRepairHash'`n" +
        "            '$stdinRepairHash'`n" +
        "            '$platformRepairHash'`n" +
        "            '$rcuRepairHash')"
    ).Replace(
        $prepareAnchor,
        "     004-arch-suffix.patch \`n" +
        "     $stdinRepairName`n`n" +
        "  /usr/bin/perl `"`${srcdir}/$lifecycleRepairName`"`n" +
        "  /usr/bin/perl `"`${srcdir}/$platformRepairName`"`n" +
        "  /usr/bin/perl `"`${srcdir}/$rcuRepairName`"`n"
    )
# This recipe uses OpenSSL's Perl generator, not autoconf/automake/libtool.
$text = $text.Replace($aggregate,'"perl" "make" "${MINGW_PACKAGE_PREFIX}-zlib"').
    Replace($configure,$dependencyFlags).Replace($check,$nativeCheck).Replace("`r`n","`n")
[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))
$result.Status = 'namespace-and-native-test-relay-prepared-not-package-admitted'
$result.RecipeSHA256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$result.LifecycleRepairSource = $lifecycleRepairName
$result.LifecycleRepairSourceSHA256 = $lifecycleRepairHash
$result.StdinRepairSource = $stdinRepairName
$result.StdinRepairSourceSHA256 = $stdinRepairHash
$result.PlatformRepairSource = $platformRepairName
$result.PlatformRepairSourceSHA256 = $platformRepairHash
$result.RcuRepairSource = $rcuRepairName
$result.RcuRepairSourceSHA256 = $rcuRepairHash
$result.Change = 'Declare MINGWARM64, require actual Perl/Make and zlib inputs, preserve native arguments across Cygwin, drain the OCSP client before waiting, avoid blocking OpenSSL apps on empty redirected stdin pipes, and publish Windows RCU pointers with acquire-release ordering'
$result.Preserved = 'Pinned source/signature/upstream patches, ARM64 assembly, all feature flags, OCSP response assertions, shared libraries, full test selection, package metadata and install operations'
$result
