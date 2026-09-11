#requires -Version 7.3
param(
    [string[]] $PackageArchives,
    [string] $OutputDirectory,
    [switch] $Describe
)

$ErrorActionPreference = 'Stop'

function Get-PythonProviderPackageNames {
    @(
        'mingw-w64-aarch64-python',
        'mingw-w64-aarch64-bzip2',
        'mingw-w64-aarch64-expat',
        'mingw-w64-aarch64-gcc',
        'mingw-w64-aarch64-gettext',
        'mingw-w64-aarch64-libffi',
        'mingw-w64-aarch64-libiconv',
        'mingw-w64-aarch64-libsystre',
        'mingw-w64-aarch64-libtre',
        'mingw-w64-aarch64-mpdecimal',
        'mingw-w64-aarch64-ncurses',
        'mingw-w64-aarch64-openssl',
        'mingw-w64-aarch64-sqlite3',
        'mingw-w64-aarch64-tcl',
        'mingw-w64-aarch64-tk',
        'mingw-w64-aarch64-tzdata',
        'mingw-w64-aarch64-wineditline',
        'mingw-w64-aarch64-xz',
        'mingw-w64-aarch64-zlib'
    )
}

function Read-PacmanPackageMetadata([string] $Archive) {
    $requiredEntries = @('.PKGINFO', '.BUILDINFO', '.MTREE')
    $entries = @(& "$env:SystemRoot\System32\tar.exe" --zstd -tf $Archive)
    if ($LASTEXITCODE -ne 0) { throw "Cannot list package archive: $Archive" }
    foreach ($entry in $requiredEntries) {
        if ($entry -cnotin $entries) { throw "Package archive lacks $entry`: $Archive" }
    }

    $lines = @(& "$env:SystemRoot\System32\tar.exe" --zstd -xOf $Archive .PKGINFO)
    if ($LASTEXITCODE -ne 0) { throw "Cannot read .PKGINFO: $Archive" }
    $fields = @{}
    foreach ($line in $lines) {
        if ($line -notmatch '^([^#][^=]+?) = (.*)$') { continue }
        $key = $Matches[1].Trim()
        if (-not $fields.ContainsKey($key)) {
            $fields[$key] = [Collections.Generic.List[string]]::new()
        }
        $fields[$key].Add($Matches[2])
    }
    foreach ($required in 'pkgname', 'pkgver', 'arch') {
        if (-not $fields.ContainsKey($required) -or $fields[$required].Count -ne 1) {
            throw "Package archive has invalid $required metadata: $Archive"
        }
    }

    [ordered]@{
        packageName = $fields.pkgname[0]
        packageVersion = $fields.pkgver[0]
        architecture = $fields.arch[0]
        depends = if ($fields.ContainsKey('depend')) { @($fields.depend) } else { @() }
        provides = if ($fields.ContainsKey('provides')) { @($fields.provides) } else { @() }
        conflicts = if ($fields.ContainsKey('conflict')) { @($fields.conflict) } else { @() }
        replaces = if ($fields.ContainsKey('replaces')) { @($fields.replaces) } else { @() }
        fileCount = @($entries | Where-Object {
            $_ -and $_ -cnotin $requiredEntries -and -not $_.EndsWith('/')
        }).Count
    }
}

function Invoke-PythonProviderExport {
    if (-not $PackageArchives -or [string]::IsNullOrWhiteSpace($OutputDirectory)) {
        throw 'PackageArchives and OutputDirectory are required.'
    }
    if (Test-Path -LiteralPath $OutputDirectory) {
        throw 'Python provider export output must be new.'
    }

    $expectedNames = @(Get-PythonProviderPackageNames)
    $metadata = [Collections.Generic.List[object]]::new()
    foreach ($archive in $PackageArchives) {
        if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
            throw "Package archive does not exist: $archive"
        }
        $item = Get-Item -LiteralPath $archive
        $package = Read-PacmanPackageMetadata $item.FullName
        if ($package.packageName -cnotin $expectedNames) {
            throw "Unexpected package in Python provider closure: $($package.packageName)"
        }
        $metadata.Add([pscustomobject]@{
            source = $item.FullName
            file = $item.Name
            bytes = $item.Length
            sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            metadata = $package
        })
    }

    $actualNames = @($metadata.metadata.packageName)
    if ($actualNames.Count -ne ($actualNames | Sort-Object -Unique).Count) {
        throw 'Python provider closure contains duplicate package identities.'
    }
    $missing = @($expectedNames | Where-Object { $_ -cnotin $actualNames })
    if ($missing.Count) { throw "Python provider closure is incomplete: $($missing -join ', ')" }
    if ($actualNames.Count -ne $expectedNames.Count) {
        throw "Python provider closure must contain exactly $($expectedNames.Count) packages."
    }

    $python = $metadata | Where-Object { $_.metadata.packageName -ceq 'mingw-w64-aarch64-python' }
    if ($python.metadata.packageVersion -cne '3.12.9-3' -or
        $python.sha256 -cne '1d10d98cf681ba8fb9d50853b75520b4f525205ba744e851b77933635c95333e') {
        throw 'Python package does not match the qualified 3.12.9-3 provider.'
    }

    New-Item -ItemType Directory -Path "$OutputDirectory\packages" | Out-Null
    $packages = foreach ($item in $metadata | Sort-Object { $_.metadata.packageName }) {
        $destination = Join-Path "$OutputDirectory\packages" $item.file
        Copy-Item -LiteralPath $item.source -Destination $destination
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -cne $item.sha256) {
            throw "Copied package hash mismatch: $($item.file)"
        }
        [ordered]@{
            name = $item.metadata.packageName
            path = "packages/$($item.file)"
            packageName = $item.metadata.packageName
            packageVersion = $item.metadata.packageVersion
            architecture = $item.metadata.architecture
            archive = "packages/$($item.file)"
            bytes = $item.bytes
            sha256 = $item.sha256
            depends = $item.metadata.depends
            provides = $item.metadata.provides
            conflicts = $item.metadata.conflicts
            replaces = $item.metadata.replaces
            fileCount = $item.metadata.fileCount
            hasPkgInfo = $true
            hasBuildInfo = $true
            hasMtree = $true
            reusedUnchanged = $true
        }
    }

    $receipt = [ordered]@{
        schema = 1
        status = 'admitted-complete-exported-verified-native-python-provider'
        generatedUtc = [DateTime]::UtcNow.ToString('o')
        target = 'MINGWARM64/aarch64-w64-mingw32'
        pinnedRecipe = [ordered]@{
            repository = 'Windows-on-ARM-Experiments/MINGW-packages'
            commit = 'f34f6df66a0a06157dd1b09dd1d1e026ce7c903c'
            pythonVersion = '3.12.9-3'
            pythonRecipeSha256 = '155d256d8346498fb2afa881c13b9306f92b2a8b4a4d063ce589c68c99de34b1'
        }
        maintainedPatch = [ordered]@{
            path = 'patches/runtime-providers/0005-python-mingw-pgo-link.patch'
            sha256 = '3d0c3282865dba72cd1dc83276cc09e909524949101f9af41efdc723d52eb3fd'
        }
        packages = @($packages)
        packageCount = @($packages).Count
        policy = @(
            'All package archives are copied byte-for-byte from qualified build or admitted provider outputs.',
            'No package identity, dependency, provides, conflicts, or replaces metadata is rewritten.',
            'The export is a dependency closure for the MINGWARM64 Python provider, not an omnibus virtual provider.'
        )
    }
    $receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$OutputDirectory\export.json" -Encoding utf8
    $receipt
}

if ($Describe) {
    Get-PythonProviderPackageNames | ConvertTo-Json
} elseif ($MyInvocation.InvocationName -ne '.') {
    Invoke-PythonProviderExport
}
