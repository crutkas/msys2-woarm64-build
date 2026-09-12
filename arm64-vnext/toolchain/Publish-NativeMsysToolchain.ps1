[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $AcceptanceDirectory,
    [Parameter(Mandatory)][string] $OutputFile
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($Prefix).TrimEnd('\') + '\'
$output = [IO.Path]::GetFullPath($OutputFile)
if ($output.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $output) -or (Test-Path -LiteralPath "$output.pending")) {
    throw 'Publish to a new manifest outside the immutable prefix.'
}
$proofPath = Join-Path $AcceptanceDirectory 'result.json'
$toolsPath = Join-Path $AcceptanceDirectory 'tool-identities.json'
$proof = Get-Content -Raw -LiteralPath $proofPath | ConvertFrom-Json
if ($proof.Passed -ne $true -or $proof.Host -cne 'Windows ARM64 UCRT' -or
    $proof.Target -cne 'aarch64-pc-cygwin' -or $proof.Profile -cne 'MSYS' -or
    $proof.CompilerProcess.Machine -cne '0xAA64') {
    throw 'An independent successful native MSYS acceptance proof is required.'
}
$requiredRuns = @('msys-c-compile','msys-c-assemble','msys-module','msys-c-link',
                  'msys-c-execute','msys-cxx-build','msys-cxx-execute')
if (@($proof.Runs).Count -ne $requiredRuns.Count) { throw 'Incomplete MSYS acceptance runs.' }
foreach ($name in $requiredRuns) {
    $run = @($proof.Runs | Where-Object { $_.Name -ceq $name })
    if ($run.Count -ne 1 -or $run[0].ExitCode -ne 0) { throw "Unsuccessful MSYS acceptance: $name" }
}
function Hash([string] $Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Relative([string] $Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Toolchain input escaped its prefix: $full"
    }
    [IO.Path]::GetRelativePath($root, $full)
}
$files = [Collections.Generic.SortedDictionary[string,object]]::new([StringComparer]::Ordinal)
$items = @(Get-ChildItem -LiteralPath $root -Recurse -Force)
if (@($items | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Dereference links before publishing the Windows prefix.'
}
foreach ($file in $items | Where-Object { -not $_.PSIsContainer }) {
    $relative = Relative $file.FullName
    $files.Add($relative, [pscustomobject]@{ Path = $relative; SHA256 = Hash $file.FullName })
}
if ($files.Count -eq 0) { throw 'Empty toolchain prefix.' }
function Component([string] $Path) {
    $relative = Relative $Path
    if (-not $files.ContainsKey($relative)) { throw "Uninventoried input: $relative" }
    $files[$relative]
}
$cc = Join-Path $root 'bin\gcc.exe'
$cxx = Join-Path $root 'bin\g++.exe'
function CompilerPath([string] $Argument) {
    $path = (& $cc $Argument | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathFullyQualified($path)) {
        throw "Compiler did not resolve $Argument inside the prefix: $path"
    }
    $path
}
$oldPath = $env:PATH
try {
    $env:PATH = "$(Join-Path $root 'bin');$oldPath"
    if ((& $cc -dumpmachine | Out-String).Trim() -cne 'aarch64-pc-cygwin' -or $LASTEXITCODE) {
        throw 'Wrong compiler target.'
    }
    $verbose = (& $cc -v 2>&1 | Out-String)
    if ($LASTEXITCODE -or $verbose -notmatch 'Thread model: posix') {
        throw 'The native MSYS compiler must use POSIX target threads.'
    }
    $components = [ordered]@{
        GCC = Component $cc
        GXX = Component $cxx
        CC1 = Component (CompilerPath '-print-prog-name=cc1')
        CC1Plus = Component (CompilerPath '-print-prog-name=cc1plus')
        Assembler = Component (CompilerPath '-print-prog-name=as')
        Linker = Component (CompilerPath '-print-prog-name=ld')
        Ar = Component (Join-Path $root 'bin\ar.exe')
        Ranlib = Component (Join-Path $root 'bin\ranlib.exe')
        Windres = Component (Join-Path $root 'bin\windres.exe')
        CRT0 = Component (CompilerPath '-print-file-name=crt0.o')
        CRTBegin = Component (CompilerPath '-print-file-name=crtbegin.o')
        CRTEnd = Component (CompilerPath '-print-file-name=crtend.o')
        Libgcc = Component (CompilerPath '-print-libgcc-file-name')
        Libstdcxx = Component (CompilerPath '-print-file-name=libstdc++.a')
        MsysImport = Component (CompilerPath '-print-file-name=libmsys-2.0.a')
        RuntimeDll = Component (Join-Path $root 'bin\msys-2.0.dll')
        Specs = Component (CompilerPath '-print-file-name=specs')
    }
    $sysroot = Relative (CompilerPath '-print-sysroot')
    $profileManifest = Component (Join-Path $root 'share\toolchain\msys-profile.json')
    $profile = Get-Content -Raw (Join-Path $root $profileManifest.Path) | ConvertFrom-Json
    if ($profile.schemaVersion -ne 1 -or $profile.profileMode -cne 'default' -or
        $profile.target -cne 'aarch64-pc-cygwin' -or
        $profile.compilerSha256 -cne $components.GCC.SHA256 -or
        $profile.specsSha256 -cne $components.Specs.SHA256 -or
        (Relative $profile.compiler) -cne $components.GCC.Path -or
        (Relative $profile.specs) -cne $components.Specs.Path) {
        throw 'The automatic MSYS profile is not bound to this compiler and specs.'
    }
    $sysrootManifest = Component (Join-Path $root 'share\toolchain\identities\runtime-inputs.sha256')
    $dllManifest = Component (Join-Path $root 'share\toolchain\identities\runtime-dll.sha256')
    $sourceSysroot = (Get-Content -Raw (Join-Path $root 'share\toolchain\identities\runtime-sysroot.txt')).Trim()
    $sourceDll = (Get-Content -Raw (Join-Path $root 'share\toolchain\identities\runtime-dll-path.txt')).Trim()
    $rows = Get-Content (Join-Path $root $sysrootManifest.Path)
    foreach ($pair in @(@('lib/crt0.o','CRT0'), @('lib/libmsys-2.0.a','MsysImport'))) {
        $matches = @($rows | Where-Object { $_ -cmatch ('^[0-9a-f]{64}  ' + [regex]::Escape($pair[0]) + '$') })
        if ($matches.Count -ne 1 -or $matches[0].Substring(0,64) -cne $components[$pair[1]].SHA256) {
            throw "Runtime source pairing differs: $($pair[0])"
        }
    }
    $dllRows = @(Get-Content (Join-Path $root $dllManifest.Path))
    if ($dllRows.Count -ne 1 -or
        $dllRows[0] -cne "$($components.RuntimeDll.SHA256)  $sourceDll") {
        throw 'Runtime DLL does not match its retained source receipt.'
    }
    foreach ($input in @($proof.RuntimeInputs) + @(Get-Content -Raw $toolsPath | ConvertFrom-Json)) {
        if ((Component $input.Path).SHA256 -cne $input.SHA256) {
            throw "Acceptance input changed: $($input.Path)"
        }
    }
    if ($proof.RuntimeDll.SHA256 -cne $components.RuntimeDll.SHA256) {
        throw 'Acceptance used a different runtime DLL.'
    }
    if (@($proof.Outputs).Count -ne 3) { throw 'Incomplete MSYS acceptance images.' }
    foreach ($image in $proof.Outputs) {
        $dlls = @($image.Imports | ForEach-Object Dll)
        if (-not $image.NativeArm64 -or -not $image.DynamicBase -or
            'msys-2.0.dll' -notin $dlls -or 'cygwin1.dll' -in $dlls -or
            'msvcrt.dll' -in $dlls -or $dlls -match '^api-ms-win-crt-' -or
            (Hash $image.Path) -cne $image.SHA256) {
            throw "Acceptance image is not the verified MSYS target: $($image.Path)"
        }
    }
    $canonical = [Text.StringBuilder]::new()
    foreach ($entry in $files.Values) {
        if ((Hash (Join-Path $root $entry.Path)) -cne $entry.SHA256) {
            throw "Prefix changed while publishing: $($entry.Path)"
        }
        [void]$canonical.Append($entry.Path).Append("`t").Append($entry.SHA256).Append("`n")
    }
    $epochHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
        [Text.Encoding]::UTF8.GetBytes($canonical.ToString()))).ToLowerInvariant()
    $manifest = [ordered]@{
        SchemaVersion = 1; Status = 'qualified'; Prefix = $root.TrimEnd('\')
        Host = @{ Triple = 'aarch64-w64-mingw32'; Machine = '0xAA64'; Runtime = 'UCRT' }
        Target = @{ Triple = 'aarch64-pc-cygwin'; Profile = 'MSYS'; DataModel = 'LP64'; ThreadModel = 'posix' }
        Sysroot = $sysroot; Files = @($files.Values); EpochSHA256 = $epochHash
        Components = $components; ProfileManifest = $profileManifest
        RuntimePairing = @{
            SourceSysroot = $sourceSysroot; SourceDll = $sourceDll
            SysrootManifest = $sysrootManifest; DllManifest = $dllManifest
        }
        SourceLock = Component (Join-Path $root 'share\toolchain\source-lock.json')
        Acceptance = @{
            Path = [IO.Path]::GetFullPath($proofPath); SHA256 = Hash $proofPath
            ToolIdentitiesPath = [IO.Path]::GetFullPath($toolsPath); ToolIdentitiesSHA256 = Hash $toolsPath
        }
    }
    $fpDirectory = Join-Path $root 'share\toolchain\assembler-fp'
    if (Test-Path -LiteralPath $fpDirectory) {
        $rawPath = Join-Path $fpDirectory 'raw-encoding.json'
        $nativePath = Join-Path $fpDirectory 'native-boundaries.json'
        $raw = Get-Content -Raw -LiteralPath $rawPath | ConvertFrom-Json
        $nativeProof = Get-Content -Raw -LiteralPath $nativePath | ConvertFrom-Json
        if ($raw.passed -ne $true -or $raw.legacy -ne $false -or
            $raw.assembler_sha256 -cne $components.Assembler.SHA256 -or
            $nativeProof.passed -ne $true -or
            $nativeProof.inputs.assembler.sha256 -cne $components.Assembler.SHA256 -or
            $nativeProof.inputs.runtime.sha256 -cne $components.RuntimeDll.SHA256) {
            throw 'Assembler delta lacks matching raw/native FP unwind qualification.'
        }
        foreach ($name in @('native-execute','cross-execute')) {
            $run = @($nativeProof.runs | Where-Object name -CEQ $name)
            if ($run.Count -ne 1 -or $run[0].exit -ne 0) {
                throw "Missing native FP boundary execution: $name"
            }
        }
        $manifest.AssemblerQualification = [ordered]@{
            RawEncoding = Component $rawPath
            NativeBoundaries = Component $nativePath
            SourceLock = Component (Join-Path $fpDirectory 'source-lock.json')
            Patch = Component (Join-Path $fpDirectory 'binutils-arm64-fp-unwind-enum-order.patch')
            Scope = 'FP unwind encoding/native boundaries for newly assembled objects; copied target-library and runtime build histories are separately bound'
            ExistingLibrariesRebuilt = $false
        }
    }
    $cohortPath = Join-Path $root 'share\toolchain\identities\runtime-cohort-receipt.json'
    if (Test-Path -LiteralPath $cohortPath) {
        $cohort = Get-Content -Raw -LiteralPath $cohortPath | ConvertFrom-Json
        if ($cohort.status -cin @('coherent-runtime-jump-buffer-abi-and-bounded-upstream-consumer-qualified',
                                  'coherent-runtime-ucontext-and-bounded-upstream-consumer-qualified')) {
            $jumpPath = Join-Path $root 'share\toolchain\sigjmp\consumer-result.json'
            $jump = Get-Content -Raw -LiteralPath $jumpPath | ConvertFrom-Json
            $header = Component (Join-Path $root "$sysroot\include\machine\setjmp.h")
            if ($jump.passed -ne $true -or $jump.inputs.runtime.sha256 -cne $components.RuntimeDll.SHA256 -or
                $jump.inputs.'import-library'.sha256 -cne $components.MsysImport.SHA256 -or
                $jump.inputs.'jmp-header'.sha256 -cne $header.SHA256 -or
                $header.SHA256 -cne $cohort.header.sha256 -or
                $jump.runtime_receipt.sha256 -cne (Hash $cohortPath)) {
                throw 'Fresh jump-buffer consumers do not bind this SDK/runtime/header cohort.'
            }
            foreach ($name in @('layout-build','layout-execute','sigjmp-build','sigjmp-execute')) {
                $run = @($jump.runs | Where-Object name -CEQ $name)
                if ($run.Count -ne 1 -or $run[0].exit -ne 0) {
                    throw "Missing fresh SDK jump-buffer qualification: $name"
                }
            }
            $manifest.JumpBufferQualification = [ordered]@{
                Header = $header
                Consumer = Component $jumpPath
                RuntimeReceipt = Component $cohortPath
                JmpBufBytes = 256; SigjmpBufBytes = 272
                SaveMaskOffset = 256; SignalMaskOffset = 264
                ExistingConsumersRecompiled = $false
                ExistingTargetLibrariesRebuilt = $false
                Scope = 'Fresh public-header consumers and coherent runtime/newlib; recompile all prior undersized-buffer consumers before admission'
            }
        }
        if ($cohort.status -ceq 'coherent-runtime-ucontext-and-bounded-upstream-consumer-qualified') {
            $contextPath = Join-Path $root 'share\toolchain\ucontext\consumer-result.json'
            $context = Get-Content -Raw -LiteralPath $contextPath | ConvertFrom-Json
            $header = Component (Join-Path $root "$sysroot\include\sys\ucontext.h")
            if ($context.passed -ne $true -or
                $context.runtime_receipt.sha256 -cne (Hash $cohortPath) -or
                $context.inputs.runtime.sha256 -cne $components.RuntimeDll.SHA256 -or
                $context.inputs.'import-library'.sha256 -cne $components.MsysImport.SHA256 -or
                $context.inputs.compiler.sha256 -cne $components.GCC.SHA256 -or
                $context.inputs.source.sha256 -cne $cohort.native_context_source.sha256 -or
                $context.inputs.'ucontext-header'.sha256 -cne $header.SHA256 -or
                $header.SHA256 -cne $cohort.ucontext_header.sha256) {
                throw 'Fresh ucontext consumers do not bind the sealed SDK/runtime/source contract.'
            }
            foreach ($name in @('ucontext-build','invalid-build','layout','coroutines','invalid-context')) {
                $run = @($context.runs | Where-Object name -CEQ $name)
                if ($run.Count -ne 1 -or $run[0].process.passed -ne $true -or
                    $run[0].process.exit -ne 0 -or $run[0].process.active_at_boundary -ne 0) {
                    throw "Missing bounded successful ucontext consumer: $name"
                }
                if ($name -in @('layout','coroutines','invalid-context') -and
                    (@($run[0].native_processes).Count -ne 1 -or
                     $run[0].native_processes[0].machine -cne '0xAA64')) {
                    throw "Missing live native process identity for ucontext consumer: $name"
                }
            }
            $manifest.UcontextQualification = [ordered]@{
                Header = $header
                Consumer = Component $contextPath
                RuntimeReceipt = Component $cohortPath
                EntryStackAlignment = 16
                ArgumentCounts = @(0, 1, 8, 9, 12)
                CoroutineYields = 32
                BoundedChildCleanup = $true
                InvalidContextReturnsEINVAL = $true
                ExistingTargetLibrariesRebuilt = $false
                Scope = 'Fresh exact runtime-owned context sources, native entry/return/arguments/FEnv/signal-mask/TLS controls; not full libxcrypt or generic DLL lifecycle admission'
            }
        }
    }
    $manifest | ConvertTo-Json -Depth 12 | Set-Content "$output.pending" -Encoding utf8
    Move-Item -LiteralPath "$output.pending" -Destination $output
    Write-Output "Published native MSYS epoch $epochHash in $output"
} finally {
    $env:PATH = $oldPath
}
