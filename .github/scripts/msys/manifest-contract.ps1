#requires -Version 7.3
Set-StrictMode -Version Latest

function Stop-MsysContract([string] $Reason) {
    throw "Invalid native MSYS contract: $Reason"
}

function Assert-MsysObject($Value, [string] $Label) {
    if ($Value -isnot [Collections.IDictionary]) { Stop-MsysContract "$Label must be an object" }
}

function Assert-MsysFields($Value, [string[]] $Names, [string] $Label) {
    Assert-MsysObject $Value $Label
    foreach ($name in $Names) {
        if (-not $Value.Contains($name)) { Stop-MsysContract "$Label is missing $name" }
    }
}

function Assert-MsysString($Value, [string] $Label) {
    if ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value)) {
        Stop-MsysContract "$Label must be a nonempty string"
    }
}

function Assert-MsysDigest($Value, [string] $Label) {
    Assert-MsysString $Value $Label
    if ($Value -cnotmatch '^[0-9a-f]{64}$') { Stop-MsysContract "$Label must be a lowercase SHA256" }
}

function Assert-MsysRelativePath($Value, [string] $Label) {
    Assert-MsysString $Value $Label
    if ([IO.Path]::IsPathRooted($Value) -or $Value -match '[/:\x00-\x1f*?"<>|]' -or
        $Value -match '(^|\\)(\.{1,2}|)(\\|$)' -or $Value -match '[ .](\\|$)') {
        Stop-MsysContract "$Label must be a canonical relative backslash path"
    }
}

function Assert-MsysAbsolutePath($Value, [string] $Label) {
    Assert-MsysString $Value $Label
    if (-not [IO.Path]::IsPathFullyQualified($Value) -or $Value -match '[\x00-\x1f]') {
        Stop-MsysContract "$Label must be an absolute Windows path"
    }
}

function Assert-MsysBinding($Value, [string] $Label, [switch] $Absolute) {
    Assert-MsysFields $Value @('Path', 'SHA256') $Label
    if ($Absolute) { Assert-MsysAbsolutePath $Value.Path "$Label.Path" }
    else { Assert-MsysRelativePath $Value.Path "$Label.Path" }
    Assert-MsysDigest $Value.SHA256 "$Label.SHA256"
}

function Assert-NativeMsysDeclaration($Manifest) {
    Assert-MsysFields $Manifest @('SchemaVersion', 'Status', 'Prefix', 'Host', 'Target', 'Sysroot', 'Files',
        'EpochSHA256', 'Components', 'SourceLock', 'Acceptance', 'RuntimePairing', 'ProfileManifest') 'manifest'
    if ($Manifest.SchemaVersion -isnot [long] -or $Manifest.SchemaVersion -ne 1 -or
        $Manifest.Status -cne 'qualified') {
        Stop-MsysContract 'requires SchemaVersion 1 and explicit qualified status'
    }
    foreach ($legacy in 'BaselineFiles', 'ChangedFile', 'LibrarySHA256') {
        if ($Manifest.Contains($legacy)) { Stop-MsysContract 'baseline overrides are not part of the MSYS contract' }
    }
    Assert-MsysAbsolutePath $Manifest.Prefix 'Prefix'
    Assert-MsysFields $Manifest.Host @('Triple', 'Machine', 'Runtime') 'Host'
    if ($Manifest.Host.Triple -cne 'aarch64-w64-mingw32' -or $Manifest.Host.Machine -cne '0xAA64' -or
        $Manifest.Host.Runtime -cne 'UCRT') {
        Stop-MsysContract 'requires a Windows ARM64 UCRT-hosted compiler'
    }
    Assert-MsysFields $Manifest.Target @('Triple', 'Profile', 'DataModel', 'ThreadModel') 'Target'
    if ($Manifest.Target.Triple -cne 'aarch64-pc-cygwin' -or $Manifest.Target.Profile -cne 'MSYS' -or
        $Manifest.Target.DataModel -cne 'LP64' -or $Manifest.Target.ThreadModel -cne 'posix') {
        Stop-MsysContract 'requires the distinct aarch64-pc-cygwin MSYS LP64 POSIX target'
    }
    Assert-MsysRelativePath $Manifest.Sysroot 'Sysroot'
    if ($Manifest.Files -isnot [array] -or $Manifest.Files.Count -eq 0) {
        Stop-MsysContract 'Files must be a nonempty inventory'
    }
    $files = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($row in $Manifest.Files) {
        Assert-MsysBinding $row 'Files entry'
        if ($files.ContainsKey($row.Path)) { Stop-MsysContract "duplicate file path $($row.Path)" }
        $files.Add($row.Path, $row.SHA256)
    }
    Assert-MsysDigest $Manifest.EpochSHA256 'EpochSHA256'
    $epoch = & "$PSScriptRoot\..\get-toolchain-epoch.ps1" -Inputs $Manifest.Files
    if ($epoch -cne $Manifest.EpochSHA256) { Stop-MsysContract 'EpochSHA256 does not bind the full Files inventory' }
    Assert-MsysObject $Manifest.Components 'Components'
    $roles = @('GCC', 'GXX', 'CC1', 'CC1Plus', 'Assembler', 'Linker', 'Ar', 'Ranlib', 'Windres',
        'CRT0', 'CRTBegin', 'CRTEnd', 'Libgcc', 'Libstdcxx', 'MsysImport', 'RuntimeDll', 'Specs')
    Assert-MsysFields $Manifest.Components $roles 'Components'
    foreach ($role in $roles) {
        $entry = $Manifest.Components[$role]
        Assert-MsysBinding $entry "Components.$role"
        if (-not $files.ContainsKey($entry.Path) -or $files[$entry.Path] -cne $entry.SHA256) {
            Stop-MsysContract "Components.$role is not bound by Files"
        }
    }
    foreach ($role in 'CRT0', 'MsysImport') {
        if (-not $Manifest.Components[$role].Path.StartsWith("$($Manifest.Sysroot)\", [StringComparison]::Ordinal)) {
            Stop-MsysContract "Components.$role must belong to the declared sysroot"
        }
    }
    if ($Manifest.Components.Specs.Path -cnotmatch '^lib\\gcc\\aarch64-pc-cygwin\\[^\\]+\\specs$' -or
        [IO.Path]::GetFileName($Manifest.Components.RuntimeDll.Path) -cne 'msys-2.0.dll' -or
        [IO.Path]::GetFileName($Manifest.Components.MsysImport.Path) -cne 'libmsys-2.0.a') {
        Stop-MsysContract 'default specs, runtime DLL or import library has the wrong identity'
    }
    Assert-MsysBinding $Manifest.SourceLock 'SourceLock'
    if (-not $files.ContainsKey($Manifest.SourceLock.Path) -or
        $files[$Manifest.SourceLock.Path] -cne $Manifest.SourceLock.SHA256) {
        Stop-MsysContract 'SourceLock is not bound by Files'
    }
    Assert-MsysBinding $Manifest.Acceptance 'Acceptance' -Absolute
    Assert-MsysFields $Manifest.Acceptance @('ToolIdentitiesPath', 'ToolIdentitiesSHA256') 'Acceptance'
    Assert-MsysAbsolutePath $Manifest.Acceptance.ToolIdentitiesPath 'Acceptance.ToolIdentitiesPath'
    Assert-MsysDigest $Manifest.Acceptance.ToolIdentitiesSHA256 'Acceptance.ToolIdentitiesSHA256'
    Assert-MsysFields $Manifest.RuntimePairing @('SourceSysroot', 'SourceDll', 'SysrootManifest', 'DllManifest') 'RuntimePairing'
    foreach ($name in 'SourceSysroot', 'SourceDll') {
        $path = $Manifest.RuntimePairing[$name]
        Assert-MsysString $path "RuntimePairing.$name"
        if ($path -cnotmatch '^/[^\\\x00-\x1f]+$' -or $path -match '(^|/)\.\.?(/|$)') {
            Stop-MsysContract "RuntimePairing.$name must be the absolute Linux source-input path"
        }
    }
    foreach ($binding in @(
        @{ Name = 'ProfileManifest'; Value = $Manifest.ProfileManifest },
        @{ Name = 'RuntimePairing.SysrootManifest'; Value = $Manifest.RuntimePairing.SysrootManifest },
        @{ Name = 'RuntimePairing.DllManifest'; Value = $Manifest.RuntimePairing.DllManifest }
    )) {
        Assert-MsysBinding $binding.Value $binding.Name
        if (-not $files.ContainsKey($binding.Value.Path) -or $files[$binding.Value.Path] -cne $binding.Value.SHA256) {
            Stop-MsysContract "$($binding.Name) is not bound by Files"
        }
    }
}
