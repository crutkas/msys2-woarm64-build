#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\cohort-inventory.ps1"
$root = (Resolve-Path -LiteralPath $Prefix).ProviderPath.TrimEnd('\')
$manifestPath = (Resolve-Path -LiteralPath $Manifest).ProviderPath
$data = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json -AsHashtable
function Reject([string] $Reason) { throw "Unqualified native MinGW cohort: $Reason" }
foreach ($name in 'SchemaVersion', 'Kind', 'Status', 'Prefix', 'Host', 'Target', 'Epoch', 'Files', 'Evidence', 'SourceBinding') {
    if (-not $data.Contains($name)) { Reject "missing $name" }
}
if ($data.SchemaVersion -isnot [long] -or $data.SchemaVersion -ne 1 -or $data.Kind -cne 'native-mingw-package-cohort' -or $data.Status -cne 'qualified' -or
    $data.Host -cne 'Windows ARM64' -or $data.Target -cne 'aarch64-w64-mingw32' -or
    [IO.Path]::GetFullPath($data.Prefix).TrimEnd('\') -ine $root) {
    Reject 'manifest host, target, status or prefix does not match'
}
Assert-CohortInventory $root @($data.Files)
$epoch = & "$PSScriptRoot\get-toolchain-epoch.ps1" -Inputs $data.Files
if ($epoch -cne $data.Epoch) { Reject 'full input epoch mismatch' }
$files = @{}
foreach ($entry in $data.Files) { $files[(Join-Path $root $entry.Path)] = $entry.SHA256 }
$descriptors = [Collections.Generic.List[object]]::new()
function Read-Proof($Binding) {
    if ($Binding -isnot [Collections.IDictionary] -or -not $Binding.Contains('Path') -or
        -not $Binding.Contains('SHA256') -or $Binding.SHA256 -cnotmatch '^[0-9a-f]{64}$' -or
        -not [IO.Path]::IsPathFullyQualified($Binding.Path)) { Reject 'invalid evidence binding' }
    $hash = (Get-FileHash -LiteralPath $Binding.Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -cne $Binding.SHA256) { Reject "evidence hash mismatch: $($Binding.Path)" }
    $descriptors.Add([pscustomobject]@{ Path = $Binding.Path; SHA256 = $hash })
    Get-Content -Raw -LiteralPath $Binding.Path | ConvertFrom-Json -AsHashtable
}
function Assert-Input($Record) {
    $path = [IO.Path]::GetFullPath($Record.Path)
    if (-not $files.ContainsKey($path) -or $files[$path] -cne $Record.SHA256) { Reject "proof used a different input: $path" }
}
function Assert-Output($Record) {
    if ($Record.NativeArm64 -ne $true -or $Record.DynamicBase -ne $true -or $Record.Machine -cne '0xAA64') {
        Reject 'proof output lacks native ARM64 PE/ASLR identity'
    }
    if ((Get-FileHash -LiteralPath $Record.Path).Hash.ToLowerInvariant() -cne $Record.SHA256) { Reject 'proof output bytes changed' }
}
function Assert-Runs($Proof, [string[]] $Names, [hashtable] $Expected = @{}) {
    if ($Proof.Passed -isnot [bool] -or -not $Proof.Passed -or @($Proof.Runs).Count -ne $Names.Count) {
        Reject 'required proof failed or has incomplete runs'
    }
    foreach ($name in $Names) {
        $runs = @($Proof.Runs | Where-Object { $_.Name -ceq $name })
        $exit = if ($Expected.ContainsKey($name)) { $Expected[$name] } else { 0 }
        if ($runs.Count -ne 1 -or $runs[0].ExitCode -isnot [long] -or $runs[0].ExitCode -ne $exit) {
            Reject "required run failed or absent: $name"
        }
    }
}
$source = Read-Proof $data.SourceBinding
if ([IO.Path]::GetFullPath($source.Prefix).TrimEnd('\') -ine $root -or
    $source.Epoch -cne $epoch -or
    (& "$PSScriptRoot\get-toolchain-epoch.ps1" -Inputs $source.Files) -cne $epoch) {
    Reject 'source-copy binding differs from manifest cohort'
}
foreach ($name in 'Native', 'Driver', 'Cache', 'ToolIdentities', 'Seh') {
    if (-not $data.Evidence.Contains($name)) { Reject "missing $name proof" }
}
$native = Read-Proof $data.Evidence.Native
$driver = Read-Proof $data.Evidence.Driver
$cache = Read-Proof $data.Evidence.Cache
$images = @(Read-Proof $data.Evidence.ToolIdentities)
$seh = Read-Proof $data.Evidence.Seh
Assert-Runs $native @('c-compile', 'c-assemble', 'resource-compile', 'c-link', 'c-execute',
    'unicode-build', 'unicode-execute', 'cxx-build', 'cxx-execute', 'autoimport-provider', 'autoimport-consumer', 'autoimport-execute')
if ($native.Host -cne 'Windows ARM64' -or $native.Target -cne $data.Target -or
    $native.CompilerProcess.Machine -cne '0xAA64' -or
    [IO.Path]::GetFullPath($native.CompilerProcess.Image) -ine (Join-Path $root 'bin\gcc.exe')) {
    Reject 'native compiler process/target proof differs'
}
$identities = @{}
foreach ($image in $images) {
    Assert-Input $image
    if ($image.NativeArm64 -ne $true -or $image.Machine -cne '0xAA64' -or -not $image.DynamicBase) {
        Reject 'non-native tool identity'
    }
    $path = [IO.Path]::GetFullPath($image.Path)
    if ($identities.ContainsKey($path)) { Reject 'duplicate tool identity' }
    $identities[$path] = $image
}
foreach ($path in $files.Keys) {
    if ([IO.Path]::GetExtension($path).ToLowerInvariant() -in @('.exe', '.dll') -and -not $identities.ContainsKey($path)) {
        Reject "unexamined PE input: $path"
    }
}
foreach ($name in 'gcc.exe', 'g++.exe', 'as.exe', 'ld.exe', 'ar.exe', 'ranlib.exe', 'windres.exe', 'objcopy.exe', 'strip.exe') {
    if (-not $identities.ContainsKey((Join-Path $root "bin\$name"))) { Reject "required tool omitted: $name" }
}
foreach ($inputRecord in $native.RuntimeInputs) { Assert-Input $inputRecord }
foreach ($name in 'crt2.o', 'crt2u.o', 'libgcc.a', 'libstdc++.a', 'libwinpthread.a', 'libmingw32.a', 'libmingwex.a', 'libmsvcrt.a') {
    if (@($native.RuntimeInputs | Where-Object { $_.Name -ceq $name }).Count -ne 1) { Reject "required library proof omitted: $name" }
}
foreach ($output in @($native.Outputs) + @($native.AutoimportProvider)) { Assert-Output $output }
if (@($native.Outputs).Count -ne 4) { Reject 'native C/C++/Unicode/autoimport outputs incomplete' }
Assert-Runs $driver @('c-suffix', 'c-native-run', 'cxx-suffix', 'cxx-native-run', 'object-name', 'explicit-name',
    'resource-quoted', 'resource-link', 'resource-native-run')
if ($driver.Legacy -ne $false -or [IO.Path]::GetFullPath($driver.Prefix).TrimEnd('\') -ine $root) { Reject 'wrong driver proof cohort' }
foreach ($name in 'gcc', 'g++', 'windres') { Assert-Input $driver[$name] }
if (@($driver.Outputs).Count -ne 3) { Reject 'driver outputs incomplete' }
foreach ($output in $driver.Outputs) { Assert-Output $output }
Assert-Runs $cache @('windows-clear-cache-build', 'windows-cache-contract-build', 'cache-disassembly',
    'cache-archive-relocations', 'native-execute', 'contract-success', 'contract-failure', 'contract-reversed') @{
        'contract-failure' = 71; 'contract-reversed' = 72
    }
if ($cache.Legacy -ne $false -or [IO.Path]::GetFullPath($cache.Prefix).TrimEnd('\') -ine $root) { Reject 'wrong cache proof cohort' }
Assert-Input $cache.Compiler
Assert-Input $cache.Library
Assert-Output $cache.Probe
$imports = @($cache.Probe.Imports | Where-Object { $_.Dll -ieq 'KERNEL32.dll' } | ForEach-Object { $_.Symbols })
if ('FlushInstructionCache' -notin $imports) { Reject 'cache proof did not exercise Windows cache API' }
if ($seh.Passed -isnot [bool] -or -not $seh.Passed -or $seh.ExitCode -ne 0 -or
    [IO.Path]::GetFullPath($seh.Compiler.Path) -ine (Join-Path $root 'bin\gcc.exe')) { Reject 'SEH reproducer did not pass on this compiler' }
Assert-Input $seh.Compiler
foreach ($entry in @($seh.Input, $seh.Object)) {
    if ((Get-FileHash -LiteralPath $entry.Path).Hash.ToLowerInvariant() -cne $entry.SHA256) { Reject 'SEH repro artifact drift' }
}
if (($seh.Options -join ' ') -cne '-g -O2 -Wall -fstack-protector-strong -x cpp-output -c') {
    Reject 'SEH flags changed'
}
$descriptors.Add([pscustomobject]@{ Path = $manifestPath; SHA256 = (Get-FileHash -LiteralPath $manifestPath).Hash.ToLowerInvariant() })
[pscustomobject]@{
    Prefix = $root; Target = $data.Target; Epoch = $epoch; Inputs = $data.Files
    Descriptors = @($descriptors)
    Scope = 'New MinGW compiler/support/native-control binding; not full MSYS or distribution qualification'
}
