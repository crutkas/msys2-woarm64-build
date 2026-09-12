#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $ProfileManifest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path -LiteralPath $Prefix).ProviderPath.TrimEnd('\')
$manifestPath = (Resolve-Path -LiteralPath $ProfileManifest).ProviderPath
$profile = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json -AsHashtable

function Fail-Profile([string] $Reason) {
    throw "Invalid MSYS default profile: $Reason"
}

if ($profile -isnot [Collections.IDictionary] -or
    $profile.schemaVersion -isnot [long] -or $profile.schemaVersion -ne 1) {
    Fail-Profile 'expected schemaVersion 1'
}
foreach ($name in 'target', 'compiler', 'compilerSha256', 'originalSpecsSha256', 'specs', 'specsSha256', 'scope', 'profileMode') {
    if (-not $profile.Contains($name) -or $profile[$name] -isnot [string] -or [string]::IsNullOrWhiteSpace($profile[$name])) {
        Fail-Profile "missing or invalid $name"
    }
}
if ($profile.target -cne 'aarch64-pc-cygwin' -or $profile.profileMode -cne 'default') {
    Fail-Profile 'requires aarch64-pc-cygwin with an automatically loaded default profile'
}
foreach ($name in 'compilerSha256', 'originalSpecsSha256', 'specsSha256') {
    if ($profile[$name] -cnotmatch '^[0-9a-f]{64}$') { Fail-Profile "invalid $name" }
}

$bound = @{}
foreach ($name in 'compiler', 'specs') {
    if (-not [IO.Path]::IsPathFullyQualified($profile[$name])) { Fail-Profile "$name must be absolute" }
    $path = (Resolve-Path -LiteralPath $profile[$name]).ProviderPath
    if (-not $path.StartsWith("$root\", [StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail-Profile "$name must name a file inside the supplied prefix"
    }
    $relative = $path.Substring($root.Length + 1)
    if ($name -eq 'compiler' -and $relative -cnotmatch '^bin\\(?:aarch64-pc-cygwin-)?gcc\.exe$') {
        Fail-Profile 'compiler is not a published GCC driver'
    }
    if ($name -eq 'specs' -and $relative -cnotmatch '^lib\\gcc\\aarch64-pc-cygwin\\[^\\]+\\specs$') {
        Fail-Profile 'specs must use the automatic target-specific specs filename'
    }
    $expected = $profile["${name}Sha256"]
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $expected) { Fail-Profile "$name hash mismatch" }
    $bound[$name] = [pscustomobject]@{ Path = $path; RelativePath = $relative; SHA256 = $actual }
}

$specs = [IO.File]::ReadAllText($bound.specs.Path).Replace("`r`n", "`n")
$sections = @{}
foreach ($name in 'self_spec', 'lib', 'link') {
    $matches = [regex]::Matches($specs, "(?m)^\*$name`:\n([^\n]*)$")
    if ($matches.Count -ne 1 -or [string]::IsNullOrWhiteSpace($matches[0].Groups[1].Value)) {
        Fail-Profile "expected one nonempty $name section"
    }
    $sections[$name] = $matches[0].Groups[1].Value
}
# cpp specs do not apply this definition to normal C++ compilation.
if ($sections.self_spec -cnotmatch '(?:^|\s)-D__MSYS__(?:\s|$)') {
    Fail-Profile 'self_spec must define __MSYS__ for both C and C++'
}
if ($sections.lib -cnotmatch '(?:^|[\s:{])-lmsys-2\.0(?:[\s}]|$)' -or
    [regex]::Matches($sections.link, '_msys_dll_entry').Count -ne 2 -or
    [regex]::Matches($sections.link, '--dll-search-prefix=msys-').Count -ne 1 -or
    $sections.lib.Contains('-lcygwin') -or $sections.link.Contains('_cygwin_dll_entry') -or
    $sections.link.Contains('--dll-search-prefix=cyg')) {
    Fail-Profile 'MSYS macro, runtime library, entry points or DLL prefix differ from the published generator contract'
}

[pscustomobject]@{
    Kind = 'msys-default-profile-binding'
    Target = $profile.target
    Compiler = $bound.compiler
    Specs = $bound.specs
    Manifest = [pscustomobject]@{
        Path = $manifestPath
        SHA256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    Scope = 'Default specs source and file binding only; not native compiler or runtime acceptance'
}
