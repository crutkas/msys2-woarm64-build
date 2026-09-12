[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Baseline,
    [Parameter(Mandatory)][string] $RuntimeSysroot,
    [Parameter(Mandatory)][string] $RuntimeDll,
    [Parameter(Mandatory)][string] $RuntimeReceipt,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string] $RuntimeReceiptSHA256,
    [string] $RuntimeInputManifest,
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $StageReceipt
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant() }
if ((Test-Path -LiteralPath $Prefix) -or (Test-Path -LiteralPath $StageReceipt)) {
    throw 'Use new SDK and evidence paths; existing cohorts are immutable.'
}
$baselineRoot = [IO.Path]::GetFullPath($Baseline).TrimEnd('\') + '\'
$prefixRoot = [IO.Path]::GetFullPath($Prefix).TrimEnd('\') + '\'
if ($prefixRoot.StartsWith($baselineRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Do not stage inside the baseline prefix.'
}
if ((Hash $RuntimeReceipt) -cne $RuntimeReceiptSHA256) { throw 'Runtime receipt hash differs.' }
$runtimeProof = Get-Content -Raw -LiteralPath $RuntimeReceipt | ConvertFrom-Json
if ($runtimeProof.schema -ne 1) { throw 'Unsupported runtime receipt schema.' }
$isSigjmp = $false
$isUcontext = $false
switch -CaseSensitive ($runtimeProof.status) {
    'runtime-ctype-abi-and-genuine-hosted-consumer-qualified' {
        if ($runtimeProof.ownership.active_runtime_writers -ne 0) {
            throw 'The ctype runtime cohort still has active writers.'
        }
    }
    'coherent-runtime-jump-buffer-abi-and-bounded-upstream-consumer-qualified' {
        $isSigjmp = $true
        if ($runtimeProof.ownership.active_runtime_jobs -ne 0 -or
            $runtimeProof.layout.new_jmp_buf_bytes -ne 256 -or
            $runtimeProof.layout.new_sigjmp_buf_bytes -ne 272 -or
            $runtimeProof.layout.new_macro_and_function_flag_offset -ne 256 -or
            $runtimeProof.layout.new_macro_and_function_sigmask_offset -ne 264 -or
            $runtimeProof.results.corrected_header_canary_preserved -ne $true -or
            $runtimeProof.results.unmasked_after_every_siglongjmp -ne $true -or
            $runtimeProof.results.repeated_macro_and_function_protected_page_recoveries -ne 8 -or
            $runtimeProof.results.upstream_crypt_badargs_exit -ne 0) {
            throw 'The sigjmp cohort does not establish the required public buffer ABI.'
        }
        if (-not $RuntimeInputManifest -or
            (Hash $RuntimeInputManifest) -cne $runtimeProof.compiler_runtime_input_inventory.sha256) {
            throw 'The complete sealed runtime/header input inventory is required.'
        }
    }
    'coherent-runtime-ucontext-and-bounded-upstream-consumer-qualified' {
        $isSigjmp = $true
        $isUcontext = $true
        if ($runtimeProof.ownership.active_runtime_jobs -ne 0 -or
            $runtimeProof.results.arm64_entry_sp_alignment -ne 16 -or
            ($runtimeProof.results.argument_counts_executed -join ',') -cne '0,1,8,9,12' -or
            $runtimeProof.results.coroutine_yields -ne 32 -or
            $runtimeProof.results.upstream_original_executable_exit -ne 0 -or
            $runtimeProof.results.upstream_fresh_test_and_helper_exit -ne 0 -or
            $runtimeProof.results.c_headers -ne 268 -or
            $runtimeProof.results.runtime_library_and_crt_inputs -ne 19) {
            throw 'The ucontext cohort does not establish the required entry/return and consumer contract.'
        }
        foreach ($field in @('stack_argument_8_starts_at_sp','lr_continuation_and_linked_return',
                              'signal_masks_and_fp_rounding_preserved','same_thread_tls_and_errno_preserved',
                              'null_link_child_return_and_exit_zero',
                              'invalid_context_returns_minus_one_einval_and_restores_mask',
                              'upstream_source_and_original_flags_unchanged','no_test_disabled_or_skipped')) {
            if ($runtimeProof.results.$field -ne $true) {
                throw "The ucontext runtime receipt lacks a passing required result: $field"
            }
        }
        if (-not $RuntimeInputManifest -or
            (Hash $RuntimeInputManifest) -cne $runtimeProof.compiler_runtime_input_inventory.sha256) {
            throw 'The complete sealed runtime/header input inventory is required.'
        }
    }
    default { throw 'The runtime owner has not published a supported qualified API cohort.' }
}
$sourceSysroot = "$($runtimeProof.prefix)/aarch64-pc-cygwin"
$sourceDll = $runtimeProof.runtime.path
if (-not $sourceSysroot.StartsWith('/') -or -not $sourceDll.StartsWith('/')) {
    throw 'The qualified runtime receipt must retain its original Linux source paths.'
}
foreach ($relative in @('include\ctype.h','include\stdio.h','lib\crt0.o','lib\libmsys-2.0.a')) {
    if (-not (Test-Path -LiteralPath (Join-Path $RuntimeSysroot $relative) -PathType Leaf)) {
        throw "Missing paired runtime input: $relative"
    }
}
$pairedFiles = [ordered]@{
    'lib\crt0.o' = 'startup'
    'lib\libmsys-2.0.a' = 'import_library'
    'include\newlib.h' = 'generated_header'
}
if ($isSigjmp) { $pairedFiles['include\machine\setjmp.h'] = 'header' }
else { $pairedFiles['include\ctype.h'] = 'ctype_header' }
if ($isUcontext) { $pairedFiles['include\sys\ucontext.h'] = 'ucontext_header' }
foreach ($relative in $pairedFiles.Keys) {
    if ((Hash (Join-Path $RuntimeSysroot $relative)) -cne $runtimeProof.($pairedFiles[$relative]).sha256) {
        throw "Runtime receipt does not qualify this input: $relative"
    }
}
if ((Hash $RuntimeDll) -cne $runtimeProof.runtime.sha256) {
    throw 'Runtime receipt does not qualify this DLL.'
}
$sealedFiles = @{}
if ($isSigjmp) {
    $inventoryRoot = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($RuntimeInputManifest))
    foreach ($line in [IO.File]::ReadAllLines($RuntimeInputManifest)) {
        if ($line -cnotmatch '^([0-9a-f]{64})  (?:\./)?([a-z-]+\.sha256|counts\.txt)$') {
            throw 'Malformed runtime inventory index row.'
        }
        if ((Hash (Join-Path $inventoryRoot $Matches[2])) -cne $Matches[1]) {
            throw 'A sealed runtime inventory child differs from its index.'
        }
    }
    $headerManifest = Join-Path $inventoryRoot 'runtime-c-headers.sha256'
    $libraryManifest = Join-Path $inventoryRoot 'runtime-libraries.sha256'
    if ((Hash $headerManifest) -cne $runtimeProof.runtime_c_headers.sha256 -or
        (Hash $libraryManifest) -cne $runtimeProof.runtime_libraries.sha256) {
        throw 'Runtime header/library inventories differ from the owner receipt.'
    }
    foreach ($line in @([IO.File]::ReadAllLines($headerManifest)) +
                      @([IO.File]::ReadAllLines($libraryManifest))) {
        if ($line -cnotmatch '^([0-9a-f]{64})  (.+)$') { throw 'Malformed runtime inventory row.' }
        $sha = $Matches[1]
        $name = $Matches[2]
        if ($name -ceq 'bin/msys-2.0.dll') { $inputPath = $RuntimeDll }
        elseif ($name.StartsWith('aarch64-pc-cygwin/include/', [StringComparison]::Ordinal) -or
                $name.StartsWith('aarch64-pc-cygwin/lib/', [StringComparison]::Ordinal)) {
            $relative = $name.Substring('aarch64-pc-cygwin/'.Length).Replace('/','\')
            $inputPath = [IO.Path]::GetFullPath((Join-Path $RuntimeSysroot $relative))
            if (-not $inputPath.StartsWith([IO.Path]::GetFullPath($RuntimeSysroot).TrimEnd('\') + '\',
                                          [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Runtime inventory path escapes its sysroot.'
            }
        } else { throw "Unexpected runtime inventory path: $name" }
        if ($sealedFiles.ContainsKey($name) -or (Hash $inputPath) -cne $sha) {
            throw "Runtime inventory has duplicate or changed input: $name"
        }
        $sealedFiles[$name] = $sha
    }
    if ($sealedFiles.Count -ne 287) { throw 'Expected the complete 268-header/19-runtime-file inventory.' }
}
$compiler = Join-Path $Baseline 'bin\gcc.exe'
$target = (& $compiler -dumpmachine | Out-String).Trim()
if ($LASTEXITCODE -or $target -cne 'aarch64-pc-cygwin') { throw 'Expected an MSYS-target baseline.' }
$version = (& $compiler -dumpversion | Out-String).Trim()
if ($LASTEXITCODE -or $version -notmatch '^\d+\.\d+(\.\d+)?$') { throw 'Cannot resolve compiler version.' }
foreach ($relative in @("$target\include\c++\$version\iostream",
                         "$target\lib\libstdc++.a","$target\lib\libsupc++.a")) {
    if (-not (Test-Path -LiteralPath (Join-Path $Baseline $relative) -PathType Leaf)) {
        throw "Baseline has no genuine hosted C++ input: $relative"
    }
}
$baselineFiles = @(Get-ChildItem -LiteralPath $Baseline -Recurse -File | ForEach-Object {
    [pscustomobject]@{ Path = [IO.Path]::GetRelativePath($Baseline, $_.FullName); SHA256 = Hash $_.FullName }
})
$runtimeFiles = @(foreach ($directory in @('include','lib')) {
    Get-ChildItem -LiteralPath (Join-Path $RuntimeSysroot $directory) -Recurse -File |
        ForEach-Object {
            if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Materialize Unix runtime inputs with tar --dereference before staging: $($_.FullName)"
            }
            $relative = [IO.Path]::GetRelativePath($RuntimeSysroot, $_.FullName)
            # Runtime cross prefixes can retain freestanding C++ headers.
            # Keep the native SDK's real hosted headers and libraries instead.
            if (-not $relative.StartsWith('include\c++\', [StringComparison]::OrdinalIgnoreCase) -and
                $_.Name -notmatch '^(libstdc\+\+|libsupc\+\+|libgcc|libgcov).*\.a$') {
                [pscustomobject]@{ Path = $relative; Source = $_.FullName; SHA256 = Hash $_.FullName }
            }
        }
})
if ($isSigjmp) {
    $runtimeFiles = @($runtimeFiles | Where-Object {
        $name = 'aarch64-pc-cygwin/' + $_.Path.Replace('\','/')
        if ($sealedFiles.ContainsKey($name)) { $true }
        elseif ($_.Path -ceq 'lib\libg.a' -and $_.SHA256 -ceq $runtimeProof.import_library.sha256) { $true }
        else { $false }
    })
    foreach ($name in $sealedFiles.Keys) {
        if ($name -ceq 'bin/msys-2.0.dll') { continue }
        $relative = $name.Substring('aarch64-pc-cygwin/'.Length).Replace('/','\')
        if (@($runtimeFiles | Where-Object Path -CEQ $relative).Count -ne 1) {
            throw "Qualified input was not selected for SDK staging: $name"
        }
    }
}
$dllHash = Hash $RuntimeDll
Copy-Item -LiteralPath $Baseline -Destination $Prefix -Recurse
foreach ($file in $runtimeFiles) {
    $destination = Join-Path (Join-Path $Prefix $target) $file.Path
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
    Copy-Item -LiteralPath $file.Source -Destination $destination
}
Copy-Item -LiteralPath $RuntimeDll -Destination (Join-Path $Prefix 'bin\msys-2.0.dll')
$metadata = [IO.Directory]::CreateDirectory((Join-Path $Prefix 'share\toolchain\identities')).FullName
$rows = @($runtimeFiles | Sort-Object Path | ForEach-Object { "$($_.SHA256)  $($_.Path.Replace('\','/'))" })
[IO.File]::WriteAllText("$metadata\runtime-inputs.sha256", ($rows -join "`n") + "`n")
[IO.File]::WriteAllText("$metadata\runtime-dll.sha256", "$dllHash  $sourceDll`n")
[IO.File]::WriteAllText("$metadata\runtime-sysroot.txt", "$sourceSysroot`n")
[IO.File]::WriteAllText("$metadata\runtime-dll-path.txt", "$sourceDll`n")
Copy-Item -LiteralPath $RuntimeReceipt -Destination "$metadata\runtime-cohort-receipt.json"
if ($isSigjmp) {
    $sealedDirectory = [IO.Directory]::CreateDirectory("$metadata\sigjmp-input-inventory").FullName
    Copy-Item -LiteralPath $RuntimeInputManifest -Destination "$sealedDirectory\SHA256SUMS"
    foreach ($line in [IO.File]::ReadAllLines($RuntimeInputManifest)) {
        if ($line -cnotmatch '^[0-9a-f]{64}  (?:\./)?([a-z-]+\.sha256|counts\.txt)$') {
            throw 'Runtime inventory index changed during staging.'
        }
        Copy-Item -LiteralPath (Join-Path $inventoryRoot $Matches[1]) -Destination $sealedDirectory
    }
}
python "$PSScriptRoot\generate-msys-specs.py" --compiler "$Prefix\bin\gcc.exe" `
    --output "$Prefix\lib\gcc\$target\$version\specs" `
    --manifest "$Prefix\share\toolchain\msys-profile.json" --profile-mode default | Out-Host
if ($LASTEXITCODE) { throw 'Cannot bind the relocated SDK default MSYS profile.' }
$allowedChanges = @{}
foreach ($file in $runtimeFiles) { $allowedChanges["$target\$($file.Path)"] = $file.SHA256 }
$allowedChanges['bin\msys-2.0.dll'] = $dllHash
if ($isSigjmp) {
    foreach ($file in Get-ChildItem -LiteralPath "$metadata\sigjmp-input-inventory" -File) {
        $relative = [IO.Path]::GetRelativePath($Prefix, $file.FullName)
        $allowedChanges[$relative] = Hash $file.FullName
    }
}
foreach ($relative in @('share\toolchain\msys-profile.json',
                        'share\toolchain\identities\runtime-inputs.sha256',
                        'share\toolchain\identities\runtime-dll.sha256',
                        'share\toolchain\identities\runtime-sysroot.txt',
                        'share\toolchain\identities\runtime-dll-path.txt',
                        'share\toolchain\identities\runtime-cohort-receipt.json')) {
    $allowedChanges[$relative] = Hash (Join-Path $Prefix $relative)
}
foreach ($file in $baselineFiles) {
    if ((Hash (Join-Path $Baseline $file.Path)) -cne $file.SHA256) {
        throw "Baseline changed during staging: $($file.Path)"
    }
    $expected = if ($allowedChanges.ContainsKey($file.Path)) { $allowedChanges[$file.Path] } else { $file.SHA256 }
    if ((Hash (Join-Path $Prefix $file.Path)) -cne $expected) {
        throw "Unexpected SDK input change: $($file.Path)"
    }
}
foreach ($file in $runtimeFiles) {
    if ((Hash $file.Source) -cne $file.SHA256 -or
        (Hash (Join-Path (Join-Path $Prefix $target) $file.Path)) -cne $file.SHA256) {
        throw "Runtime source/staged input differs: $($file.Path)"
    }
}
if ((Hash $RuntimeDll) -cne $dllHash -or (Hash $RuntimeReceipt) -cne $RuntimeReceiptSHA256) {
    throw 'Runtime cohort changed during staging.'
}
[ordered]@{
    SchemaVersion = 1; Status = 'paired-native-msys-sdk-awaiting-acceptance'
    Prefix = $prefixRoot.TrimEnd('\'); Baseline = $baselineRoot.TrimEnd('\')
    RuntimeSysroot = $RuntimeSysroot; RuntimeDll = $RuntimeDll; RuntimeDllSHA256 = $dllHash
    SourceSysroot = $sourceSysroot; SourceDll = $sourceDll
    RuntimeReceipt = $RuntimeReceipt; RuntimeReceiptSHA256 = $RuntimeReceiptSHA256
    RuntimeInputManifest = $RuntimeInputManifest
    JumpBufferAbiChanged = (Hash (Join-Path $Baseline "$target\include\machine\setjmp.h")) -cne
                          (Hash (Join-Path $Prefix "$target\include\machine\setjmp.h"))
    UcontextImplementationChanged = $isUcontext
    BaselineFiles = $baselineFiles; RuntimeFiles = $runtimeFiles
    Preserved = 'Compiler binaries, POSIX libgcc, hosted C++ headers/libstdc++/libsupc++, and source identities'
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $StageReceipt -Encoding utf8
Write-Output "Paired SDK staged, not yet qualified: $Prefix"
