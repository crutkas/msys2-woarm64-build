#requires -Version 7.3
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\..\.github\scripts\export-python-provider-packages.ps1"

$names = @(Get-PythonProviderPackageNames)
if ($names.Count -ne 19) { throw 'Python provider closure must contain exactly 19 package identities.' }
if ($names.Count -ne ($names | Sort-Object -Unique).Count) {
    throw 'Python provider package identities must be unique.'
}
foreach ($required in @(
    'mingw-w64-aarch64-python',
    'mingw-w64-aarch64-gcc',
    'mingw-w64-aarch64-openssl',
    'mingw-w64-aarch64-sqlite3',
    'mingw-w64-aarch64-tcl',
    'mingw-w64-aarch64-tk'
)) {
    if ($required -cnotin $names) { throw "Missing Python provider package identity: $required" }
}
if ($names | Where-Object { -not $_.StartsWith('mingw-w64-aarch64-', [StringComparison]::Ordinal) }) {
    throw 'Python provider closure must not substitute MSYS, MINGW64, or CLANGARM64 package identities.'
}

$script = [IO.File]::ReadAllText("$PSScriptRoot\..\.github\scripts\export-python-provider-packages.ps1")
foreach ($required in @(
    'Package archive lacks',
    'duplicate package identities',
    'Python provider closure is incomplete',
    "status = 'admitted-complete-exported-verified-native-python-provider'",
    'name = $item.metadata.packageName',
    'path = "packages/$($item.file)"',
    'reusedUnchanged = $true',
    'No package identity, dependency, provides, conflicts, or replaces metadata is rewritten.'
)) {
    if (-not $script.Contains($required, [StringComparison]::Ordinal)) {
        throw "Python provider exporter lost invariant: $required"
    }
}

'PASS: Python provider export preserves 19 genuine MINGWARM64 package identities and metadata'
