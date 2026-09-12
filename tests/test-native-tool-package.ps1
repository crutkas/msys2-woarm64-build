#requires -Version 7.3
param(
    [Parameter(Mandatory)][ValidateSet('cmake', 'ninja')][string] $Tool,
    [Parameter(Mandatory)][string] $Payload,
    [Parameter(Mandatory)][string] $Inventory,
    [Parameter(Mandatory)][string] $Provenance,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$prepare = Join-Path $PSScriptRoot '..\.github\scripts\prepare-native-tool-package.ps1'
$arguments = @{Tool=$Tool;Payload=$Payload;Inventory=$Inventory;Provenance=$Provenance;OutputDirectory=$OutputDirectory}
& $prepare @arguments
$bytes = [IO.File]::ReadAllBytes("$OutputDirectory\payload-files.sha256")
if ($bytes.Length -eq 0 -or $bytes -contains 13 -or $bytes[-1] -ne 10) {
    throw 'POSIX checksum manifest must be nonempty and LF-terminated without CR.'
}
$text = [IO.File]::ReadAllText("$OutputDirectory\PKGBUILD")
if ($text.Contains('@PAYLOAD_SHA256@') -or $text.Contains('@FILES_SHA256@') -or $text.Contains('@PROVENANCE_SHA256@')) {
    throw 'Unresolved package template checksum.'
}
if ($Tool -eq 'cmake' -and -not $text.Contains('payload/doc/cmake/LICENSE.rst')) { throw 'Missing actual CMake license.' }
"PASS: $Tool payload bound to pinned archive with LF checksum manifest and real license"
$rejected = $false
try { & $prepare @arguments } catch {
    if ($_.Exception.Message -cne 'Tool package output must be new.') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Existing package input output was overwritten.' }
'PASS: preserved existing output'
if ($Tool -eq 'ninja') {
    $fake = Join-Path $OutputDirectory 'wrong-payload'
    New-Item -ItemType Directory -Path "$fake\bin" | Out-Null
    [IO.File]::WriteAllText("$fake\bin\ninja.exe", 'Deliberately not the official executable.')
    @(@{Path='bin\ninja.exe';SHA256=(Get-FileHash -LiteralPath "$fake\bin\ninja.exe").Hash.ToLowerInvariant()}) |
        ConvertTo-Json -AsArray | Set-Content -LiteralPath "$OutputDirectory\wrong-inventory.json" -Encoding utf8
    $arguments.Payload = $fake
    $arguments.Inventory = "$OutputDirectory\wrong-inventory.json"
    $arguments.OutputDirectory = "$OutputDirectory\rejected-payload"
    $rejected = $false
    try { & $prepare @arguments } catch {
        if ($_.Exception.Message -cne 'Ninja payload is not the pinned official executable.') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Caller inventory substituted for actual archive identity.' }
    'PASS: matching caller inventory cannot admit an unrelated executable'
}
