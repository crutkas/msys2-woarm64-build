$ErrorActionPreference = 'Stop'
$verifier = Join-Path $PSScriptRoot '..\..\.github\scripts\msys\test-msys-profile.ps1'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
$prefix = Join-Path $temporary 'profile fixture'
$specsPath = Join-Path $prefix 'lib\gcc\aarch64-pc-cygwin\15.0.1\specs'
$compilerPath = Join-Path $prefix 'bin\gcc.exe'
$manifestPath = Join-Path $temporary 'profile.json'
$utf8 = [Text.UTF8Encoding]::new($false)
$specs = "*cpp:`n`n*self_spec:`n -D__MSYS__`n*lib:`n%{!nostdlib:-lmsys-2.0}`n*link:`n_msys_dll_entry _msys_dll_entry --dll-search-prefix=msys-`n"
New-Item -ItemType Directory -Path (Split-Path $specsPath), (Split-Path $compilerPath) -Force | Out-Null
try {
    # Deliberately non-executable fixture: this suite cannot qualify a compiler.
    [IO.File]::WriteAllText($compilerPath, 'NOT A COMPILER', $utf8)
    [IO.File]::WriteAllText($specsPath, $specs, $utf8)
    $profile = @{
        schemaVersion = 1
        target = 'aarch64-pc-cygwin'
        compiler = $compilerPath
        compilerSha256 = (Get-FileHash -LiteralPath $compilerPath).Hash.ToLowerInvariant()
        originalSpecsSha256 = 'a' * 64
        specs = $specsPath
        specsSha256 = (Get-FileHash -LiteralPath $specsPath).Hash.ToLowerInvariant()
        scope = 'Source-only profile parser fixture; not executable or qualified'
        profileMode = 'default'
    }
    function Save-Profile($Value) {
        [IO.File]::WriteAllText($manifestPath, ($Value | ConvertTo-Json -Depth 4), $utf8)
    }
    function Assert-Rejected([string] $Name) {
        $rejected = $false
        try { $null = & $verifier -Prefix $prefix -ProfileManifest $manifestPath } catch {
            if ($_.Exception.Message -notlike 'Invalid MSYS default profile:*') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw "Fixture unexpectedly accepted: $Name" }
        "PASS: $Name"
    }
    Save-Profile $profile
    $result = & $verifier -Prefix $prefix -ProfileManifest $manifestPath
    if ($result.Kind -cne 'msys-default-profile-binding' -or $null -ne $result.PSObject.Properties['Passed']) {
        throw 'Profile parser must not emit a native acceptance verdict.'
    }
    'PASS: source-only self_spec profile accepted without cpp definition, no native acceptance verdict'

    foreach ($case in @(
        @{ Name = 'MinGW target'; Field = 'target'; Value = 'aarch64-w64-mingw32' },
        @{ Name = 'overlay profile'; Field = 'profileMode'; Value = 'overlay' },
        @{ Name = 'string schema'; Field = 'schemaVersion'; Value = '1' },
        @{ Name = 'compiler hash drift'; Field = 'compilerSha256'; Value = '0' * 64 },
        @{ Name = 'specs hash drift'; Field = 'specsSha256'; Value = '0' * 64 },
        @{ Name = 'incomplete manifest'; Field = 'originalSpecsSha256'; Value = $null }
    )) {
        $invalid = $profile.Clone()
        $invalid[$case.Field] = $case.Value
        Save-Profile $invalid
        Assert-Rejected $case.Name
    }
    foreach ($case in @(
        @{ Name = 'missing MSYS macro'; Text = $specs.Replace('-D__MSYS__', '-D__CYGWIN__') },
        @{ Name = 'legacy cpp-only macro with empty self_spec'; Text = $specs.Replace("*cpp:`n`n*self_spec:`n -D__MSYS__", "*cpp:`n-D__MSYS__`n*self_spec:`n") },
        @{ Name = 'legacy cpp-only profile without self_spec'; Text = $specs.Replace("*cpp:`n`n*self_spec:`n -D__MSYS__", "*cpp:`n-D__MSYS__") },
        @{ Name = 'duplicate empty self_spec'; Text = $specs + "*self_spec:`n`n" },
        @{ Name = 'Cygwin library'; Text = $specs.Replace('-lmsys-2.0', '-lcygwin') },
        @{ Name = 'Cygwin entry'; Text = $specs.Replace('_msys_dll_entry', '_cygwin_dll_entry') },
        @{ Name = 'Cygwin DLL prefix'; Text = $specs.Replace('--dll-search-prefix=msys-', '--dll-search-prefix=cyg') },
        @{ Name = 'duplicate lib section'; Text = $specs + "*lib:`n-lmsys-2.0`n" }
    )) {
        [IO.File]::WriteAllText($specsPath, $case.Text, $utf8)
        $invalid = $profile.Clone()
        $invalid.specsSha256 = (Get-FileHash -LiteralPath $specsPath).Hash.ToLowerInvariant()
        Save-Profile $invalid
        Assert-Rejected $case.Name
    }
    [IO.File]::WriteAllText($specsPath, $specs, $utf8)
    $overlay = Join-Path (Split-Path $specsPath) 'msys2.specs'
    Copy-Item -LiteralPath $specsPath -Destination $overlay
    $invalid = $profile.Clone()
    $invalid.specs = $overlay
    Save-Profile $invalid
    Assert-Rejected 'overlay filename falsely labeled default'
    $outside = Join-Path $temporary 'gcc.exe'
    Copy-Item -LiteralPath $compilerPath -Destination $outside
    $invalid = $profile.Clone()
    $invalid.compiler = $outside
    Save-Profile $invalid
    Assert-Rejected 'compiler outside supplied prefix'
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
