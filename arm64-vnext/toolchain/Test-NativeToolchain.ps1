[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [ValidateSet('MinGW', 'MSYS')][string] $Profile = 'MinGW'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\Get-ToolchainPeIdentity.ps1"
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Choose a new evidence directory: $OutputDirectory"
}
$out = [IO.Directory]::CreateDirectory($OutputDirectory).FullName
$bin = Join-Path $Prefix 'bin'
$target = if ($Profile -eq 'MSYS') { 'aarch64-pc-cygwin' } else { 'aarch64-w64-mingw32' }
$identities = @(Get-ChildItem -LiteralPath $Prefix -Recurse -File |
    Where-Object { $_.Extension -in '.exe', '.dll' } |
    ForEach-Object { Get-ToolchainPeIdentity $_.FullName })
if ($identities.Count -eq 0 -or
    @($identities | Where-Object { -not $_.NativeArm64 -or -not $_.DynamicBase }).Count) {
    throw 'Compiler prefix is empty, non-ARM64, or lacks mandatory ARM64 ASLR.'
}
$identities | ConvertTo-Json -Depth 8 | Set-Content "$out\tool-identities.json" -Encoding utf8

function Tool([string] $Name) {
    foreach ($candidate in @("$bin\$Name.exe", "$bin\$target-$Name.exe")) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw "Missing native tool: $Name"
}
$cc = Tool gcc
$cxx = Tool 'g++'
$assembler = Tool as
$null = Tool ld
$null = Tool ar
$null = Tool nm
$null = Tool windres
if ((& $cc -dumpmachine | Out-String).Trim() -ne $target -or $LASTEXITCODE -ne 0) {
    throw "Compiler target does not match the $Profile profile."
}
$runs = [Collections.Generic.List[object]]::new()
function Run([string] $Name, [string] $Executable, [string[]] $Arguments, [string] $ExpectedText = '') {
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $stdoutBytes = [IO.MemoryStream]::new()
    $stderrBytes = [IO.MemoryStream]::new()
    $process = [Diagnostics.Process]::Start($info)
    try {
        $stdout = $process.StandardOutput.BaseStream.CopyToAsync($stdoutBytes)
        $stderr = $process.StandardError.BaseStream.CopyToAsync($stderrBytes)
        if (-not $process.WaitForExit(120000)) {
            Stop-Process -Id $process.Id -ErrorAction Stop
            throw "$Name timed out"
        }
        [void]$stdout.GetAwaiter().GetResult()
        [void]$stderr.GetAwaiter().GetResult()
        $outputData = $stdoutBytes.ToArray()
        $errorData = $stderrBytes.ToArray()
        [IO.File]::WriteAllBytes("$out\$Name.stdout.bin", $outputData)
        [IO.File]::WriteAllBytes("$out\$Name.stderr.bin", $errorData)
        $utf8 = [Text.UTF8Encoding]::new($false, $true)
        $text = $utf8.GetString($outputData)
        $errorText = $utf8.GetString($errorData)
        $text | Set-Content "$out\$Name.stdout.txt" -Encoding utf8
        $errorText | Set-Content "$out\$Name.stderr.txt" -Encoding utf8
        $runs.Add([pscustomobject]@{
            Name = $Name; Executable = $Executable; Arguments = $Arguments
            ExitCode = $process.ExitCode
        })
        if ($process.ExitCode -ne 0) { throw "$Name failed ($($process.ExitCode)): $errorText" }
        if ($ExpectedText -and $text.Trim() -ne $ExpectedText) { throw "$Name output mismatch: $text" }
    }
    finally {
        $process.Dispose()
        $stdoutBytes.Dispose()
        $stderrBytes.Dispose()
    }
}

function Assert-UnchangedInputs {
    foreach ($identity in @($identities) + @($runtimeInputs)) {
        if ((Get-FileHash -LiteralPath $identity.Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne
            $identity.SHA256) {
            throw "Tool changed during the round trip: $($identity.Path)"
        }
    }
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CompilerMachineProbe {
    [StructLayout(LayoutKind.Sequential)]
    public struct Info { public ushort Machine, Reserved; public uint Attributes; }
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetProcessInformation(IntPtr process, int kind, out Info info, uint size);
}
'@

$oldPath = $env:PATH
try {
    $env:PATH = "$bin;$oldPath"
    $runtimeNames = if ($Profile -eq 'MSYS') {
        @('crt0.o', 'crtbegin.o', 'crtend.o', 'libgcc.a', 'libstdc++.a', 'libmsys-2.0.a', 'specs')
    } else {
        @('crt2.o', 'crt2u.o', 'libgcc.a', 'libstdc++.a',
          'libwinpthread.a', 'libmingw32.a', 'libmingwex.a', 'libmsvcrt.a')
    }
    $runtimeInputs = @(foreach ($name in $runtimeNames) {
        $selected = (& $cc "-print-file-name=$name" | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $selected -eq $name -or
            -not (Test-Path -LiteralPath $selected -PathType Leaf)) {
            throw "Native compiler did not resolve $name to an installed file."
        }
        [pscustomobject]@{
            Name = $name
            Path = [IO.Path]::GetFullPath($selected)
            SHA256 = (Get-FileHash -LiteralPath $selected -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    $start = [Diagnostics.ProcessStartInfo]::new($cc)
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in @('-x', 'c', '-fsyntax-only', '-')) { $start.ArgumentList.Add($argument) }
    $held = [Diagnostics.Process]::Start($start)
    try {
        $machine = [CompilerMachineProbe+Info]::new()
        if (-not [CompilerMachineProbe]::GetProcessInformation($held.Handle, 9, [ref]$machine, 8)) {
            throw [ComponentModel.Win32Exception]::new([Runtime.InteropServices.Marshal]::GetLastWin32Error())
        }
        if ($machine.Machine -ne 0xaa64) { throw 'The running compiler is not native ARM64.' }
        $processIdentity = [ordered]@{
            ProcessId = $held.Id; Image = $cc
            Machine = ('0x{0:X4}' -f $machine.Machine); Attributes = $machine.Attributes
        }
        $held.StandardInput.WriteLine('int main(void) { return 0; }')
        $held.StandardInput.Close()
        if (-not $held.WaitForExit(30000)) {
            Stop-Process -Id $held.Id -ErrorAction Stop
            throw 'Compiler stdin probe timed out'
        }
        if ($held.ExitCode -ne 0) { throw "Compiler stdin probe failed: $($held.StandardError.ReadToEnd())" }
    }
    finally {
        if (-not $held.HasExited) { Stop-Process -Id $held.Id -ErrorAction Stop }
        $held.Dispose()
    }
    if ($Profile -eq 'MSYS') {
        $compilerIdentity = Get-ToolchainPeIdentity $cc
        if ('msys-2.0.dll' -in @($compilerIdentity.Imports | ForEach-Object Dll) -or
            -not (@($compilerIdentity.Imports | ForEach-Object Dll) -match '^api-ms-win-crt-')) {
            throw 'Expected a native UCRT-hosted compiler, independently targeting MSYS.'
        }
        Copy-Item -LiteralPath "$bin\msys-2.0.dll" -Destination $out
        foreach ($source in @('msys-native.c', 'msys-module.cc', 'msys-runtime.cc')) {
            Copy-Item -LiteralPath "$PSScriptRoot\probes\$source" -Destination $out
        }
        Run 'msys-c-compile' $cc @('-O2', '-S', "$out\msys-native.c", '-o', "$out\msys-native.s")
        Run 'msys-c-assemble' $assembler @("$out\msys-native.s", '-o', "$out\msys-native.o")
        Run 'msys-module' $cxx @('-O2', '-shared', "$out\msys-module.cc", '-o', "$out\module.dll")
        Run 'msys-c-link' $cc @("$out\msys-native.o", '-o', "$out\msys-native.exe")
        Run 'msys-c-execute' "$out\msys-native.exe" @("$out\module.dll") 'native-msys-c-ok long=8'
        Run 'msys-cxx-build' $cxx @('-std=c++17', '-O2', '-pthread',
                                  "$out\msys-runtime.cc", '-o', "$out\msys-runtime.exe")
        Run 'msys-cxx-execute' "$out\msys-runtime.exe" @() 'native-msys-runtime-ok'
        $outputs = @('msys-native.exe', 'msys-runtime.exe', 'module.dll' |
            ForEach-Object { Get-ToolchainPeIdentity "$out\$_" })
        foreach ($output in $outputs) {
            $dlls = @($output.Imports | ForEach-Object Dll)
            if (-not $output.NativeArm64 -or -not $output.DynamicBase -or
                'msys-2.0.dll' -notin $dlls -or
                $dlls -contains 'msvcrt.dll' -or $dlls -match '^api-ms-win-crt-') {
                throw "Expected ARM64 MSYS-target output, not UCRT target code: $($output.Path)"
            }
        }
        Assert-UnchangedInputs
        [ordered]@{
            RecordedUtc = [DateTime]::UtcNow.ToString('o')
            Passed = $true; Host = 'Windows ARM64 UCRT'; Target = $target; Profile = 'MSYS'
            CompilerProcess = $processIdentity; RuntimeInputs = $runtimeInputs
            RuntimeDll = Get-ToolchainPeIdentity "$out\msys-2.0.dll"
            Runs = $runs.ToArray(); Outputs = $outputs
        } | ConvertTo-Json -Depth 9 | Set-Content "$out\result.json" -Encoding utf8
        Write-Output "Native MSYS compiler C/C++/DLL round trips passed: $out\result.json"
        return
    }
    Copy-Item "$PSScriptRoot\probes\windows-c.c", "$PSScriptRoot\probes\windows-runtime.cc",
        "$PSScriptRoot\probes\windows-unicode.c", "$PSScriptRoot\probes\toolchain.rc",
        "$PSScriptRoot\probes\pe-autoimport-provider.c",
        "$PSScriptRoot\probes\pe-autoimport-consumer.c" $out
    Run 'c-compile' $cc @('-O2', '-S', "$out\windows-c.c", '-o', "$out\windows-c.s")
    Run 'c-assemble' $assembler @("$out\windows-c.s", '-o', "$out\windows-c.o")
    Run 'resource-compile' (Tool windres) @('-i', "$out\toolchain.rc", '-o', "$out\resource.o", '-O', 'coff')
    Run 'c-link' $cc @("$out\windows-c.o", "$out\resource.o", '-o', "$out\windows-c.exe")
    Run 'c-execute' "$out\windows-c.exe" @() "native-printf-73`r`nnative-c-ok"
    Run 'unicode-build' $cc @('-O2', '-municode', "$out\windows-unicode.c", '-o', "$out\windows-unicode.exe")
    Run 'unicode-execute' "$out\windows-unicode.exe" @('arm64-unicode') 'native-unicode-ok'
    Run 'cxx-build' $cxx @('-std=c++17', '-O2', '-static',
        "$out\windows-runtime.cc", '-o', "$out\windows-runtime.exe")
    Run 'cxx-execute' "$out\windows-runtime.exe" @() 'native-runtime-ok'
    Run 'autoimport-provider' $cc @('-O2', '-shared', "$out\pe-autoimport-provider.c",
        "-Wl,--out-implib=$out\provider.a", '-o', "$out\provider.dll")
    Run 'autoimport-consumer' $cc @('-O2', "$out\pe-autoimport-consumer.c",
        "$out\provider.a", '-o', "$out\autoimport.exe")
    $providerIdentity = Get-ToolchainPeIdentity "$out\provider.dll"
    if (-not $providerIdentity.NativeArm64 -or -not $providerIdentity.DynamicBase) {
        throw 'Native compiler produced an invalid autoimport provider architecture or ASLR policy.'
    }
    Run 'autoimport-execute' "$out\autoimport.exe" @()
    $autoimportText = Get-Content -Raw -LiteralPath "$out\autoimport-execute.stdout.txt"
    if ($autoimportText -notmatch '^far-autoimport-ok gap=(\d+)\s*$' -or
        [UInt64]$Matches[1] -le 0x100000000L) {
        throw 'Native external-data probe did not establish a greater-than-4GB DLL gap.'
    }
    $outputs = @("$out\windows-c.exe", "$out\windows-runtime.exe", "$out\windows-unicode.exe",
        "$out\autoimport.exe" |
        ForEach-Object { Get-ToolchainPeIdentity $_ })
    foreach ($output in $outputs) {
        if (-not $output.NativeArm64) { throw 'Compiler produced a non-ARM64 executable.' }
        $dlls = @($output.Imports | ForEach-Object Dll)
        if ($dlls -contains 'msvcrt.dll' -or -not ($dlls -match '^api-ms-win-crt-')) {
            throw "Expected UCRT imports, not legacy MSVCRT: $($output.Path)"
        }
    }
    Assert-UnchangedInputs
    $report = [ordered]@{
        RecordedUtc = [DateTime]::UtcNow.ToString('o')
        Passed = $true; Host = 'Windows ARM64'; Target = 'aarch64-w64-mingw32'
        CompilerProcess = $processIdentity; RuntimeInputs = $runtimeInputs
        Runs = $runs.ToArray(); Outputs = $outputs
        AutoimportProvider = $providerIdentity
    }
    $report | ConvertTo-Json -Depth 9 | Set-Content "$out\result.json" -Encoding utf8
    Write-Output "Native C/C++ compiler round trips passed: $out\result.json"
}
finally { $env:PATH = $oldPath }
