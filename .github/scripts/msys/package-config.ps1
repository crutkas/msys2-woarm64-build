#requires -Version 7.3

function ConvertTo-MsysConfigLiteral([string] $Value) {
    if ([string]::IsNullOrEmpty($Value) -or $Value -match '[\x00-\x1f]') {
        throw 'MSYS package config values must be nonempty and contain no control characters.'
    }
    "'" + $Value.Replace("'", "'\''") + "'"
}

function New-MsysPackageConfigText(
    [string] $NativeBin,
    [string] $Sysroot,
    [string] $OutputRoot,
    [int] $Jobs
) {
    if ($Jobs -lt 1 -or $Jobs -gt 16) { throw 'MSYS package config requires an explicit 1-16 job allocation.' }
    foreach ($path in $NativeBin, $Sysroot, $OutputRoot) {
        if (-not $path.StartsWith('/') -or $path -match '(^|/)\.\.?(/|$)') {
            throw 'MSYS package config requires absolute normalized MSYS paths.'
        }
    }
    $binLiteral = ConvertTo-MsysConfigLiteral $NativeBin
    $sysrootLiteral = ConvertTo-MsysConfigLiteral $Sysroot
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add('source /etc/makepkg.conf')
    $lines.Add('export MSYSTEM=MSYS')
    $lines.Add('CARCH=aarch64')
    $lines.Add('CHOST=aarch64-pc-cygwin')
    $lines.Add('CC=gcc')
    $lines.Add('CXX=g++')
    $lines.Add('export AR=ar AS=as LD=ld RANLIB=ranlib WINDRES=windres RC=windres STRIP=strip OBJCOPY=objcopy OBJDUMP=objdump')
    $lines.Add('CPPFLAGS=')
    $lines.Add("CFLAGS='-O2 -pipe'")
    $lines.Add('CXXFLAGS="$CFLAGS"')
    $lines.Add('LDFLAGS=')
    $lines.Add("MAKEFLAGS=-j$Jobs")
    $lines.Add("export CMAKE_BUILD_PARALLEL_LEVEL=$Jobs")
    $lines.Add("export CTEST_PARALLEL_LEVEL=$Jobs")
    $lines.Add('export PATH=' + $binLiteral + ':"$PATH"')
    $lines.Add('export PKG_CONFIG_SYSROOT_DIR=' + $sysrootLiteral)
    $lines.Add('export PKG_CONFIG_LIBDIR=' + $sysrootLiteral + '/lib/pkgconfig:' + $sysrootLiteral + '/share/pkgconfig')
    $lines.Add('unset PKG_CONFIG_PATH')
    foreach ($pair in @(
        @('BUILDDIR', 'build'), @('SRCDEST', 'sources'), @('SRCPKGDEST', 'source-packages'),
        @('LOGDEST', 'logs'), @('PKGDEST', 'packages')
    )) {
        $lines.Add('export ' + $pair[0] + '=' + (ConvertTo-MsysConfigLiteral "$OutputRoot/$($pair[1])"))
    }
    # The launcher must also export these destinations before makepkg loads this
    # config, because libmakepkg restores inherited destination values afterward.
    ($lines -join "`n") + "`n"
}
