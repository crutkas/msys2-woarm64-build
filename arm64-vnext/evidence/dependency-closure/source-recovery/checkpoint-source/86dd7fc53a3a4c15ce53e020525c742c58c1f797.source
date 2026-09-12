#requires -Version 7.3

function New-PackageRuntimeSnapshot([string] $SourceRoot, [string] $Destination) {
    $source = (Resolve-Path -LiteralPath $SourceRoot).ProviderPath.TrimEnd('\')
    $destinationRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
    if (Test-Path -LiteralPath $destinationRoot) { throw 'Pipeline snapshot destination must be new.' }
    if ($destinationRoot.StartsWith("$source\", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Pipeline snapshot must be outside its source checkout.'
    }
    $revision = & git -C $source rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $revision -cnotmatch '^[0-9a-f]{40}$') { throw 'Cannot identify pipeline source revision.' }
    $files = @(
        Get-Item -LiteralPath (Join-Path $source 'config.sh')
        Get-ChildItem -LiteralPath (Join-Path $source '.github\scripts') -Recurse -File |
            Where-Object { $_.Extension -ne '.pyc' -and $_.FullName -notmatch '\\__pycache__\\' }
        Get-ChildItem -LiteralPath (Join-Path $source 'patches\makepkg') -File
    ) | ForEach-Object {
        @{ Path = $_.FullName.Substring($source.Length + 1); SHA256 = (Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant() }
    }
    foreach ($entry in $files) {
        $path = Join-Path $destinationRoot $entry.Path
        New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $source $entry.Path) -Destination $path
        if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -cne $entry.SHA256) {
            throw "Pipeline runtime changed while being copied: $($entry.Path)"
        }
    }
    [pscustomobject]@{Root=$destinationRoot;Revision=$revision;Files=@($files)}
}

function Assert-PackageRuntimeSnapshot($Snapshot) {
    foreach ($entry in $Snapshot.Files) {
        if ((Get-FileHash -LiteralPath (Join-Path $Snapshot.Root $entry.Path)).Hash.ToLowerInvariant() -cne $entry.SHA256) {
            throw "Invocation pipeline runtime changed: $($entry.Path)"
        }

    }
}

function Set-NativePackageJob($StartInfo, $Python, [string] $RuntimeRoot, [string] $OutputRoot, [int] $TimeoutSeconds) {
    $command = @($StartInfo.FileName) + @($StartInfo.ArgumentList)
    $StartInfo.FileName = $Python.Path
    $StartInfo.ArgumentList.Clear()
    foreach ($argument in @(
        '-I', "$RuntimeRoot\.github\scripts\native-job.py",
        '--cwd', $StartInfo.WorkingDirectory, '--target-root', "$OutputRoot\build",
        '--relay-records', "$OutputRoot\native-exits", '--log', "$OutputRoot\native-job.log",
        '--result', "$OutputRoot\native-job.json", '--timeout', "$TimeoutSeconds", '--'
    ) + $command) { $StartInfo.ArgumentList.Add($argument) }
}

function Read-NativePackageJob([string] $OutputRoot) {
    $path = Join-Path $OutputRoot 'native-job.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Native job monitor did not produce a result.' }
    $result = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    if ($result.passed -ne $true -and (Test-Path -LiteralPath "$OutputRoot\packages")) {
        $packages = @(Get-ChildItem -LiteralPath "$OutputRoot\packages" -File -Filter '*.pkg.tar.*')
        if ($packages.Count) {
            New-Item -ItemType Directory -Path "$OutputRoot\rejected-packages" | Out-Null
            foreach ($package in $packages) { Move-Item -LiteralPath $package.FullName -Destination "$OutputRoot\rejected-packages" }
        }
    }
    $result
}
