#requires -Version 7.3
param(
    [Parameter(Mandatory)]
    [string] $ProviderExport,
    [Parameter(Mandatory)]
    [string] $Bsdtar,
    [Parameter(Mandatory)]
    [string] $Git,
    [string] $OutputReport,
    [switch] $KeepWorkDirectory
)

$ErrorActionPreference = 'Stop'

function Get-Sha256([string] $Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-PeMachine([string] $Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64 -or $bytes[0] -ne 0x4d -or $bytes[1] -ne 0x5a) {
        throw "Not a PE image: $Path"
    }
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    if ($peOffset -lt 0 -or $peOffset + 6 -gt $bytes.Length) {
        throw "Malformed PE image: $Path"
    }
    [BitConverter]::ToUInt16($bytes, $peOffset + 4)
}

function Read-PkgInfo([string] $Package) {
    $text = & $Bsdtar -xOf $Package .PKGINFO | Out-String
    if ($LASTEXITCODE -ne 0) { throw "Could not read .PKGINFO from $Package" }
    $values = @{}
    foreach ($line in $text -split "`r?`n") {
        if ($line -notmatch '^([^=]+?)\s*=\s*(.*)$') { continue }
        $key = $Matches[1].Trim()
        if (-not $values.ContainsKey($key)) {
            $values[$key] = [Collections.Generic.List[string]]::new()
        }
        $values[$key].Add($Matches[2])
    }
    [ordered]@{
        name = if ($values.pkgname) { $values.pkgname[0] } else { $null }
        version = if ($values.pkgver) { $values.pkgver[0] } else { $null }
        architecture = if ($values.arch) { $values.arch[0] } else { $null }
        licenses = @($values.license)
        dependencies = @($values.depend)
    }
}

foreach ($path in $ProviderExport, $Bsdtar, $Git) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required input is missing: $path"
    }
}

$exportPath = (Resolve-Path -LiteralPath $ProviderExport).Path
$exportRoot = Split-Path $exportPath
$export = Get-Content -LiteralPath $exportPath -Raw | ConvertFrom-Json
if ($export.schema -ne 1 -or $export.status -notmatch 'verified|admitted|complete|exported') {
    throw "Provider export is not admitted: $ProviderExport"
}

$expected = [ordered]@{
    'mingw-w64-aarch64-git-lfs' = [ordered]@{
        version = '3.7.1-1'
        required = @(
            'mingwarm64/bin/git-lfs.exe',
            'mingwarm64/share/licenses/git-lfs/LICENSE.md'
        )
        dependencies = @('mingw-w64-aarch64-git=2.55.0.5')
    }
    'mingw-w64-aarch64-git-extra' = [ordered]@{
        version = '1.1.713.cd940aab6-1'
        required = @(
            'mingwarm64/bin/git-askpass.exe',
            'mingwarm64/bin/git-askyesno.exe',
            'mingwarm64/share/licenses/git-extra/LICENSE.txt'
        )
        dependencies = @('mingw-w64-aarch64-git=2.55.0.5', 'diffutils')
    }
}
$declared = @($export.packages)
if ($declared.Count -ne $expected.Count) {
    throw "Expected exactly $($expected.Count) helper packages, got $($declared.Count)"
}

$work = Join-Path ([IO.Path]::GetTempPath()) "git-helper-provider-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $work | Out-Null
$packageReports = [Collections.Generic.List[object]]::new()
try {
    foreach ($name in $expected.Keys) {
        $entry = @($declared | Where-Object name -CEQ $name)
        if ($entry.Count -ne 1) { throw "Expected one package declaration for $name" }
        $relative = [string] $entry[0].path
        if ([IO.Path]::IsPathRooted($relative) -or
            $relative.Replace('\', '/').Split('/') -contains '..') {
            throw "Unsafe package path for ${name}: $relative"
        }
        $package = Join-Path $exportRoot $relative.Replace('/', '\')
        if (-not (Test-Path -LiteralPath $package -PathType Leaf)) {
            throw "Package is missing: $package"
        }
        $actualHash = Get-Sha256 $package
        if ($actualHash -cne ([string] $entry[0].sha256).ToLowerInvariant()) {
            throw "Package hash mismatch for $name"
        }
        $metadata = Read-PkgInfo $package
        if ($metadata.name -cne $name -or
            $metadata.version -cne $expected[$name].version -or
            $metadata.architecture -cne 'any') {
            throw "Unexpected package metadata for ${name}: $($metadata | ConvertTo-Json -Compress)"
        }
        foreach ($dependency in $expected[$name].dependencies) {
            if ($dependency -cnotin $metadata.dependencies) {
                throw "$name is missing dependency $dependency"
            }
        }

        $stage = Join-Path $work $name
        New-Item -ItemType Directory -Path $stage | Out-Null
        & $Bsdtar -xf $package -C $stage
        if ($LASTEXITCODE -ne 0) { throw "Could not extract $package" }
        foreach ($relativePath in $expected[$name].required) {
            $path = Join-Path $stage $relativePath.Replace('/', '\')
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "$name is missing $relativePath"
            }
        }
        if ($name -ceq 'mingw-w64-aarch64-git-extra' -and
            (Test-Path -LiteralPath "$stage\mingwarm64\bin\git-credential-helper-selector.exe")) {
            throw 'git-extra contains the GCM-owned helper selector'
        }

        $peReports = [Collections.Generic.List[object]]::new()
        foreach ($pe in Get-ChildItem -LiteralPath "$stage\mingwarm64" -Recurse -File |
            Where-Object Extension -In '.exe', '.dll') {
            $machine = Get-PeMachine $pe.FullName
            if ($machine -ne 0xaa64) {
                throw "Non-ARM64 PE in ${name}: $($pe.FullName)"
            }
            $peReports.Add([ordered]@{
                path = [IO.Path]::GetRelativePath($stage, $pe.FullName).Replace('\', '/')
                sha256 = Get-Sha256 $pe.FullName
                bytes = $pe.Length
                machine = '0xaa64'
            })
        }
        $packageReports.Add([ordered]@{
            name = $name
            version = $metadata.version
            path = $relative.Replace('\', '/')
            sha256 = $actualHash
            licenses = $metadata.licenses
            dependencies = $metadata.dependencies
            native_pe = $peReports
        })
    }

    $forbidden = @(
        [Text.Encoding]::UTF8.GetBytes('C:\ap'),
        [Text.Encoding]::UTF8.GetBytes('C:/ap'),
        [Text.Encoding]::UTF8.GetBytes('/c/ap'),
        [Text.Encoding]::UTF8.GetBytes('.copilot'),
        [Text.Encoding]::UTF8.GetBytes('session-state'),
        [Text.Encoding]::UTF8.GetBytes('NON-FUNCTIONAL STUB'),
        [Text.Encoding]::UTF8.GetBytes('STUB-PLACEHOLDER'),
        [Text.Encoding]::UTF8.GetBytes('PIPELINE-TEST-DO-NOT-SHIP')
    )
    foreach ($file in Get-ChildItem -LiteralPath $work -Recurse -File) {
        if ($file.Name -in '.BUILDINFO', '.MTREE', '.PKGINFO') { continue }
        $bytes = [IO.File]::ReadAllBytes($file.FullName)
        $lower = [Text.Encoding]::Latin1.GetString($bytes).ToLowerInvariant()
        foreach ($markerBytes in $forbidden) {
            $marker = [Text.Encoding]::UTF8.GetString($markerBytes).ToLowerInvariant()
            if ($lower.Contains($marker)) {
                throw "Forbidden marker '$marker' in $($file.FullName)"
            }
        }
    }

    $lfs = Join-Path $work 'mingw-w64-aarch64-git-lfs\mingwarm64\bin\git-lfs.exe'
    $repo = Join-Path $work 'lfs-roundtrip'
    $privateHome = Join-Path $work 'home'
    New-Item -ItemType Directory -Path $repo, $privateHome | Out-Null
    $oldEnvironment = @{
        PATH = $env:PATH
        HOME = $env:HOME
        USERPROFILE = $env:USERPROFILE
        GIT_CONFIG_NOSYSTEM = $env:GIT_CONFIG_NOSYSTEM
        GIT_CONFIG_GLOBAL = $env:GIT_CONFIG_GLOBAL
    }
    try {
        $env:PATH = "$(Split-Path $lfs);$(Split-Path $Git);$($oldEnvironment.PATH)"
        $env:HOME = $privateHome
        $env:USERPROFILE = $privateHome
        $env:GIT_CONFIG_NOSYSTEM = '1'
        $env:GIT_CONFIG_GLOBAL = Join-Path $privateHome 'global.gitconfig'
        New-Item -ItemType File -Path $env:GIT_CONFIG_GLOBAL | Out-Null

        & $Git -C $repo init --quiet
        & $Git -C $repo config user.name 'ARM64 helper verifier'
        & $Git -C $repo config user.email 'arm64-helper-verifier@example.invalid'
        & $Git -C $repo lfs install --local --force | Out-Null
        & $Git -C $repo lfs track '*.bin' | Out-Null
        $content = [Text.Encoding]::UTF8.GetBytes(('native-arm64-lfs-roundtrip-' * 4096))
        [IO.File]::WriteAllBytes((Join-Path $repo 'sample.bin'), $content)
        $contentHash = Get-Sha256 (Join-Path $repo 'sample.bin')
        & $Git -C $repo add .gitattributes sample.bin
        $pointer = & $Git -C $repo show ':sample.bin' | Out-String
        if ($pointer -notmatch 'version https://git-lfs.github.com/spec/v1' -or
            $pointer -notmatch "oid sha256:$contentHash") {
            throw 'Git index does not contain the expected LFS pointer'
        }
        & $Git -C $repo commit --quiet -m 'Verify native LFS filter'
        $object = Join-Path "$repo\.git\lfs\objects" `
            ($contentHash.Substring(0, 2) + '\' + $contentHash.Substring(2, 2) + '\' + $contentHash)
        if (-not (Test-Path -LiteralPath $object -PathType Leaf)) {
            throw "LFS object is missing: $object"
        }
        Remove-Item -LiteralPath "$repo\sample.bin"
        & $Git -C $repo checkout -- sample.bin
        if ((Get-Sha256 "$repo\sample.bin") -cne $contentHash) {
            throw 'Git LFS smudge roundtrip changed the content'
        }
        & $Git -C $repo lfs fsck | Out-Null
        $roundtrip = [ordered]@{
            git = & $Git --version
            lfs = & $lfs version
            content_sha256 = $contentHash
            object_sha256 = Get-Sha256 $object
            network_used = $false
            global_config_isolated = $true
        }
    } finally {
        foreach ($name in $oldEnvironment.Keys) {
            if ($null -eq $oldEnvironment[$name]) {
                Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
            } else {
                Set-Item -Path "Env:$name" -Value $oldEnvironment[$name]
            }
        }
    }

    $report = [ordered]@{
        schema = 1
        status = 'verified-native-arm64-git-helper-provider'
        provider_export = [ordered]@{
            path = $exportPath
            sha256 = Get-Sha256 $exportPath
        }
        packages = $packageReports
        lfs_roundtrip = $roundtrip
        ownership_boundary = [ordered]@{
            git_credential_helper_selector_present = $false
            owner = 'mingw-w64-aarch64-git-credential-manager'
        }
    }
    if ($OutputReport) {
        $parent = Split-Path $OutputReport
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        $report | ConvertTo-Json -Depth 8 |
            Set-Content -LiteralPath $OutputReport -Encoding utf8
    }
    $report
} finally {
    if (-not $KeepWorkDirectory) {
        Remove-Item -LiteralPath $work -Recurse -Force
    }
}
