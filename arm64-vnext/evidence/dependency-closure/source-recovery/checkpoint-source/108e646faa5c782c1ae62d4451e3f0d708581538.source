function New-MsysReaderFixture([string] $Directory) {
    $prefix = Join-Path $Directory 'not-a-native-toolchain'
    $proofPath = Join-Path $Directory 'fixture-proof.json'
    $toolsPath = Join-Path $Directory 'fixture-tools.json'
    $manifestPath = Join-Path $Directory 'fixture-manifest.json'
    $utf8 = [Text.UTF8Encoding]::new($false)
    $paths = [ordered]@{
        GCC = 'bin\gcc.exe'; GXX = 'bin\g++.exe'; CC1 = 'libexec\cc1.exe'; CC1Plus = 'libexec\cc1plus.exe'
        Assembler = 'bin\as.exe'; Linker = 'bin\ld.exe'; Ar = 'bin\ar.exe'; Ranlib = 'bin\ranlib.exe'; Windres = 'bin\windres.exe'
        CRT0 = 'aarch64-pc-cygwin\lib\crt0.o'; CRTBegin = 'lib\crtbegin.o'; CRTEnd = 'lib\crtend.o'
        Libgcc = 'lib\libgcc.a'; Libstdcxx = 'lib\libstdc++.a'; MsysImport = 'aarch64-pc-cygwin\lib\libmsys-2.0.a'
        RuntimeDll = 'bin\msys-2.0.dll'; Specs = 'lib\gcc\aarch64-pc-cygwin\15.0.1\specs'
    }
    $components = @{}
    foreach ($role in $paths.Keys) {
        $path = Join-Path $prefix $paths[$role]
        New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
        # No fixture contains executable machine code or any compiled artifact.
        [IO.File]::WriteAllText($path, "NONEXECUTABLE NEGATIVE CONTROL: $role", $utf8)
    }
    $specs = "*cpp:`n`n*self_spec:`n -D__MSYS__`n*lib:`n-lmsys-2.0`n*link:`n_msys_dll_entry _msys_dll_entry --dll-search-prefix=msys-`n"
    [IO.File]::WriteAllText((Join-Path $prefix $paths.Specs), $specs, $utf8)
    foreach ($role in $paths.Keys) {
        $components[$role] = @{
            Path = $paths[$role]
            SHA256 = (Get-FileHash -LiteralPath (Join-Path $prefix $paths[$role])).Hash.ToLowerInvariant()
        }
    }
    $profileRelative = 'share\toolchain\msys-profile.json'
    $sysrootRelative = 'share\toolchain\identities\runtime-inputs.sha256'
    $dllRelative = 'share\toolchain\identities\runtime-dll.sha256'
    $lockRelative = 'share\toolchain\source-lock.json'
    New-Item -ItemType Directory -Path (Join-Path $prefix 'share\toolchain\identities') -Force | Out-Null
    $profile = @{
        schemaVersion = 1; target = 'aarch64-pc-cygwin'; profileMode = 'default'
        compiler = Join-Path $prefix $paths.GCC; compilerSha256 = $components.GCC.SHA256
        originalSpecsSha256 = '0' * 64; specs = Join-Path $prefix $paths.Specs; specsSha256 = $components.Specs.SHA256
        scope = 'Nonexecutable reader rejection fixture only'
    }
    [IO.File]::WriteAllText((Join-Path $prefix $profileRelative), ($profile | ConvertTo-Json), $utf8)
    [IO.File]::WriteAllText((Join-Path $prefix $sysrootRelative),
        "$($components.CRT0.SHA256)  lib/crt0.o`n$($components.MsysImport.SHA256)  lib/libmsys-2.0.a`n", $utf8)
    [IO.File]::WriteAllText((Join-Path $prefix $dllRelative), "$($components.RuntimeDll.SHA256)  /fixture/msys-2.0.dll`n", $utf8)
    [IO.File]::WriteAllText((Join-Path $prefix $lockRelative), '{"fixture":"not-a-source-qualification"}', $utf8)
    # Even with structurally plausible publisher fields, false acceptance must
    # fail before this fixture's bogus driver could be used.
    $proof = @{
        Passed = $false; Host = 'Windows ARM64 UCRT'; Target = 'aarch64-pc-cygwin'; Profile = 'MSYS'
        CompilerProcess = @{ Image = Join-Path $prefix $paths.GCC; Machine = '0xAA64'; ProcessId = 1 }
        RuntimeInputs = @(); RuntimeDll = @{}; Runs = @(); Outputs = @()
    }
    [IO.File]::WriteAllText($proofPath, ($proof | ConvertTo-Json -Depth 5), $utf8)
    [IO.File]::WriteAllText($toolsPath, '[]', $utf8)
    $files = @(Get-ChildItem -LiteralPath $prefix -Recurse -File | ForEach-Object {
        @{ Path = $_.FullName.Substring($prefix.Length + 1); SHA256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
    })
    $map = @{}
    foreach ($entry in $files) { $map[$entry.Path] = $entry }
    $manifest = @{
        SchemaVersion = 1; Status = 'qualified'; Prefix = $prefix
        Host = @{ Triple = 'aarch64-w64-mingw32'; Machine = '0xAA64'; Runtime = 'UCRT' }
        Target = @{ Triple = 'aarch64-pc-cygwin'; Profile = 'MSYS'; DataModel = 'LP64'; ThreadModel = 'posix' }
        Sysroot = 'aarch64-pc-cygwin'; Files = $files; Components = $components
        EpochSHA256 = & "$PSScriptRoot\..\..\.github\scripts\get-toolchain-epoch.ps1" -Inputs $files
        SourceLock = $map[$lockRelative]; ProfileManifest = $map[$profileRelative]
        RuntimePairing = @{ SourceSysroot = '/fixture/sysroot'; SourceDll = '/fixture/msys-2.0.dll'
            SysrootManifest = $map[$sysrootRelative]; DllManifest = $map[$dllRelative] }
        Acceptance = @{ Path = $proofPath; SHA256 = (Get-FileHash -LiteralPath $proofPath).Hash.ToLowerInvariant()
            ToolIdentitiesPath = $toolsPath; ToolIdentitiesSHA256 = (Get-FileHash -LiteralPath $toolsPath).Hash.ToLowerInvariant() }
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 10), $utf8)
    @{ Prefix = $prefix; Manifest = $manifestPath; Data = $manifest; ProofPath = $proofPath; Proof = $proof }
}
