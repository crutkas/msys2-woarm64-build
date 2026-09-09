#requires -Version 7.3
param(
    [Parameter(Mandatory)]
    [string] $GitLfsPackage,
    [Parameter(Mandatory)]
    [string] $GitLfsSignature,
    [Parameter(Mandatory)]
    [string] $GitExtraPackage,
    [Parameter(Mandatory)]
    [string] $GitExtraSignature,
    [Parameter(Mandatory)]
    [string] $GitLfsLicense,
    [Parameter(Mandatory)]
    [string] $BuildExtraLicense,
    [Parameter(Mandatory)]
    [string] $BuildExtraSourceRoot,
    [Parameter(Mandatory)]
    [string] $BuildExtraInventory,
    [Parameter(Mandatory)]
    [string] $GitExtraBuildDirectory,
    [Parameter(Mandatory)]
    [string] $GitExtraBuildLog,
    [Parameter(Mandatory)]
    [string] $GitExtraGcc,
    [Parameter(Mandatory)]
    [string] $GitExtraGxx,
    [Parameter(Mandatory)]
    [string] $GitExtraWindres,
    [Parameter(Mandatory)]
    [string] $OutputDirectory,
    [Parameter(Mandatory)]
    [string] $Bsdtar,
    [Parameter(Mandatory)]
    [string] $Gpg,
    [Parameter(Mandatory)]
    [string] $GpgHome
)

$ErrorActionPreference = 'Stop'

$SigningFingerprint = '91883E11E83DC29D14104DB4EDD44359093056EE'
$BuildExtraCommit = '21d6ed86c38d28e89c950c9e1e349b6edefd1afb'
$DistributionContractSha256 = '8576a0499b93a7ddbc0f7c4ee3d9f44f5183b6c44f635561d8f31a622f350405'
$GitLfsSourceCommit = 'a94294cc43168621a7d9609bebef62dbbd2804dd'
$GitExtraToolHashes = @{
    Gcc = 'cefca4ee864efbc185d29c78fac8c64135233a3bbdaef93ec6c92d4bb6418f7f'
    Gxx = '5d9f0b601c45e6d72e92b98625c2aad1a55864a485bb8fcb04475403c3b5ee80'
    Windres = '1001c87661a820f94c8ca99df86e95ecc66722e5db1504350c20286eab30cbcd'
}
$PinnedInputs = @{
    GitLfsPackage = '43f98ba2bb123e12c87cb0982df5d072237189110415ebf9e1148746ec93deb8'
    GitLfsSignature = '2e398ca01dceac8797ff6d4c0ac8ac2d112d3e8d6809e92c24c198e4674a7f4d'
    GitExtraPackage = '320b8456d299995d67e452a10c2f930993fc7169170564fb93c6ea022bdaab90'
    GitExtraSignature = '39047cf2016313d570ed41daa1757749218046ec8c731ee0ed9de30d71148107'
    GitLfsLicense = '4fae9062ab5cdd5fb15486b728534d8aded8b4ae9d84b6d66a956f5162c366b6'
    BuildExtraLicense = '5b2198d1645f767585e8a88ac0499b04472164c0d2da22e75ecf97ef443ab32e'
}

function Get-Sha256([string] $Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function ConvertTo-MsysPath([string] $Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "GPG home must be an absolute Windows path: $Path"
    }
    "/$($Matches[1].ToLowerInvariant())/$($Matches[2].Replace('\', '/'))"
}

function Assert-FileHash([string] $Path, [string] $Expected, [string] $Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing ${Label}: $Path"
    }
    $actual = Get-Sha256 $Path
    if ($actual -cne $Expected) {
        throw "$Label hash mismatch: expected $Expected, got $actual"
    }
}

function Assert-PackageSignature([string] $Package, [string] $Signature) {
    $status = & $Gpg --homedir (ConvertTo-MsysPath $GpgHome) --batch --status-fd 1 `
        --verify $Signature $Package 2>&1 |
        Out-String
    if ($LASTEXITCODE -ne 0 -or
        $status -notmatch "\[GNUPG:\] VALIDSIG $SigningFingerprint ") {
        throw "Detached signature verification failed for $Package`n$status"
    }
}

function Assert-BuildExtraSource {
    Assert-FileHash $BuildExtraInventory `
        'e599aee160244bcc5367be49e2bf4b60a67c5d8ebc69282f553d545712cd1f76' `
        'build-extra source inventory'
    $inventory = Get-Content -LiteralPath $BuildExtraInventory -Raw | ConvertFrom-Json -AsHashtable
    if ($inventory.source.version -cne $BuildExtraCommit) {
        throw "Unexpected build-extra source revision: $($inventory.source.version)"
    }
    foreach ($entry in $inventory.files.GetEnumerator()) {
        if (-not $entry.Key.StartsWith('git-extra/', [StringComparison]::Ordinal)) {
            continue
        }
        $relative = $entry.Key.Substring('git-extra/'.Length).Replace('/', '\')
        Assert-FileHash (Join-Path $BuildExtraSourceRoot $relative) `
            $entry.Value.sha256 "build-extra source $relative"
    }
}

function Get-PackageMetadata([string] $Package) {
    $text = & $Bsdtar -xOf $Package .PKGINFO | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read .PKGINFO from $Package"
    }
    $values = @{}
    foreach ($line in $text -split "`r?`n") {
        if ($line -notmatch '^([^=]+?)\s*=\s*(.*)$') { continue }
        $key = $Matches[1].Trim()
        if (-not $values.ContainsKey($key)) {
            $values[$key] = [Collections.Generic.List[string]]::new()
        }
        $values[$key].Add($Matches[2])
    }
    if (-not $values.pkgname -or -not $values.pkgver) {
        throw "Incomplete .PKGINFO in $Package"
    }
    [ordered]@{
        Name = $values.pkgname[0]
        Version = $values.pkgver[0]
        BuildDate = if ($values.builddate) { $values.builddate[0] } else { '0' }
    }
}

function ConvertTo-RelativePath([string] $Root, [string] $Path) {
    [IO.Path]::GetRelativePath($Root, $Path).Replace('\', '/')
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

function Set-AdaptedText([string] $Stage) {
    $binaryExtensions = @('.exe', '.dll', '.ico', '.gz')
    foreach ($file in Get-ChildItem -LiteralPath $Stage -Recurse -File) {
        if ($file.Name -in '.PKGINFO', '.BUILDINFO', '.MTREE' -or
            $file.Extension.ToLowerInvariant() -in $binaryExtensions) {
            continue
        }
        $bytes = [IO.File]::ReadAllBytes($file.FullName)
        if ($bytes -contains 0) { continue }
        $text = [Text.Encoding]::UTF8.GetString($bytes)
        $updated = $text.Replace('mingw-w64-clang-aarch64', 'mingw-w64-aarch64').
            Replace('CLANGARM64', 'MINGWARM64').
            Replace('clangarm64', 'mingwarm64')
        if ($updated -cne $text) {
            [IO.File]::WriteAllText(
                $file.FullName,
                $updated,
                [Text.UTF8Encoding]::new($false)
            )
        }
    }
}

function New-Mtree([string] $Stage, [string] $Output) {
    $lines = [Collections.Generic.List[string]]::new()
    $lines.Add('#mtree')
    $lines.Add('/set type=file uid=0 gid=0 mode=644')
    foreach ($directory in Get-ChildItem -LiteralPath $Stage -Recurse -Directory |
        Sort-Object FullName) {
        $relative = ConvertTo-RelativePath $Stage $directory.FullName
        $lines.Add("./$relative type=dir mode=755")
    }
    foreach ($file in Get-ChildItem -LiteralPath $Stage -Recurse -File |
        Where-Object Name -NotIn '.BUILDINFO', '.MTREE', '.PKGINFO' |
        Sort-Object FullName) {
        $relative = ConvertTo-RelativePath $Stage $file.FullName
        $hash = Get-Sha256 $file.FullName
        $mode = if ($file.Extension -eq '.exe' -or
            $relative -match '(^|/)(bin|profile\.d|post-install|lint_package)/') {
            '755'
        } else {
            '644'
        }
        $lines.Add("./$relative size=$($file.Length) sha256digest=$hash mode=$mode")
    }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($lines -join "`n") + "`n")
    $stream = [IO.File]::Create($Output)
    try {
        $gzip = [IO.Compression.GZipStream]::new(
            $stream,
            [IO.Compression.CompressionLevel]::SmallestSize
        )
        try { $gzip.Write($bytes) } finally { $gzip.Dispose() }
    } finally {
        $stream.Dispose()
    }
}

function Write-PackageMetadata(
    [string] $Stage,
    [string] $Name,
    [string] $Version,
    [string] $Description,
    [string] $Url,
    [string[]] $Licenses,
    [string[]] $Depends,
    [string[]] $Provides,
    [string[]] $Conflicts,
    [string] $BuildDate
) {
    $size = (Get-ChildItem -LiteralPath $Stage -Recurse -File |
        Where-Object Name -NotIn '.BUILDINFO', '.MTREE', '.PKGINFO' |
        Measure-Object Length -Sum).Sum
    $pkginfo = [Collections.Generic.List[string]]::new()
    $pkginfo.Add('# Generated by export-git-helper-provider.ps1')
    $pkginfo.Add("pkgname = $Name")
    $pkginfo.Add("pkgbase = $($Name -replace '-aarch64-', '-')")
    $pkginfo.Add('xdata = pkgtype=pkg')
    $pkginfo.Add("pkgver = $Version")
    $pkginfo.Add("pkgdesc = $Description")
    $pkginfo.Add("url = $Url")
    $pkginfo.Add("builddate = $BuildDate")
    $pkginfo.Add('packager = Windows on ARM native helper provider')
    $pkginfo.Add("size = $size")
    $pkginfo.Add('arch = any')
    foreach ($license in $Licenses) { $pkginfo.Add("license = $license") }
    foreach ($dependency in $Depends) { $pkginfo.Add("depend = $dependency") }
    foreach ($provider in $Provides) { $pkginfo.Add("provides = $provider") }
    foreach ($conflict in $Conflicts) { $pkginfo.Add("conflict = $conflict") }
    [IO.File]::WriteAllText(
        "$Stage\.PKGINFO",
        ($pkginfo -join "`n") + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    $buildInfo = @(
        'format = 2',
        "pkgname = $Name",
        "pkgbase = $($Name -replace '-aarch64-', '-')",
        "pkgver = $Version",
        'pkgarch = any',
        'packager = Windows on ARM native helper provider',
        "builddate = $BuildDate",
        'builddir = /build/git-helper-provider',
        'buildtool = makepkg-compatible-provider-export',
        'buildtoolver = 1',
        'buildenv = !distcc',
        'buildenv = !ccache'
    )
    [IO.File]::WriteAllText(
        "$Stage\.BUILDINFO",
        ($buildInfo -join "`n") + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    New-Mtree $Stage "$Stage\.MTREE"
}

function New-AdaptedPackage(
    [string] $SourcePackage,
    [string] $ExpectedSourceName,
    [string] $ExpectedVersion,
    [string] $Name,
    [string] $Description,
    [string] $Url,
    [string[]] $Licenses,
    [string[]] $Depends,
    [string[]] $Provides,
    [string[]] $Conflicts,
    [scriptblock] $Adapt
) {
    $metadata = Get-PackageMetadata $SourcePackage
    if ($metadata.Name -cne $ExpectedSourceName -or
        $metadata.Version -cne $ExpectedVersion) {
        throw "Unexpected source package identity: $($metadata.Name) $($metadata.Version)"
    }
    $stage = Join-Path $OutputDirectory "stage-$Name"
    New-Item -ItemType Directory -Path $stage | Out-Null
    & $Bsdtar -xf $SourcePackage -C $stage
    if ($LASTEXITCODE -ne 0) { throw "Could not extract $SourcePackage" }
    Remove-Item -LiteralPath "$stage\.PKGINFO", "$stage\.BUILDINFO", "$stage\.MTREE" -Force
    Move-Item -LiteralPath "$stage\clangarm64" -Destination "$stage\mingwarm64"
    & $Adapt $stage
    Set-AdaptedText $stage
    foreach ($pe in Get-ChildItem -LiteralPath "$stage\mingwarm64" -Recurse -File |
        Where-Object Extension -In '.exe', '.dll') {
        $machine = Get-PeMachine $pe.FullName
        if ($machine -ne 0xaa64) {
            throw "Non-ARM64 native payload: $($pe.FullName) (0x$('{0:x4}' -f $machine))"
        }
    }
    Write-PackageMetadata $stage $Name $ExpectedVersion $Description $Url `
        $Licenses $Depends $Provides $Conflicts $metadata.BuildDate
    $timestamp = [DateTimeOffset]::FromUnixTimeSeconds(
        [long] $metadata.BuildDate
    ).UtcDateTime
    foreach ($item in Get-ChildItem -LiteralPath $stage -Recurse -Force) {
        $item.LastWriteTimeUtc = $timestamp
    }
    $archive = Join-Path "$OutputDirectory\packages" "$Name-$ExpectedVersion-any.pkg.tar.zst"
    $entries = @(Get-ChildItem -LiteralPath $stage -Force | Sort-Object Name |
        ForEach-Object Name)
    & $Bsdtar --zstd -cf $archive -C $stage @entries
    if ($LASTEXITCODE -ne 0) { throw "Could not create $archive" }
    $result = [ordered]@{
        name = $Name
        path = "packages/$([IO.Path]::GetFileName($archive))"
        sha256 = Get-Sha256 $archive
        version = $ExpectedVersion
        source_package = [ordered]@{
            name = $metadata.Name
            path = "sources/$([IO.Path]::GetFileName($SourcePackage))"
            sha256 = Get-Sha256 $SourcePackage
        }
    }
    Remove-Item -LiteralPath $stage -Recurse
    $result
}

if (Test-Path -LiteralPath $OutputDirectory) {
    throw "Output directory must be new: $OutputDirectory"
}
foreach ($tool in $Bsdtar, $Gpg) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Required tool is missing: $tool"
    }
}
if (-not (Test-Path -LiteralPath $GpgHome -PathType Container)) {
    throw "Private GPG home is missing: $GpgHome"
}

Assert-FileHash $GitLfsPackage $PinnedInputs.GitLfsPackage 'Git LFS package'
Assert-FileHash $GitLfsSignature $PinnedInputs.GitLfsSignature 'Git LFS signature'
Assert-FileHash $GitExtraPackage $PinnedInputs.GitExtraPackage 'git-extra package'
Assert-FileHash $GitExtraSignature $PinnedInputs.GitExtraSignature 'git-extra signature'
Assert-FileHash $GitLfsLicense $PinnedInputs.GitLfsLicense 'Git LFS license'
Assert-FileHash $BuildExtraLicense $PinnedInputs.BuildExtraLicense 'build-extra license'
Assert-FileHash $GitExtraGcc $GitExtraToolHashes.Gcc 'git-extra GCC'
Assert-FileHash $GitExtraGxx $GitExtraToolHashes.Gxx 'git-extra G++'
Assert-FileHash $GitExtraWindres $GitExtraToolHashes.Windres 'git-extra windres'
if (-not (Test-Path -LiteralPath $GitExtraBuildLog -PathType Leaf)) {
    throw "Missing git-extra build log: $GitExtraBuildLog"
}
Assert-BuildExtraSource
Assert-PackageSignature $GitLfsPackage $GitLfsSignature
Assert-PackageSignature $GitExtraPackage $GitExtraSignature

New-Item -ItemType Directory -Path "$OutputDirectory\packages", "$OutputDirectory\sources" |
    Out-Null
foreach ($source in $GitLfsPackage, $GitLfsSignature, $GitExtraPackage, $GitExtraSignature) {
    Copy-Item -LiteralPath $source -Destination "$OutputDirectory\sources"
}
$packages = [Collections.Generic.List[object]]::new()
$packages.Add((New-AdaptedPackage `
    $GitLfsPackage `
    'mingw-w64-clang-aarch64-git-lfs' `
    '3.7.1-1' `
    'mingw-w64-aarch64-git-lfs' `
    'Git LFS 3.7.1 for the native ARM64 Git for Windows distribution' `
    'https://github.com/git-lfs/git-lfs' `
    @('MIT') `
    @('mingw-w64-aarch64-git=2.55.0.5') `
    @() `
    @() `
    {
        param($stage)
        $license = "$stage\mingwarm64\share\licenses\git-lfs\LICENSE.md"
        New-Item -ItemType Directory -Path (Split-Path $license) -Force | Out-Null
        Copy-Item -LiteralPath $GitLfsLicense -Destination $license
    }))
$packages.Add((New-AdaptedPackage `
    $GitExtraPackage `
    'mingw-w64-clang-aarch64-git-extra' `
    '1.1.713.cd940aab6-1' `
    'mingw-w64-aarch64-git-extra' `
    'Git for Windows extra files for the native ARM64 distribution' `
    'https://github.com/git-for-windows/build-extra' `
    @('GPL-2.0-only') `
    @('mingw-w64-aarch64-git=2.55.0.5', 'diffutils') `
    @('git-extra') `
    @('git-extra', 'mingw-w64-clang-aarch64-git-extra') `
    {
        param($stage)
        # GCM owns the selector in the full-release contract.
        Remove-Item -LiteralPath "$stage\mingwarm64\bin\git-credential-helper-selector.exe"
        foreach ($name in @(
            'blocked-file-util.exe',
            'create-shortcut.exe',
            'git-askpass.exe',
            'git-askyesno.exe',
            'proxy-lookup.exe',
            'WhoUses.exe'
        )) {
            $source = Join-Path $GitExtraBuildDirectory $name
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
                throw "Missing native git-extra build output: $source"
            }
            Copy-Item -LiteralPath $source -Destination "$stage\mingwarm64\bin\$name" -Force
        }
        $license = "$stage\mingwarm64\share\licenses\git-extra\LICENSE.txt"
        New-Item -ItemType Directory -Path (Split-Path $license) -Force | Out-Null
        Copy-Item -LiteralPath $BuildExtraLicense -Destination $license
    }))

$receipt = [ordered]@{
    schema = 1
    status = 'verified-native-arm64-git-helper-packages-exported'
    generated_utc = [DateTime]::UtcNow.ToString('o')
    target = 'MINGWARM64/aarch64-w64-mingw32'
    baseline = [ordered]@{
        git_for_windows = 'v2.55.0.windows.5'
        build_extra_commit = $BuildExtraCommit
        distribution_contract_sha256 = $DistributionContractSha256
        git_lfs_version = '3.7.1'
        git_lfs_source_commit = $GitLfsSourceCommit
    }
    upstream_admission = [ordered]@{
        repository = 'git-for-windows/pacman-repo'
        branch = 'aarch64'
        signing_fingerprint = $SigningFingerprint
        detached_signatures_verified = $true
        git_lfs_package_commit = 'af55e9b347f6d2356016b11bc447a8a4c09e41b1'
        git_extra_package_commit = '2864662d81d62b3284ce891f9a110381982f7271'
        git_lfs_signature = [ordered]@{
            path = "sources/$([IO.Path]::GetFileName($GitLfsSignature))"
            sha256 = Get-Sha256 $GitLfsSignature
        }
        git_extra_signature = [ordered]@{
            path = "sources/$([IO.Path]::GetFileName($GitExtraSignature))"
            sha256 = Get-Sha256 $GitExtraSignature
        }
    }
    git_extra_native_rebuild = [ordered]@{
        source_commit = $BuildExtraCommit
        source_inventory_sha256 = Get-Sha256 $BuildExtraInventory
        target = 'aarch64-w64-mingw32'
        jobs = 2
        compiler = [ordered]@{
            gcc_sha256 = Get-Sha256 $GitExtraGcc
            gxx_sha256 = Get-Sha256 $GitExtraGxx
            windres_sha256 = Get-Sha256 $GitExtraWindres
        }
        build_log_sha256 = Get-Sha256 $GitExtraBuildLog
        outputs = [ordered]@{}
    }
    packages = $packages
    ownership = [ordered]@{
        git_lfs = @('mingwarm64/bin/git-lfs.exe')
        git_extra = @('mingwarm64/bin/git-askpass.exe', 'mingwarm64/bin/git-askyesno.exe')
        excluded_managed_component = 'mingwarm64/bin/git-credential-helper-selector.exe'
    }
    adaptation = @(
        'The signed Git-for-Windows CLANGARM64 packages are the native ARM64 donor packages for this release baseline.',
        'Payload paths were moved from clangarm64 to the admitted mingwarm64 prefix after all native PE files were verified as ARM64.',
        'Git LFS executable bytes are unchanged from the signed ARM64 donor package.',
        'git-extra native executables were rebuilt from the pinned build-extra sources with the qualified aarch64-w64-mingw32 GCC toolchain.',
        'git-credential-helper-selector.exe was excluded because the full-release contract assigns that managed path to the GCM provider.'
    )
}
foreach ($name in @(
    'blocked-file-util.exe',
    'create-shortcut.exe',
    'git-askpass.exe',
    'git-askyesno.exe',
    'proxy-lookup.exe',
    'WhoUses.exe'
)) {
    $path = Join-Path $GitExtraBuildDirectory $name
    $receipt.git_extra_native_rebuild.outputs[$name] = [ordered]@{
        sha256 = Get-Sha256 $path
        bytes = (Get-Item -LiteralPath $path).Length
    }
}
$receipt | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath "$OutputDirectory\export.json" -Encoding utf8
$receipt
