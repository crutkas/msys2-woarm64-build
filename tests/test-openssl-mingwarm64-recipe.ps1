#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $RecipeInventory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$prepare = "$PSScriptRoot\..\.github\scripts\prepare-openssl-mingwarm64-recipe.ps1"
$arguments = @{SourceDirectory=$SourceDirectory;RecipeInventory=$RecipeInventory;OutputDirectory=$OutputDirectory}
$result = & $prepare @arguments
$before = [IO.File]::ReadAllText("$SourceDirectory\PKGBUILD").Replace("`r`n","`n")
$after = [IO.File]::ReadAllText("$OutputDirectory\PKGBUILD")
$oldCheck = [regex]::Match($before,'(?ms)^check\(\) \{.*?^\}').Value
$newCheck = [regex]::Match($after,'(?ms)^check\(\) \{.*?^\}').Value
if (-not $newCheck.Contains('/usr/bin/perl "$PWD/util/wrap.pl" /bin/bash "$native_exec"') -or
    -not $newCheck.Contains('make test TESTS=') -or
    -not $newCheck.Contains('export EXE_SHELL HARNESS_JOBS="$jobs" OPENSSL_WIN32_UTF8=1 PERLIO=crlf') -or
    -not $newCheck.Contains('export WOARM64_NATIVE_TARGET_OS=MSWin32') -or
    -not $newCheck.Contains('export WOARM64_NATIVE_ARG_CONVERSION=paths')) {
    throw 'OpenSSL native checks lost wrapper setup, full selection, argument preservation, or job bound.'
}
$dependencyFlags = @'
  CPPFLAGS="${CPPFLAGS:+${CPPFLAGS} }-idirafter ${MINGW_PREFIX}/include" \
  LDFLAGS="${LDFLAGS:+${LDFLAGS} }-L${MINGW_PREFIX}/lib" \
  MSYS2_ARG_CONV_EXCL="--prefix=" \
'@.Replace("`r`n","`n")
if (-not $after.Contains($dependencyFlags)) { throw 'Separate native dependency root is missing.' }
$lifecycleRepairName = '0001-native-test-relay-lifecycle.pl'
$stdinRepairName = '0002-windows-redirected-stdin-ready.patch'
$platformRepairName = '0003-native-mingw-test-platform.pl'
$rcuRepairName = '0004-native-mingw-rcu-memory-order.pl'
$lifecycleRepairPath = Join-Path $OutputDirectory $lifecycleRepairName
$stdinRepairPath = Join-Path $OutputDirectory $stdinRepairName
$platformRepairPath = Join-Path $OutputDirectory $platformRepairName
$rcuRepairPath = Join-Path $OutputDirectory $rcuRepairName
if (-not (Test-Path -LiteralPath $lifecycleRepairPath) -or
    (Get-FileHash -LiteralPath $lifecycleRepairPath).Hash.ToLowerInvariant() -cne
        $result.LifecycleRepairSourceSHA256 -or
    -not $after.Contains("'$lifecycleRepairName'") -or
    -not $after.Contains("'$($result.LifecycleRepairSourceSHA256)'") -or
    -not $after.Contains("/usr/bin/perl `"`${srcdir}/$lifecycleRepairName`"")) {
    throw 'OpenSSL lifecycle repair is not pinned into the prepared recipe.'
}
if (-not (Test-Path -LiteralPath $stdinRepairPath) -or
    (Get-FileHash -LiteralPath $stdinRepairPath).Hash.ToLowerInvariant() -cne
        $result.StdinRepairSourceSHA256 -or
    -not $after.Contains("'$stdinRepairName'") -or
    -not $after.Contains("'$($result.StdinRepairSourceSHA256)'") -or
    -not $after.Contains("     $stdinRepairName")) {
    throw 'OpenSSL redirected-stdin repair is not pinned into the prepared recipe.'
}
$stdinRepair = [IO.File]::ReadAllText($stdinRepairPath)
if (-not $stdinRepair.Contains('PeekNamedPipe(inhand, NULL, 0, NULL, &available, NULL)') -or
    -not $stdinRepair.Contains('GetLastError() == ERROR_BROKEN_PIPE')) {
    throw 'OpenSSL redirected-stdin repair lost pipe readiness or EOF handling.'
}
if (-not (Test-Path -LiteralPath $platformRepairPath) -or
    (Get-FileHash -LiteralPath $platformRepairPath).Hash.ToLowerInvariant() -cne
        $result.PlatformRepairSourceSHA256 -or
    -not $after.Contains("'$platformRepairName'") -or
    -not $after.Contains("'$($result.PlatformRepairSourceSHA256)'") -or
    -not $after.Contains("/usr/bin/perl `"`${srcdir}/$platformRepairName`"")) {
    throw 'OpenSSL native target-platform repair is not pinned into the prepared recipe.'
}
$platformRepair = [IO.File]::ReadAllText($platformRepairPath)
foreach ($required in "nm `$shlib_nm_flags", 'WOARM64_NATIVE_TARGET_OS', 'unexpected verify skip anchor', 'MinGW snprintf() overflows the stack', '"<:raw", $command_file') {
    if (-not $platformRepair.Contains($required)) {
        throw "OpenSSL target-platform repair lost required behavior: $required"
    }
}
if (-not (Test-Path -LiteralPath $rcuRepairPath) -or
    (Get-FileHash -LiteralPath $rcuRepairPath).Hash.ToLowerInvariant() -cne
        $result.RcuRepairSourceSHA256 -or
    -not $after.Contains("'$rcuRepairName'") -or
    -not $after.Contains("'$($result.RcuRepairSourceSHA256)'") -or
    -not $after.Contains("/usr/bin/perl `"`${srcdir}/$rcuRepairName`"")) {
    throw 'OpenSSL native RCU memory-order repair is not pinned into the prepared recipe.'
}
$rcuRepair = [IO.File]::ReadAllText($rcuRepairPath)
foreach ($required in '__atomic_load_n(p, __ATOMIC_ACQUIRE)', '__atomic_store_n(p, *v, __ATOMIC_RELEASE)', '23ad2f6fef6467ebfc8a85ae3e3458e565bdd74a36aa78c8c6a5156ee7afd823') {
    if (-not $rcuRepair.Contains($required)) {
        throw "OpenSSL native RCU memory-order repair lost required behavior: $required"
    }
}
$reversed = $after.Replace($newCheck,$oldCheck).
    Replace('"perl" "make" "${MINGW_PACKAGE_PREFIX}-zlib"','"${MINGW_PACKAGE_PREFIX}-autotools"').
    Replace($dependencyFlags,'  MSYS2_ARG_CONV_EXCL="--prefix=" \').
    Replace(
            "     004-arch-suffix.patch \`n" +
            "     $stdinRepairName`n`n" +
            "  /usr/bin/perl `"`${srcdir}/$lifecycleRepairName`"`n" +
            "  /usr/bin/perl `"`${srcdir}/$platformRepairName`"`n" +
            "  /usr/bin/perl `"`${srcdir}/$rcuRepairName`"`n",
            "     004-arch-suffix.patch`n").
    Replace(
        "        'pathtools.h'`n" +
        "        '$lifecycleRepairName'`n" +
        "        '$stdinRepairName'`n" +
        "        '$platformRepairName'`n" +
        "        '$rcuRepairName')",
        "        'pathtools.h')"
    ).
    Replace(
        "            '1585ef1b61cf53a2ca27049c11d49e0834683dfda798f03547761375df482a90'`n" +
        "            '$($result.LifecycleRepairSourceSHA256)'`n" +
        "            '$($result.StdinRepairSourceSHA256)'`n" +
        "            '$($result.PlatformRepairSourceSHA256)'`n" +
        "            '$($result.RcuRepairSourceSHA256)')",
        "            '1585ef1b61cf53a2ca27049c11d49e0834683dfda798f03547761375df482a90')"
    ).Replace(" 'mingwarm64')",")")
if ($reversed -cne $before) {
    throw 'OpenSSL source/features/build/install changed outside the declared native repair.'
}
'PASS: OpenSSL source/features/build/install and OCSP assertions preserved with explicit native lifecycle repair'
$rejected = $false
try { $null = & $prepare @arguments } catch {
    if ($_.Exception.Message -cne 'Prepared recipe output must be new.') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Existing prepared recipe was overwritten.' }
'PASS: existing recipe output is preserved'
