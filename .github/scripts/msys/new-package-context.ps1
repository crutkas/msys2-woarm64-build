#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Manifest,
    [Parameter(Mandatory)][string] $MsysRoot,
    [Parameter(Mandatory)][string] $OutputDirectory,
    [Parameter(Mandatory)][ValidateRange(1, 16)][int] $Jobs
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. "$PSScriptRoot\package-config.ps1"

# Never prepare executable build settings from schema-only or failed evidence.
$binding = & "$PSScriptRoot\read-qualified-toolchain.ps1" -Prefix $Prefix -Manifest $Manifest
$msys = (Resolve-Path -LiteralPath $MsysRoot).ProviderPath.TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
foreach ($protected in $msys, $binding.Prefix) {
    if ($output -ieq $protected -or $output.StartsWith("$protected\", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'MSYS package context must not write inside bootstrap or compiler prefixes.'
    }
}
if (Test-Path -LiteralPath $output) { throw 'MSYS package context requires a fresh output directory.' }
foreach ($file in 'usr\bin\cygpath.exe', 'usr\bin\makepkg', 'etc\makepkg.conf') {
    if (-not (Test-Path -LiteralPath (Join-Path $msys $file) -PathType Leaf)) { throw "Missing MSYS2 bootstrap prerequisite: $file" }
}
function ConvertTo-MsysPath([string] $Path) {
    $value = & "$msys\usr\bin\cygpath.exe" -u $Path
    if ($LASTEXITCODE -ne 0 -or $value -isnot [string] -or -not $value.StartsWith('/')) {
        throw "MSYS path conversion failed: $Path"
    }
    $value
}
$outputMsys = ConvertTo-MsysPath $output
$text = New-MsysPackageConfigText -NativeBin (ConvertTo-MsysPath (Join-Path $binding.Prefix 'bin')) `
    -Sysroot (ConvertTo-MsysPath $binding.Sysroot) -OutputRoot $outputMsys -Jobs $Jobs
$environment = [ordered]@{
    MSYSTEM = 'MSYS'
    MSYS2_PATH_TYPE = 'minimal'
    CHERE_INVOKING = '1'
    CARCH = 'aarch64'
    CCACHE_NAMESPACE = "msys-$($binding.EpochSHA256)"
    CCACHE_COMPILERCHECK = 'content'
    BUILDDIR = "$outputMsys/build"
    SRCDEST = "$outputMsys/sources"
    SRCPKGDEST = "$outputMsys/source-packages"
    LOGDEST = "$outputMsys/logs"
    PKGDEST = "$outputMsys/packages"
}
New-Item -ItemType Directory -Path $output | Out-Null
foreach ($directory in 'build', 'sources', 'source-packages', 'logs', 'packages') {
    New-Item -ItemType Directory -Path (Join-Path $output $directory) | Out-Null
}
$config = Join-Path $output 'makepkg-msys.conf'
[IO.File]::WriteAllText($config, $text, [Text.UTF8Encoding]::new($false))
$context = [ordered]@{
    Kind = 'msys-package-context'
    State = 'prepared-not-executed'
    Qualification = $binding
    BootstrapRoot = $msys
    Jobs = $Jobs
    Config = @{ Path = $config; SHA256 = (Get-FileHash -LiteralPath $config).Hash.ToLowerInvariant() }
    Environment = $environment
    MakepkgArguments = @('--config', (ConvertTo-MsysPath $config), '--check', '--cleanbuild', '--log', '--force', '--noconfirm')
    Scope = 'Prepared only from real qualification; does not run makepkg, install packages or qualify bootstrap drivers'
}
$context | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath "$output\context.json" -Encoding utf8
[pscustomobject]$context
