$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\..\.github\scripts\msys\manifest-contract.ps1"
$epochScript = Join-Path $PSScriptRoot '..\..\.github\scripts\get-toolchain-epoch.ps1'

# Schema-only data, with no corresponding files or acceptance result. These
# declarations must never be treated as a qualified toolchain test fixture.
$roles = [ordered]@{
    GCC = 'bin\gcc.exe'; GXX = 'bin\g++.exe'; CC1 = 'libexec\cc1.exe'; CC1Plus = 'libexec\cc1plus.exe'
    Assembler = 'bin\as.exe'; Linker = 'bin\ld.exe'; Ar = 'bin\ar.exe'; Ranlib = 'bin\ranlib.exe'; Windres = 'bin\windres.exe'
    CRT0 = 'aarch64-pc-cygwin\lib\crt0.o'; CRTBegin = 'lib\crtbegin.o'; CRTEnd = 'lib\crtend.o'
    Libgcc = 'lib\libgcc.a'; Libstdcxx = 'lib\libstdc++.a'; MsysImport = 'aarch64-pc-cygwin\lib\libmsys-2.0.a'
    RuntimeDll = 'bin\msys-2.0.dll'; Specs = 'lib\gcc\aarch64-pc-cygwin\15.0.1\specs'
}
$files = @()
$components = @{}
foreach ($entry in $roles.GetEnumerator()) {
    $binding = @{ Path = $entry.Value; SHA256 = 'a' * 64 }
    $files += $binding
    $components[$entry.Key] = $binding
}
$sourceLock = @{ Path = 'share\toolchain\source-lock.json'; SHA256 = 'b' * 64 }
$profile = @{ Path = 'share\toolchain\msys-profile.json'; SHA256 = 'c' * 64 }
$sysrootManifest = @{ Path = 'share\toolchain\identities\runtime-inputs.sha256'; SHA256 = 'd' * 64 }
$dllManifest = @{ Path = 'share\toolchain\identities\runtime-dll.sha256'; SHA256 = 'e' * 64 }
$files += @($sourceLock, $profile, $sysrootManifest, $dllManifest)
$declaration = @{
    SchemaVersion = 1; Status = 'qualified'; Prefix = 'C:\nonexistent-schema-fixture'
    Host = @{ Triple = 'aarch64-w64-mingw32'; Machine = '0xAA64'; Runtime = 'UCRT' }
    Target = @{ Triple = 'aarch64-pc-cygwin'; Profile = 'MSYS'; DataModel = 'LP64'; ThreadModel = 'posix' }
    Sysroot = 'aarch64-pc-cygwin'; Files = $files; Components = $components
    EpochSHA256 = & $epochScript -Inputs $files
    SourceLock = $sourceLock; ProfileManifest = $profile
    Acceptance = @{ Path = 'C:\absent-evidence\result.json'; SHA256 = 'f' * 64
        ToolIdentitiesPath = 'C:\absent-evidence\tool-identities.json'; ToolIdentitiesSHA256 = '0' * 64 }
    RuntimePairing = @{ SourceSysroot = '/root/fixture/sysroot'; SourceDll = '/root/fixture/msys-2.0.dll'
        SysrootManifest = $sysrootManifest; DllManifest = $dllManifest }
}
$json = $declaration | ConvertTo-Json -Depth 10
$valid = $json | ConvertFrom-Json -AsHashtable
$result = @(Assert-NativeMsysDeclaration $valid)
if ($result.Count -ne 0) { throw 'Structural validation must not emit an acceptance verdict.' }
'PASS: agreed declaration schema emits no native acceptance verdict'

$cases = @(
    @{ Name = 'missing qualified status'; Mutate = { param($d) $d.Remove('Status') } },
    @{ Name = 'false qualified status'; Mutate = { param($d) $d.Status = $false } },
    @{ Name = 'staged status'; Mutate = { param($d) $d.Status = 'staged' } },
    @{ Name = 'string schema version'; Mutate = { param($d) $d.SchemaVersion = '1' } },
    @{ Name = 'x64 host'; Mutate = { param($d) $d.Host.Machine = '0x8664' } },
    @{ Name = 'MSYS-hosted driver'; Mutate = { param($d) $d.Host.Runtime = 'MSYS' } },
    @{ Name = 'MinGW target'; Mutate = { param($d) $d.Target.Triple = 'aarch64-w64-mingw32' } },
    @{ Name = 'Cygwin profile'; Mutate = { param($d) $d.Target.Profile = 'Cygwin' } },
    @{ Name = 'LLP64 target'; Mutate = { param($d) $d.Target.DataModel = 'LLP64' } },
    @{ Name = 'win32 threads'; Mutate = { param($d) $d.Target.ThreadModel = 'win32' } },
    @{ Name = 'empty file inventory'; Mutate = { param($d) $d.Files = @() } },
    @{ Name = 'case-aliased duplicate'; Mutate = { param($d) $d.Files += @{ Path = 'BIN\GCC.EXE'; SHA256 = 'a' * 64 } } },
    @{ Name = 'traversal'; Mutate = { param($d) $d.Files[0].Path = '..\outside.exe' } },
    @{ Name = 'absolute member'; Mutate = { param($d) $d.Files[0].Path = 'C:\outside.exe' } },
    @{ Name = 'alternate data stream'; Mutate = { param($d) $d.Files[0].Path = 'bin\gcc.exe:stream' } },
    @{ Name = 'trailing-dot member'; Mutate = { param($d) $d.Files[0].Path = 'bin\gcc.exe.' } },
    @{ Name = 'baseline overrides'; Mutate = { param($d) $d.ChangedFile = 'lib\libgcc.a' } },
    @{ Name = 'wrong epoch'; Mutate = { param($d) $d.EpochSHA256 = '0' * 64 } },
    @{ Name = 'missing runtime component'; Mutate = { param($d) $d.Components.Remove('RuntimeDll') } },
    @{ Name = 'unbound compiler component'; Mutate = { param($d) $d.Components.GCC.SHA256 = 'f' * 64 } },
    @{ Name = 'wrong sysroot'; Mutate = { param($d) $d.Sysroot = 'mingw' } },
    @{ Name = 'unbound profile manifest'; Mutate = { param($d) $d.ProfileManifest.SHA256 = 'f' * 64 } },
    @{ Name = 'unbound source lock'; Mutate = { param($d) $d.SourceLock.SHA256 = 'f' * 64 } },
    @{ Name = 'missing runtime pairing'; Mutate = { param($d) $d.Remove('RuntimePairing') } },
    @{ Name = 'relative runtime source'; Mutate = { param($d) $d.RuntimePairing.SourceDll = 'msys-2.0.dll' } },
    @{ Name = 'unbound runtime input manifest'; Mutate = { param($d) $d.RuntimePairing.SysrootManifest.SHA256 = 'f' * 64 } },
    @{ Name = 'missing tool identities'; Mutate = { param($d) $d.Acceptance.Remove('ToolIdentitiesPath') } }
)
foreach ($case in $cases) {
    $invalid = $json | ConvertFrom-Json -AsHashtable
    $null = & $case.Mutate $invalid
    $rejected = $false
    try { Assert-NativeMsysDeclaration $invalid } catch {
        if ($_.Exception.Message -notlike 'Invalid native MSYS contract:*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw "Declaration accepted: $($case.Name)" }
    "PASS: $($case.Name)"
}
