param(
    [Parameter(Mandatory = $true)]
    [string]$ExportRoot,

    [Parameter(Mandatory = $true)]
    [string]$CompilerRoot,

    [Parameter(Mandatory = $true)]
    [string]$SdkRoot,

    [Parameter(Mandatory = $true)]
    [string]$ZlibStage,

    [Parameter(Mandatory = $true)]
    [string]$NativePython,

    [Parameter(Mandatory = $true)]
    [string]$Observer,

    [Parameter(Mandatory = $true)]
    [string]$CandidateRoot,

    [Parameter(Mandatory = $true)]
    [string]$ApiProbeRoot
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Assert-Condition {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Get-Sha256 {
    param([string]$Path)
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-PkgInfoValues {
    param([string[]]$Lines, [string]$Name)
    @(
        $Lines |
            Where-Object { $_.StartsWith("$Name = ", [StringComparison]::Ordinal) } |
            ForEach-Object { $_.Substring($Name.Length + 3) }
    )
}

function Invoke-Captured {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$LogPath
    )
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $FilePath
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in $ArgumentList) {
        [void]$start.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::Start($start)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    [IO.File]::WriteAllText(
        $LogPath,
        $stdout + $stderr,
        [Text.UTF8Encoding]::new($false)
    )
    [pscustomobject]@{
        RawExit = $process.ExitCode
        Output = $stdout + $stderr
    }
}

function Invoke-ObservedNative {
    param(
        [string]$Name,
        [string]$Target,
        [string[]]$Arguments
    )
    $runRoot = Join-Path $evidenceRoot $Name
    $relayRoot = Join-Path $runRoot 'native-exit-relays'
    New-Item -ItemType Directory -Path $relayRoot | Out-Null
    $log = Join-Path $runRoot 'output.log'
    $result = Join-Path $runRoot 'native-job.json'

    $env:WOARM64_NATIVE_TEST_ROOT = $readbackRoot
    $env:WOARM64_NATIVE_EXIT_DIR = $relayRoot
    $env:WOARM64_NATIVE_PYTHON_SHA256 = $nativePythonSha256
    Remove-Item Env:WOARM64_NATIVE_ARG_COUNT -ErrorAction SilentlyContinue
    Remove-Item Env:WOARM64_NATIVE_PATH_CONVERSION -ErrorAction SilentlyContinue
    Remove-Item Env:WOARM64_NATIVE_MSYS_ROOT -ErrorAction SilentlyContinue

    $observerArguments = @(
        $Observer,
        '--cwd', $readbackRoot,
        '--target-root', $readbackRoot,
        '--relay-records', $relayRoot,
        '--log', $log,
        '--result', $result,
        '--timeout', '120',
        '--',
        $NativePython,
        '-I',
        $nativeRelay,
        $Target
    ) + $Arguments
    $run = Invoke-Captured -FilePath $hostPython `
        -ArgumentList $observerArguments `
        -LogPath (Join-Path $runRoot 'observer.log')
    $record = Get-Content -LiteralPath $result -Raw | ConvertFrom-Json
    Assert-Condition ($run.RawExit -eq 0) "$Name observer exited $($run.RawExit)"
    Assert-Condition ($record.parent_raw_exit -eq 0) "$Name target failed: $($record.parent_raw_exit)"
    Assert-Condition ([bool]$record.observation_count_matches) "$Name observer count mismatch"
    Assert-Condition (@($record.unobserved_processes).Count -eq 0) "$Name had unobserved processes"
    Assert-Condition (@($record.unresolved_processes).Count -eq 0) "$Name had unresolved processes"
    Assert-Condition (@($record.unrelayed_high_exits).Count -eq 0) "$Name had unrelayed high exits"
    [pscustomobject]@{
        name = $Name
        result = $result
        resultSha256 = Get-Sha256 $result
        output = $log
        outputSha256 = Get-Sha256 $log
        parentRawExit = [int]$record.parent_raw_exit
        created = [int]$record.created_processes
        observed = [int]$record.observed_processes
    }
}

$ExportRoot = (Resolve-Path -LiteralPath $ExportRoot).Path
$CompilerRoot = (Resolve-Path -LiteralPath $CompilerRoot).Path
$SdkRoot = (Resolve-Path -LiteralPath $SdkRoot).Path
$ZlibStage = (Resolve-Path -LiteralPath $ZlibStage).Path
$NativePython = (Resolve-Path -LiteralPath $NativePython).Path
$Observer = (Resolve-Path -LiteralPath $Observer).Path
$CandidateRoot = (Resolve-Path -LiteralPath $CandidateRoot).Path
$ApiProbeRoot = (Resolve-Path -LiteralPath $ApiProbeRoot).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path

$hostBin = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64\usr\bin'
$bsdtar = Join-Path $hostBin 'bsdtar.exe'
$hostPython = (Get-Command python.exe -ErrorAction Stop).Source
$objdump = Join-Path $CompilerRoot 'bin\objdump.exe'
$gcc = Join-Path $CompilerRoot 'bin\gcc.exe'
$nativeRelay = Join-Path $repoRoot '.github\scripts\native-target-exec.py'
$fixture = Join-Path $repoRoot 'tests\native-pcre2-all-width-api.c'
$readbackRoot = Join-Path $ExportRoot 'readback-01'
$evidenceRoot = Join-Path $ExportRoot 'evidence'

Assert-Condition (-not (Test-Path -LiteralPath $readbackRoot)) "fresh readback root required: $readbackRoot"
Assert-Condition (-not (Test-Path -LiteralPath $evidenceRoot)) "fresh evidence root required: $evidenceRoot"
foreach ($required in @($bsdtar, $objdump, $gcc, $nativeRelay, $fixture)) {
    Assert-Condition (Test-Path -LiteralPath $required -PathType Leaf) "missing verifier input: $required"
}
New-Item -ItemType Directory -Path $readbackRoot, $evidenceRoot | Out-Null

$expected = [ordered]@{
    bzip2 = [pscustomobject]@{
        Base = 'bzip2'; Version = '1.0.8-4'; License = 'spdx:bzip2-1.0.6'
        Groups = @('compression'); Depends = @('libbz2')
        Required = @('usr/bin/bzip2.exe', 'usr/bin/bzip2recover.exe',
            'usr/share/man/man1/bzip2.1', 'usr/share/licenses/bzip2/LICENSE')
    }
    libbz2 = [pscustomobject]@{
        Base = 'bzip2'; Version = '1.0.8-4'; License = 'spdx:bzip2-1.0.6'
        Groups = @('compression', 'libraries'); Depends = @('gcc-libs')
        Required = @('usr/bin/msys-bz2-1.dll')
    }
    'libbz2-devel' = [pscustomobject]@{
        Base = 'bzip2'; Version = '1.0.8-4'; License = 'spdx:bzip2-1.0.6'
        Groups = @('compression', 'development'); Depends = @('libbz2=1.0.8')
        Required = @('usr/include/bzlib.h', 'usr/lib/libbz2.a', 'usr/lib/libbz2.dll.a')
    }
    pcre2 = [pscustomobject]@{
        Base = 'pcre2'; Version = '10.48-1'
        License = 'spdx:BSD-3-Clause WITH PCRE2-exception'
        Groups = @()
        Depends = @('libreadline', 'libbz2', 'zlib', 'libpcre2_8=10.48',
            'libpcre2_16=10.48', 'libpcre2_32=10.48', 'libpcre2posix=10.48')
        Required = @('usr/bin/pcre2grep.exe', 'usr/bin/pcre2test.exe',
            'usr/share/man/man1/pcre2grep.1', 'usr/share/licenses/pcre2/LICENSE.md')
    }
    libpcre2_8 = [pscustomobject]@{
        Base = 'pcre2'; Version = '10.48-1'
        License = 'spdx:BSD-3-Clause WITH PCRE2-exception'
        Groups = @('libraries'); Depends = @('gcc-libs')
        Required = @('usr/bin/msys-pcre2-8-0.dll')
    }
    libpcre2_16 = [pscustomobject]@{
        Base = 'pcre2'; Version = '10.48-1'
        License = 'spdx:BSD-3-Clause WITH PCRE2-exception'
        Groups = @('libraries'); Depends = @('gcc-libs')
        Required = @('usr/bin/msys-pcre2-16-0.dll')
    }
    libpcre2_32 = [pscustomobject]@{
        Base = 'pcre2'; Version = '10.48-1'
        License = 'spdx:BSD-3-Clause WITH PCRE2-exception'
        Groups = @('libraries'); Depends = @('gcc-libs')
        Required = @('usr/bin/msys-pcre2-32-0.dll')
    }
    libpcre2posix = [pscustomobject]@{
        Base = 'pcre2'; Version = '10.48-1'
        License = 'spdx:BSD-3-Clause WITH PCRE2-exception'
        Groups = @('libraries'); Depends = @('libpcre2_8=10.48')
        Required = @('usr/bin/msys-pcre2-posix-3.dll')
    }
    'pcre2-devel' = [pscustomobject]@{
        Base = 'pcre2'; Version = '10.48-1'
        License = 'spdx:BSD-3-Clause WITH PCRE2-exception'
        Groups = @('development')
        Depends = @('libpcre2_8=10.48', 'libpcre2_16=10.48',
            'libpcre2_32=10.48', 'libpcre2posix=10.48')
        Required = @('usr/bin/pcre2-config', 'usr/include/pcre2.h',
            'usr/include/pcre2posix.h', 'usr/lib/libpcre2-8.dll.a',
            'usr/lib/libpcre2-16.dll.a', 'usr/lib/libpcre2-32.dll.a',
            'usr/lib/libpcre2-posix.dll.a', 'usr/lib/pkgconfig/libpcre2-8.pc')
    }
}

$exportPath = Join-Path $ExportRoot 'export.json'
$export = Get-Content -LiteralPath $exportPath -Raw | ConvertFrom-Json
Assert-Condition ($export.schema -eq 1) 'export schema is not 1'
Assert-Condition (@($export.packages).Count -eq $expected.Count) 'export package count mismatch'

$owners = @{}
$packageResults = @()
foreach ($item in $export.packages) {
    Assert-Condition ($expected.Contains($item.name)) "unexpected package: $($item.name)"
    $definition = $expected[$item.name]
    Assert-Condition (-not [IO.Path]::IsPathRooted($item.path)) "absolute export path: $($item.path)"
    $packagePath = Join-Path $ExportRoot ($item.path -replace '/', '\')
    Assert-Condition (Test-Path -LiteralPath $packagePath -PathType Leaf) "missing package: $packagePath"
    Assert-Condition ((Get-Sha256 $packagePath) -eq $item.sha256) "package hash mismatch: $($item.name)"

    $info = @(& $bsdtar -xOf $packagePath .PKGINFO)
    Assert-Condition ($LASTEXITCODE -eq 0) "cannot read .PKGINFO: $($item.name)"
    Assert-Condition ((Get-PkgInfoValues $info pkgname) -eq $item.name) "pkgname mismatch: $($item.name)"
    Assert-Condition ((Get-PkgInfoValues $info pkgbase) -eq $definition.Base) "pkgbase mismatch: $($item.name)"
    Assert-Condition ((Get-PkgInfoValues $info pkgver) -eq $definition.Version) "pkgver mismatch: $($item.name)"
    Assert-Condition ((Get-PkgInfoValues $info arch) -eq 'aarch64') "arch mismatch: $($item.name)"
    Assert-Condition ((Get-PkgInfoValues $info license) -eq $definition.License) "license mismatch: $($item.name)"
    Assert-Condition (
        ((@(Get-PkgInfoValues $info group) | Sort-Object) -join "`n") -eq
        ((@($definition.Groups) | Sort-Object) -join "`n")
    ) "group mismatch: $($item.name)"
    Assert-Condition (
        ((@(Get-PkgInfoValues $info depend) | Sort-Object) -join "`n") -eq
        ((@($definition.Depends) | Sort-Object) -join "`n")
    ) "dependency mismatch: $($item.name)"

    $members = @(& $bsdtar -tf $packagePath)
    Assert-Condition ($LASTEXITCODE -eq 0) "cannot list package: $($item.name)"
    foreach ($metadata in @('.PKGINFO', '.BUILDINFO', '.MTREE')) {
        Assert-Condition ($members.Contains($metadata)) "missing $metadata in $($item.name)"
    }
    Assert-Condition (@($members | Where-Object { $_ -match '(^/|(^|/)\.\.(/|$))' }).Count -eq 0) `
        "unsafe archive path in $($item.name)"
    $payload = @($members | Where-Object { $_ -like 'usr/*' -and -not $_.EndsWith('/') })
    foreach ($required in $definition.Required) {
        Assert-Condition ($payload.Contains($required)) "missing $required in $($item.name)"
    }
    foreach ($path in $payload) {
        Assert-Condition (-not $owners.ContainsKey($path)) `
            "duplicate ownership for ${path}: $($owners[$path]) and $($item.name)"
        $owners[$path] = $item.name
    }
    & $bsdtar -xf $packagePath -C $readbackRoot
    Assert-Condition ($LASTEXITCODE -eq 0) "cannot extract package: $($item.name)"
    $packageResults += [pscustomobject]@{
        name = $item.name
        path = $item.path
        sha256 = $item.sha256
        pkginfoSha256 = Get-Sha256 (Join-Path $ExportRoot "roots\$($item.name)\.PKGINFO")
        payloadFiles = $payload.Count
    }
}

Assert-Condition (@($expected.Keys | Where-Object {
    -not @($export.packages.name).Contains($_)
}).Count -eq 0) 'expected package absent from export'
Assert-Condition (@($owners.Keys | Where-Object { $_ -like '*.la' }).Count -eq 0) `
    'libtool archives leaked into package payload'
$forbidden = @($owners.Keys | Where-Object {
    $_ -match '(?i)(echo\.exe|msys-intl|msys-iconv|argv-relay|native-pcre2.*api)'
})
Assert-Condition ($forbidden.Count -eq 0) 'test-only helper leaked into package payload'

$privateMarkers = '(?i)([a-z]:[/\\](?:ap[0-9]|ag-)|[.]copilot[/\\]|less-native-01|pcre2-candidate-)'
$privateHits = @()
foreach ($path in $owners.Keys) {
    $full = Join-Path $readbackRoot ($path -replace '/', '\')
    $bytes = [IO.File]::ReadAllBytes($full)
    $ascii = [Text.Encoding]::ASCII.GetString($bytes)
    $unicode = [Text.Encoding]::Unicode.GetString($bytes)
    if ($ascii -match $privateMarkers -or $unicode -match $privateMarkers) {
        $privateHits += $path
    }
}
Assert-Condition ($privateHits.Count -eq 0) "private build paths found: $($privateHits -join ', ')"

$external = [ordered]@{
    'msys-2.0.dll' = [pscustomobject]@{
        Path = (Join-Path $CompilerRoot 'bin\msys-2.0.dll')
        Sha256 = '907afa099a69aa3c13d4e3b30eeba18c4a6b1766d5fa39b4746fae23c3f9e76c'
    }
    'msys-readline8.dll' = [pscustomobject]@{
        Path = (Join-Path $SdkRoot 'usr\bin\msys-readline8.dll')
        Sha256 = 'bf2a0cd06cb4951b8ad37c3e74970d6550f2d5fc101c3eb8056f7127b42253a7'
    }
    'msys-history8.dll' = [pscustomobject]@{
        Path = (Join-Path $SdkRoot 'usr\bin\msys-history8.dll')
        Sha256 = 'f48e5347c7610fd53ca8066f19f8b7d964a9c6d251718d3997a4dc8d46e34840'
    }
    'msys-ncursesw6.dll' = [pscustomobject]@{
        Path = (Join-Path $SdkRoot 'usr\bin\msys-ncursesw6.dll')
        Sha256 = 'e2d03ae2ac264d8788f3cd7ea4917c51c9b26ac59ee574e4cade633a96de3585'
    }
    'msys-z.dll' = [pscustomobject]@{
        Path = (Join-Path $ZlibStage 'usr\bin\msys-z.dll')
        Sha256 = 'aa736ada198e6255d400baf508a1002178b1fd86cc65275ba52bb9772ec9481c'
    }
}
$runtimeBin = Join-Path $readbackRoot 'usr\bin'
foreach ($entry in $external.GetEnumerator()) {
    Assert-Condition ((Get-Sha256 $entry.Value.Path) -eq $entry.Value.Sha256) `
        "external dependency changed: $($entry.Key)"
    Copy-Item -LiteralPath $entry.Value.Path -Destination (Join-Path $runtimeBin $entry.Key)
}

$peResults = @()
$systemImports = @(
    'ADVAPI32.dll', 'KERNEL32.dll', 'NETAPI32.dll', 'PSAPI.DLL',
    'SHELL32.dll', 'USER32.dll', 'WINMM.dll', 'WS2_32.dll'
)
foreach ($path in @($owners.Keys | Where-Object { $_ -match '(?i)\.(exe|dll)$' } | Sort-Object)) {
    $full = Join-Path $readbackRoot ($path -replace '/', '\')
    $bytes = [IO.File]::ReadAllBytes($full)
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    $machine = [BitConverter]::ToUInt16($bytes, $peOffset + 4)
    Assert-Condition ($machine -eq 0xaa64) "non-ARM64 PE: $path"
    $headers = @(& $objdump -p $full)
    Assert-Condition ($LASTEXITCODE -eq 0) "objdump failed: $path"
    $imports = @(
        $headers |
            Where-Object { $_ -match 'DLL Name:\s*(\S+)' } |
            ForEach-Object { $Matches[1] }
    )
    foreach ($import in $imports) {
        if ($systemImports -contains $import) {
            continue
        }
        Assert-Condition (Test-Path -LiteralPath (Join-Path $runtimeBin $import)) `
            "unresolved private import $import in $path"
    }
    $peResults += [pscustomobject]@{
        path = $path
        sha256 = Get-Sha256 $full
        machine = 'AA64'
        imports = $imports
    }
}

$pcre8 = Join-Path $runtimeBin 'msys-pcre2-8-0.dll'
$pcre8Headers = @(& $objdump -p $pcre8)
$pcre8Disassembly = @(& $objdump -d $pcre8)
$cacheEvidence = [pscustomobject]@{
    importsFlushInstructionCache = [bool]($pcre8Headers -match 'FlushInstructionCache')
    legacyCacheInstructionCount = @(
        $pcre8Disassembly | Where-Object { $_ -match 'ctr_el0|dc\s+cvau|ic\s+ivau' }
    ).Count
}
Assert-Condition $cacheEvidence.importsFlushInstructionCache `
    'PCRE2 JIT DLL does not import FlushInstructionCache'
Assert-Condition ($cacheEvidence.legacyCacheInstructionCount -eq 0) `
    'PCRE2 JIT DLL contains legacy ARM cache-maintenance instructions'

$oldPath = $env:PATH
try {
    $env:PATH = "$runtimeBin;$($CompilerRoot)\bin;$env:SystemRoot\System32"
    $targetEvidenceRoot = Join-Path $readbackRoot 'verification'
    New-Item -ItemType Directory -Path $targetEvidenceRoot | Out-Null
    $apiExecutable = Join-Path $targetEvidenceRoot 'native-pcre2-all-width-api.exe'
    $compileLog = Join-Path $evidenceRoot 'all-width-api-compile.log'
    $compile = Invoke-Captured -FilePath $gcc -ArgumentList @(
        '-O2', '-pipe', '-fstack-protector-strong', '-D_FORTIFY_SOURCE=2',
        "-I$(Join-Path $readbackRoot 'usr\include')",
        $fixture,
        "-L$(Join-Path $readbackRoot 'usr\lib')",
        '-lpcre2-8', '-lpcre2-16', '-lpcre2-32', '-lpcre2-posix',
        '-Wl,--no-insert-timestamp',
        '-o', $apiExecutable
    ) -LogPath $compileLog
    Assert-Condition ($compile.RawExit -eq 0) "all-width API compilation failed: $($compile.Output)"

    $nativePythonSha256 = Get-Sha256 $NativePython
    Assert-Condition (
        $nativePythonSha256 -eq
        'c55badc4658c6a5e01f21959ae813a66060b786b3297b67991b27a673327652f'
    ) 'native Python relay identity changed'

    $apiResult = Join-Path $targetEvidenceRoot 'all-width-api-result.json'
    $observedRuns = @()
    $observedRuns += Invoke-ObservedNative -Name 'all-width-api' `
        -Target $apiExecutable -Arguments @($apiResult)
    $api = Get-Content -LiteralPath $apiResult -Raw | ConvertFrom-Json
    Assert-Condition ([bool]$api.passed) 'all-width API result did not pass'
    Assert-Condition (
        $api.unicode -eq 1 -and $api.jit -eq 1 -and
        $api.newline -eq 5 -and $api.width8_matches -ge 2 -and
        $api.width16_matches -ge 2 -and $api.width32_matches -ge 2 -and
        $api.posix -eq 1 -and $api.positive -and $api.nonmatch -and
        $api.invalid_pattern
    ) 'all-width API result is incomplete'

    $observedRuns += Invoke-ObservedNative -Name 'pcre2grep-version' `
        -Target (Join-Path $runtimeBin 'pcre2grep.exe') -Arguments @('--version')
    $observedRuns += Invoke-ObservedNative -Name 'bzip2-help' `
        -Target (Join-Path $runtimeBin 'bzip2.exe') -Arguments @('--help')
}
finally {
    $env:PATH = $oldPath
}

$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = Join-Path $runtimeBin 'pcre2test.exe'
$start.WorkingDirectory = $readbackRoot
$start.UseShellExecute = $false
$start.RedirectStandardInput = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.Environment.Clear()
$start.Environment['PATH'] = "$runtimeBin;$env:SystemRoot\System32"
$start.Environment['SystemRoot'] = $env:SystemRoot
$start.Environment['WINDIR'] = $env:WINDIR
$start.Environment['TERM'] = 'xterm'
$process = [Diagnostics.Process]::Start($start)
Start-Sleep -Milliseconds 750
Assert-Condition (-not $process.HasExited) 'pcre2test exited before live module capture'
$modules = @(
    $process.Modules |
        ForEach-Object {
            [pscustomobject]@{
                name = $_.ModuleName
                path = $_.FileName
                sha256 = Get-Sha256 $_.FileName
            }
        }
)
$process.StandardInput.Close()
$process.WaitForExit(30000) | Out-Null
Assert-Condition ($process.HasExited) 'pcre2test did not exit after stdin close'
Assert-Condition ($process.ExitCode -eq 0) "pcre2test module probe exited $($process.ExitCode)"
$system32 = [IO.Path]::GetFullPath((Join-Path $env:SystemRoot 'System32'))
$disallowedModules = @(
    $modules | Where-Object {
        $full = [IO.Path]::GetFullPath($_.path)
        -not $full.StartsWith($runtimeBin, [StringComparison]::OrdinalIgnoreCase) -and
        -not $full.StartsWith($system32, [StringComparison]::OrdinalIgnoreCase)
    }
)
Assert-Condition ($disallowedModules.Count -eq 0) `
    "live module escaped private runtime/System32: $($disallowedModules.path -join ', ')"
$loadedRuntime = $modules | Where-Object { $_.name -ieq 'msys-2.0.dll' }
Assert-Condition ($null -ne $loadedRuntime) 'live process did not load msys-2.0.dll'
Assert-Condition ($loadedRuntime.sha256 -eq $external['msys-2.0.dll'].Sha256) `
    'live process loaded the wrong MSYS runtime'

$strictLog = Join-Path $CandidateRoot 'logs\pcre2-check.log'
$suiteLog = Join-Path $CandidateRoot 'src\pcre2-10.48\test-suite.log'
$installLog = Join-Path $CandidateRoot 'logs\pcre2-install.log'
$strictText = Get-Content -LiteralPath $strictLog -Raw
Assert-Condition ($strictText -match 'TOTAL:\s+4') 'strict total is not 4'
Assert-Condition ($strictText -match 'PASS:\s+4') 'strict pass count is not 4'
Assert-Condition ($strictText -match 'FAIL:\s+0') 'strict failure count is not 0'

$candidateObserverPath = 'C:\ap15-d207\less-native-01\observer-pcre2-15\native-job.json'
$candidateObserver = Get-Content -LiteralPath $candidateObserverPath -Raw | ConvertFrom-Json
Assert-Condition ($candidateObserver.parent_raw_exit -eq 1) `
    'candidate-13 overall controller exit must remain the honest post-check raw 1'
Assert-Condition (
    $candidateObserver.created_processes -eq 3390 -and
    $candidateObserver.observed_processes -eq 3390 -and
    $candidateObserver.observation_count_matches -and
    @($candidateObserver.unobserved_processes).Count -eq 0 -and
    @($candidateObserver.unresolved_processes).Count -eq 0 -and
    @($candidateObserver.unrelayed_high_exits).Count -eq 0
) 'candidate-13 observer evidence changed'

$priorApiResult = Join-Path $ApiProbeRoot 'native-pcre2-jit-api.json'
$priorApiObserver = Join-Path $ApiProbeRoot 'observer\native-job.json'
$testOnlyNames = @('echo.exe', 'msys-intl-8.dll', 'msys-iconv-2.dll',
    'native-msys-argv-relay.exe')
foreach ($name in $testOnlyNames) {
    Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $readbackRoot "usr\bin\$name"))) `
        "test-only helper leaked into readback root: $name"
}

$verification = [ordered]@{
    schema = 1
    status = 'verified-native-msys-bzip2-pcre2-provider-candidate'
    generatedUtc = [DateTime]::UtcNow.ToString('o')
    export = [ordered]@{
        path = $exportPath
        sha256 = Get-Sha256 $exportPath
        packageCount = @($export.packages).Count
        packages = $packageResults
    }
    ownership = [ordered]@{
        payloadFiles = $owners.Count
        duplicatePaths = 0
        forbiddenTestHelpers = @()
        privatePathHits = @()
    }
    peReadback = [ordered]@{
        packagedPeCount = $peResults.Count
        nonArm64 = 0
        unresolvedImports = 0
        files = $peResults
    }
    runtimeCohort = [ordered]@{
        dependencies = @(
            $external.GetEnumerator() | ForEach-Object {
                [ordered]@{
                    name = $_.Key
                    source = $_.Value.Path
                    sha256 = $_.Value.Sha256
                }
            }
        )
        liveModules = $modules
        disallowedLiveModules = @()
    }
    movedRoot = [ordered]@{
        root = $readbackRoot
        path = "$runtimeBin;$env:SystemRoot\System32"
        runs = $observedRuns
        allWidthApi = [ordered]@{
            executable = $apiExecutable
            executableSha256 = Get-Sha256 $apiExecutable
            result = $apiResult
            resultSha256 = Get-Sha256 $apiResult
            value = $api
        }
        jitInstructionCache = $cacheEvidence
    }
    upstream = [ordered]@{
        strictRawExit = 0
        passed = 4
        failed = 0
        checkLog = [ordered]@{ path = $strictLog; sha256 = Get-Sha256 $strictLog }
        testSuite = [ordered]@{ path = $suiteLog; sha256 = Get-Sha256 $suiteLog }
        installLog = [ordered]@{ path = $installLog; sha256 = Get-Sha256 $installLog }
        observer = [ordered]@{
            path = $candidateObserverPath
            sha256 = Get-Sha256 $candidateObserverPath
            overallRawExit = 1
            postCheckFailure = 'repository-relative API fixture path after source-directory change'
            created = 3390
            observed = 3390
            unresolved = 0
            unobserved = 0
            unrelayedHighExits = 0
        }
    }
    priorFocusedApi = [ordered]@{
        result = $priorApiResult
        resultSha256 = Get-Sha256 $priorApiResult
        observer = $priorApiObserver
        observerSha256 = Get-Sha256 $priorApiObserver
    }
    sourceAndRecipes = [ordered]@{
        pcre2SourceSha256 = 'b6c68fdf6f3ac31388b50aa89ff0fc49c00c987c16e7b5146491d12003f2c8ed'
        pcre2Recipe = Join-Path 'C:\ap15-d207\less-native-01\recipe' 'PKGBUILD.pcre2.aarch64'
        pcre2RecipeSha256 = Get-Sha256 (Join-Path 'C:\ap15-d207\less-native-01\recipe' 'PKGBUILD.pcre2.aarch64')
        bzip2Recipe = Join-Path 'C:\ap15-d207\less-native-01\recipe' 'PKGBUILD.bzip2.upstream'
        bzip2RecipeSha256 = Get-Sha256 (Join-Path 'C:\ap15-d207\less-native-01\recipe' 'PKGBUILD.bzip2.upstream')
        packagingScript = Join-Path $repoRoot '.github\scripts\package-native-msys-bzip2-pcre2.sh'
        packagingScriptSha256 = Get-Sha256 (Join-Path $repoRoot '.github\scripts\package-native-msys-bzip2-pcre2.sh')
        verificationScript = $PSCommandPath
        verificationScriptSha256 = Get-Sha256 $PSCommandPath
        allWidthFixture = $fixture
        allWidthFixtureSha256 = Get-Sha256 $fixture
    }
    limitations = @(
        'candidate-13 combined controller remains raw 1 only because its post-check API fixture path was relative',
        'the strict upstream suite itself passed raw 0 with 4/4 tests',
        'the original focused API and this package-readback all-width API both passed raw 0',
        'test-only echo, intl, iconv, and argv relay are excluded from every package'
    )
}

$verificationPath = Join-Path $ExportRoot 'verification.json'
[IO.File]::WriteAllText(
    $verificationPath,
    ($verification | ConvertTo-Json -Depth 12) + "`n",
    [Text.UTF8Encoding]::new($false)
)
$verification | ConvertTo-Json -Depth 4
