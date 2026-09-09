#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $OutputDirectory,
    [string] $Stage = 'C:\ag-readline-e138-01\ncurses-static-cxx-01\stage',
    [string] $Inventory = 'C:\ag-readline-e138-01\ncurses-static-cxx-01\stage.inventory.json',
    [string] $Handoff = 'C:\ag-readline-e138-01\ncurses-handoff-01\handoff.json',
    [string] $BootstrapRoot = 'C:\ag-bash-e138-01\host-bootstrap-02\msys64',
    [string] $MakepkgConfig = 'C:\ap06-2160\native-msys-zlib-package-01\invocation\makepkg-msys.conf'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$inventoryPin = '8440b2b509b2a997a9db05474dff64a875e851a2c5b229f22d35fd430cda5b8a'
$handoffPin = 'eabe9fb4635cf4698c88c895bd4a138eb005efb7c789af1fbcfe908642c47003'

function Get-Sha256([string] $Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Pin([string] $Path, [string] $Expected, [string] $Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label is missing: $Path"
    }
    $actual = Get-Sha256 $Path
    if ($actual -cne $Expected) {
        throw "$Label changed: expected $Expected, got $actual"
    }
}

$output = [IO.Path]::GetFullPath($OutputDirectory).TrimEnd('\')
if (Test-Path -LiteralPath $output) {
    throw "Output must be new: $output"
}
Assert-Pin $Inventory $inventoryPin 'Qualified ncurses inventory'
Assert-Pin $Handoff $handoffPin 'Qualified ncurses handoff'
if (-not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\bash.exe" -PathType Leaf) -or
    -not (Test-Path -LiteralPath "$BootstrapRoot\usr\bin\makepkg" -PathType Leaf)) {
    throw "Packaging bootstrap is incomplete: $BootstrapRoot"
}

$inventoryData = Get-Content -Raw -LiteralPath $Inventory | ConvertFrom-Json -AsHashtable
$handoffData = Get-Content -Raw -LiteralPath $Handoff | ConvertFrom-Json -AsHashtable
if ($handoffData.get_Item('status') -cne 'native-stage-upstream-static-shared-api-pty-dll-proofs-package-link-gated' -or
    $handoffData.get_Item('runtime_sha256') -cne '1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16') {
    throw 'The supplied ncurses handoff is not the pinned package-link-gated result.'
}
$gate = $handoffData.get_Item('package_link_gate')
if ($gate.get_Item('path') -cne 'usr/lib/terminfo' -or
    $gate.get_Item('required_target') -cne '../share/terminfo' -or
    $gate.get_Item('qualified_as_symlink') -ne $false) {
    throw 'The ncurses package-link gate changed.'
}

$sourceFiles = @($inventoryData.get_Item('files').GetEnumerator() | Sort-Object Key)
if ($sourceFiles.Count -ne 6833) {
    throw "Qualified ncurses inventory changed file count: $($sourceFiles.Count)"
}
foreach ($entry in $sourceFiles) {
    $path = Join-Path $Stage $entry.Key.Replace('/', '\')
    Assert-Pin $path $entry.Value.get_Item('sha256') "Qualified ncurses payload $($entry.Key)"
}

New-Item -ItemType Directory -Path $output, "$output\recipe", "$output\packages" | Out-Null
Copy-Item -LiteralPath $Stage -Destination "$output\recipe\payload" -Recurse
$hashLines = $sourceFiles | ForEach-Object {
    "$($_.Value.get_Item('sha256'))  payload/$($_.Key)"
}
[IO.File]::WriteAllText(
    "$output\recipe\payload-files.sha256",
    ($hashLines -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)
& "$env:SystemRoot\System32\tar.exe" -cf "$output\recipe\payload.tar" -C "$output\recipe" payload
if ($LASTEXITCODE) {
    throw 'Could not archive the qualified ncurses payload.'
}

$template = Join-Path $PSScriptRoot '..\native-packaging\ncurses\PKGBUILD.in'
$recipe = [IO.File]::ReadAllText($template).Replace("`r`n", "`n")
$recipe = $recipe.Replace('@PAYLOAD_SHA256@', (Get-Sha256 "$output\recipe\payload.tar"))
$recipe = $recipe.Replace('@FILES_SHA256@', (Get-Sha256 "$output\recipe\payload-files.sha256"))
[IO.File]::WriteAllText("$output\recipe\PKGBUILD", $recipe, [Text.UTF8Encoding]::new($false))

$start = [Diagnostics.ProcessStartInfo]::new("$BootstrapRoot\usr\bin\bash.exe")
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.WorkingDirectory = "$output\recipe"
$start.Environment['INTAKE_ROOT'] = $output
$start.Environment['INTAKE_CONFIG'] = [IO.Path]::GetFullPath($MakepkgConfig)
$start.Environment['MSYS'] = 'winsymlinks:sys'
$start.ArgumentList.Add('--noprofile')
$start.ArgumentList.Add('--norc')
$start.ArgumentList.Add('-lc')
$start.ArgumentList.Add(@'
set -euo pipefail
export PATH=/usr/bin
root=$(cygpath -u "$INTAKE_ROOT")
config=$(cygpath -u "$INTAKE_CONFIG")
cd "$root/recipe"
export PKGDEST="$root/packages"
export SRCDEST="$root/sources"
export SRCPKGDEST="$root/source-packages"
export LOGDEST="$root/logs"
export BUILDDIR="$root/build"
export CCACHE_DIR="$root/ccache"
makepkg --config "$config" --check --cleanbuild --log --force --noconfirm
'@)
$stdout = [IO.File]::Create("$output\makepkg.stdout.log")
$stderr = [IO.File]::Create("$output\makepkg.stderr.log")
try {
    $process = [Diagnostics.Process]::Start($start)
    try {
        $copyOut = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $copyErr = $process.StandardError.BaseStream.CopyToAsync($stderr)
        $process.WaitForExit()
        $null = $copyOut.GetAwaiter().GetResult()
        $null = $copyErr.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "makepkg failed with exit code $($process.ExitCode)"
        }
    } finally {
        $process.Dispose()
    }
} finally {
    $stdout.Dispose()
    $stderr.Dispose()
}

$packages = @(Get-ChildItem -LiteralPath "$output\packages" -File -Filter '*.pkg.tar.zst' | Sort-Object Name)
if ($packages.Count -ne 2) {
    throw "Expected two ncurses package archives, found $($packages.Count)."
}
$runtimePackage = $packages | Where-Object Name -eq 'ncurses-6.6-2-aarch64.pkg.tar.zst'
if ($null -eq $runtimePackage) {
    throw 'The ncurses runtime package archive is missing.'
}
$linkCheck = [Diagnostics.ProcessStartInfo]::new("$BootstrapRoot\usr\bin\bash.exe")
$linkCheck.UseShellExecute = $false
$linkCheck.Environment['ARCHIVE_PATH'] = $runtimePackage.FullName
$linkCheck.ArgumentList.Add('--noprofile')
$linkCheck.ArgumentList.Add('--norc')
$linkCheck.ArgumentList.Add('-lc')
$linkCheck.ArgumentList.Add(@'
set -euo pipefail
export PATH=/usr/bin
archive=$(cygpath -u "$ARCHIVE_PATH")
entry=$(bsdtar -tvf "$archive" usr/lib/terminfo)
[[ "$entry" == l*" usr/lib/terminfo -> ../share/terminfo" ]]
'@)
$linkProcess = [Diagnostics.Process]::Start($linkCheck)
try {
    $linkProcess.WaitForExit()
    if ($linkProcess.ExitCode -ne 0) {
        throw 'The ncurses package did not preserve usr/lib/terminfo as a relative symlink.'
    }
} finally {
    $linkProcess.Dispose()
}
$exports = foreach ($package in $packages) {
    $name = ($package.Name -replace '-6\.6-2-aarch64\.pkg\.tar\.zst$', '')
    if ($name -cnotin @('ncurses', 'ncurses-devel')) {
        throw "Unexpected ncurses package archive: $($package.Name)"
    }
    [ordered]@{
        name = $name
        path = "packages/$($package.Name)"
        sha256 = Get-Sha256 $package.FullName
    }
}

[ordered]@{
    schema = 1
    status = 'admitted-qualified-native-msys-ncurses-exported'
    packages = @($exports)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$output\export.json" -Encoding utf8

[ordered]@{
    schema = 1
    status = 'qualified-native-msys-ncurses-packaged'
    source = [ordered]@{
        handoff = [ordered]@{ path = [IO.Path]::GetFullPath($Handoff); sha256 = $handoffPin }
        inventory = [ordered]@{ path = [IO.Path]::GetFullPath($Inventory); sha256 = $inventoryPin }
        recipe_version = '6.6-2'
    }
    packaging_resolution = [ordered]@{
        path = 'usr/lib/terminfo'
        type = 'symlink'
        target = '../share/terminfo'
        source_directory_excluded_from_devel = $true
    }
    packages = @($exports)
    limitations = @(
        'Package metadata resolves the declared terminfo symlink gate without changing library bytes.',
        'Stage was qualified against runtime 1bdf95fed1454f58531c704b7c2b65ac6051c9dace56220aab5d8399c6b8cd16, not d70cfb46ed6bfa643a6ab557a71008e86043d8a04e5ce2d33549e4e95a49117d.',
        'No downstream Bash, SQLite, Heimdal, OpenSSH, or full shared-distribution admission is claimed.'
    )
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "$output\handoff.json" -Encoding utf8

[pscustomobject]@{
    Export = "$output\export.json"
    ExportSHA256 = Get-Sha256 "$output\export.json"
    Handoff = "$output\handoff.json"
    HandoffSHA256 = Get-Sha256 "$output\handoff.json"
    Packages = $packages.Count
}
