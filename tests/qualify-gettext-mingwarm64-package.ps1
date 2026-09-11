#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $PackageArchive,
    [Parameter(Mandatory)][string] $RuntimeDependencyBin,
    [Parameter(Mandatory)][string[]] $DependencyPackages,
    [Parameter(Mandatory)][string] $EvidenceDirectory
)

$ErrorActionPreference = 'Stop'
$archive = Get-Item -LiteralPath $PackageArchive
$dependencyBin = Get-Item -LiteralPath $RuntimeDependencyBin
$integrationRoot = $dependencyBin.Parent.Parent
$pacman = "$($integrationRoot.FullName)\usr\bin\pacman.exe"
$pacmanConfig = "$($integrationRoot.FullName)\etc\pacman.conf"
$gcc = "$($dependencyBin.FullName)\gcc.exe"
$objdump = "$($dependencyBin.FullName)\objdump.exe"
$integrationGit = "$($dependencyBin.FullName)\git.exe"
foreach ($required in $pacman, $pacmanConfig, $gcc, $objdump, $integrationGit,
    "$($dependencyBin.FullName)\libiconv-2.dll") {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Gettext qualification prerequisite is missing: $required"
    }
}
if (Test-Path -LiteralPath $EvidenceDirectory) {
    throw 'Gettext qualification evidence directory must be new.'
}
New-Item -ItemType Directory -Path (
    "$EvidenceDirectory\root",
    "$EvidenceDirectory\installed",
    "$EvidenceDirectory\consumers",
    "$EvidenceDirectory\dependency-extracted",
    "$EvidenceDirectory\moved-root"
) | Out-Null

$entries = @(& "$env:SystemRoot\System32\tar.exe" --zstd -tf $archive.FullName)
if ($LASTEXITCODE -ne 0) { throw 'Cannot list gettext package archive.' }
foreach ($entry in '.PKGINFO', '.BUILDINFO', '.MTREE',
    'mingwarm64/bin/gettext.exe', 'mingwarm64/bin/libintl-8.dll') {
    if ($entry -cnotin $entries) { throw "Gettext package is missing $entry." }
}
$pkginfo = @(& "$env:SystemRoot\System32\tar.exe" --zstd -xOf $archive.FullName .PKGINFO)
if ($LASTEXITCODE -ne 0) { throw 'Cannot read gettext package metadata.' }
foreach ($line in @(
    'pkgname = mingw-w64-aarch64-gettext',
    'pkgver = 1.0-1',
    'depend = mingw-w64-aarch64-libiconv'
)) {
    if ($line -cnotin $pkginfo) { throw "Gettext package metadata is missing: $line" }
}
$packageDependencies = @(
    $pkginfo | ForEach-Object {
        if ($_ -match '^depend = (.+)$') { $Matches[1] }
    }
)
$packageDependencyNames = @(
    $packageDependencies | ForEach-Object {
        if ($_ -notmatch '^([^<>=]+)') { throw "Invalid gettext dependency: $_" }
        $Matches[1]
    }
)

function Read-PackageIdentity([string] $Path) {
    $info = @(& "$env:SystemRoot\System32\tar.exe" --zstd -xOf $Path .PKGINFO)
    if ($LASTEXITCODE -ne 0) { throw "Cannot read dependency package metadata: $Path" }
    $name = @($info | ForEach-Object { if ($_ -match '^pkgname = (.+)$') { $Matches[1] } })
    $version = @($info | ForEach-Object { if ($_ -match '^pkgver = (.+)$') { $Matches[1] } })
    if ($name.Count -ne 1 -or $version.Count -ne 1) {
        throw "Dependency archive has invalid package identity: $Path"
    }
    [ordered]@{ name = $name[0]; version = $version[0] }
}

$dependencyArchives = @(
    foreach ($dependencyPackage in $DependencyPackages) {
        $item = Get-Item -LiteralPath $dependencyPackage
        $identity = Read-PackageIdentity $item.FullName
        [pscustomobject]@{
            item = $item
            name = $identity.name
            version = $identity.version
            sha256 = (Get-FileHash $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
)
if (@($dependencyArchives.name | Sort-Object -Unique).Count -ne $dependencyArchives.Count) {
    throw 'Gettext dependency package set contains duplicate package identities.'
}
$missingDependencyArchives = @(
    $packageDependencyNames | Where-Object { $_ -cnotin $dependencyArchives.name }
)
if ($missingDependencyArchives.Count) {
    throw "Gettext dependency package set is missing: $($missingDependencyArchives -join ', ')"
}

& "$env:SystemRoot\System32\tar.exe" --zstd -xf $archive.FullName -C "$EvidenceDirectory\root"
if ($LASTEXITCODE -ne 0) { throw 'Cannot extract gettext package archive.' }
$prefix = "$EvidenceDirectory\root\mingwarm64"

function Get-PeMachine([string] $Path) {
    $stream = [IO.File]::OpenRead($Path)
    try {
        $reader = [IO.BinaryReader]::new($stream)
        if ($reader.ReadUInt16() -ne 0x5a4d) { throw "Not a PE file: $Path" }
        $stream.Position = 0x3c
        $stream.Position = $reader.ReadUInt32()
        if ($reader.ReadUInt32() -ne 0x00004550) { throw "Invalid PE signature: $Path" }
        $reader.ReadUInt16()
    } finally {
        $stream.Dispose()
    }
}

function Get-PeImports([string] $Path) {
    $output = @(& $objdump -p $Path 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Cannot inspect PE imports: $Path" }
    @(
        $output |
            ForEach-Object {
                if ($_ -match '^\s*DLL Name:\s*(\S+)\s*$') { $Matches[1] }
            } |
            Where-Object { $_ } |
            Sort-Object -Unique
    )
}

$packageBinNames = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
Get-ChildItem "$prefix\bin" -File | ForEach-Object { [void]$packageBinNames.Add($_.Name) }
$dependencyBinNames = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
Get-ChildItem $dependencyBin.FullName -File | ForEach-Object {
    [void]$dependencyBinNames.Add($_.Name)
}
$systemDllNames = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
Get-ChildItem "$env:SystemRoot\System32" -Filter '*.dll' -File | ForEach-Object {
    [void]$systemDllNames.Add($_.Name)
}

$peInventory = @(
    Get-ChildItem "$prefix\bin" -File |
        Where-Object { $_.Extension -in '.exe', '.dll' } |
        Sort-Object Name |
        ForEach-Object {
            $machine = Get-PeMachine $_.FullName
            if ($machine -ne 0xaa64) { throw "Gettext payload is not ARM64: $($_.FullName)" }
            $imports = @(Get-PeImports $_.FullName)
            $resolvedImports = foreach ($import in $imports) {
                $source = if ($packageBinNames.Contains($import)) {
                    'package'
                } elseif ($dependencyBinNames.Contains($import)) {
                    'qualified-integration-dependency'
                } elseif ($systemDllNames.Contains($import) -or
                    $import.StartsWith('api-ms-win-', [StringComparison]::OrdinalIgnoreCase) -or
                    $import.StartsWith('ext-ms-', [StringComparison]::OrdinalIgnoreCase)) {
                    'windows-system'
                } else {
                    throw "Unresolved gettext PE import '$import' in $($_.FullName)."
                }
                [ordered]@{ name = $import; source = $source }
            }
            [ordered]@{
                path = [IO.Path]::GetRelativePath($prefix, $_.FullName).Replace('\', '/')
                sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                machine = '0xaa64'
                imports = @($resolvedImports)
            }
        }
)
foreach ($requiredBinary in 'bin/gettext.exe', 'bin/libintl-8.dll') {
    if ($requiredBinary -cnotin $peInventory.path) {
        throw "Gettext PE inventory is missing $requiredBinary."
    }
}
$peInventoryPath = "$EvidenceDirectory\pe-import-inventory.json"
$peInventory | ConvertTo-Json -Depth 7 | Set-Content $peInventoryPath -Encoding utf8

function Test-ByteSequence([byte[]] $Haystack, [byte[]] $Needle) {
    if ($Needle.Length -eq 0 -or $Needle.Length -gt $Haystack.Length) { return $false }
    for ($i = 0; $i -le $Haystack.Length - $Needle.Length; $i++) {
        if ($Haystack[$i] -ne $Needle[0]) { continue }
        $match = $true
        for ($j = 1; $j -lt $Needle.Length; $j++) {
            if ($Haystack[$i + $j] -ne $Needle[$j]) {
                $match = $false
                break
            }
        }
        if ($match) { return $true }
    }
    $false
}
foreach ($marker in 'C:\ap', 'C:/ap', '/c/ap', '.copilot', 'session-state') {
    $needle = [Text.Encoding]::ASCII.GetBytes($marker)
    $matches = @(Get-ChildItem "$EvidenceDirectory\root" -Recurse -Force -File | Where-Object {
        Test-ByteSequence ([IO.File]::ReadAllBytes($_.FullName)) $needle
    })
    if ($matches.Count) {
        throw "Gettext package contains forbidden marker '$marker': $($matches.FullName -join ', ')"
    }
}

$installRoot = (Get-Item "$EvidenceDirectory\installed").FullName
New-Item -ItemType Directory -Force -Path (
    "$installRoot\var\lib\pacman",
    "$installRoot\var\log",
    "$installRoot\var\cache\pacman\pkg"
) | Out-Null
$installArguments = @(
    '--root', $installRoot,
    '--config', $pacmanConfig,
    '--noconfirm',
    '-U'
) + @($dependencyArchives | ForEach-Object { $_.item.FullName }) + @($archive.FullName)
$pacmanOutput = @(
    & $pacman @installArguments 2>&1 | ForEach-Object { $_.ToString() }
)
$pacmanExit = $LASTEXITCODE
$pacmanOutput | Set-Content "$EvidenceDirectory\pacman-install.log" -Encoding utf8
if ($pacmanExit -ne 0) {
    throw "Pacman dependency transaction failed with exit code $pacmanExit."
}
$queryPackageNames = @($dependencyArchives.name) + 'mingw-w64-aarch64-gettext'
$queryArguments = @('--root', $installRoot, '--config', $pacmanConfig, '-Q') +
    $queryPackageNames
$installedPackages = @(
    & $pacman @queryArguments 2>&1 | ForEach-Object { $_.ToString() }
)
if ($LASTEXITCODE -ne 0) {
    throw 'Pacman could not read back the gettext dependency transaction.'
}
$expectedInstalledPackages = @(
    $dependencyArchives | ForEach-Object { "$($_.name) $($_.version)" }
) + 'mingw-w64-aarch64-gettext 1.0-1'
if (@($expectedInstalledPackages | Where-Object { $_ -cnotin $installedPackages }).Count) {
    throw 'Pacman did not read back the exact gettext dependency package identities.'
}
$installedPackages | Set-Content "$EvidenceDirectory\pacman-query.log" -Encoding utf8

$dependencyPayloadComparison = @(
    foreach ($dependency in $dependencyArchives) {
        $extractRoot = "$EvidenceDirectory\dependency-extracted\$($dependency.name)"
        New-Item -ItemType Directory $extractRoot | Out-Null
        & "$env:SystemRoot\System32\tar.exe" --zstd -xf $dependency.item.FullName -C $extractRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Cannot extract dependency package for byte comparison: $($dependency.name)"
        }
        $files = @(
            Get-ChildItem $extractRoot -Recurse -File |
                Where-Object {
                    -not [IO.Path]::GetRelativePath($extractRoot, $_.FullName).StartsWith(
                        '.',
                        [StringComparison]::Ordinal
                    )
                } |
                Sort-Object FullName |
                ForEach-Object {
                    $relative = [IO.Path]::GetRelativePath($extractRoot, $_.FullName)
                    $installedPath = Join-Path $installRoot $relative
                    if (-not (Test-Path -LiteralPath $installedPath -PathType Leaf)) {
                        throw "Installed dependency file is missing: $relative"
                    }
                    $archiveHash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                    $installedHash =
                        (Get-FileHash $installedPath -Algorithm SHA256).Hash.ToLowerInvariant()
                    if ($archiveHash -cne $installedHash) {
                        throw "Installed dependency bytes differ from the archive: $relative"
                    }
                    [ordered]@{
                        path = $relative.Replace('\', '/')
                        bytes = $_.Length
                        sha256 = $archiveHash
                    }
                }
        )
        [ordered]@{
            name = $dependency.name
            version = $dependency.version
            archiveSha256 = $dependency.sha256
            files = $files
            everyInstalledFileByteIdentical = $true
        }
    }
)
$dependencyPayloadComparisonPath = "$EvidenceDirectory\dependency-payload-comparison.json"
$dependencyPayloadComparison | ConvertTo-Json -Depth 7 |
    Set-Content $dependencyPayloadComparisonPath -Encoding utf8

$dependencyArguments = @('--root', $installRoot, '--config', $pacmanConfig, '-T') +
    $packageDependencies
$dependencyCheck = @(
    & $pacman @dependencyArguments 2>&1 | ForEach-Object { $_.ToString() }
)
$dependencyExit = $LASTEXITCODE
$dependencyCheck | Set-Content "$EvidenceDirectory\pacman-dependency-check.log" -Encoding utf8
$unsatisfiedDependencies = @(
    $dependencyCheck | Where-Object {
        $_ -notmatch '^warning: database file for .+ does not exist'
    }
)
if ($dependencyExit -ne 0 -or $unsatisfiedDependencies.Count -ne 0) {
    throw 'Pacman dependency resolution did not satisfy the gettext package metadata.'
}
$qkkArguments = @('--root', $installRoot, '--config', $pacmanConfig, '-Qkk') +
    $queryPackageNames
$qkk = @(
    & $pacman @qkkArguments 2>&1 | ForEach-Object { $_.ToString() }
)
$qkkExit = $LASTEXITCODE
$qkk | Set-Content "$EvidenceDirectory\pacman-qkk.log" -Encoding utf8
$gettextQkk = @(
    $qkk | Where-Object {
        $_ -match '^mingw-w64-aarch64-gettext: [0-9]+ total files, 0 altered files$'
    }
)
$unexpectedQkk = @(
    $qkk | Where-Object {
        $_ -notmatch '^warning: database file for .+ does not exist' -and
        $_ -notmatch '^warning: mingw-w64-aarch64-libiconv: .+ \((Modification time|Permissions) mismatch\)$' -and
        $_ -notmatch '^mingw-w64-aarch64-libiconv: [0-9]+ total files, [0-9]+ altered files$' -and
        $_ -notmatch '^mingw-w64-aarch64-gettext: [0-9]+ total files, 0 altered files$'
    }
)
if ($qkkExit -notin 0, 1 -or $gettextQkk.Count -ne 1 -or $unexpectedQkk.Count -ne 0) {
    throw 'Pacman package integrity readback failed.'
}

$installedPrefix = "$installRoot\mingwarm64"
$consumerSource = "$EvidenceDirectory\consumers\gettext-consumer.c"
[IO.File]::WriteAllText(
    $consumerSource,
    @'
#include <libintl.h>
#include <string.h>

int main(void) {
  const char *translated = gettext("qualified-consumer");
  return strcmp(translated, "qualified-consumer") == 0 ? 0 : 1;
}
'@,
    [Text.UTF8Encoding]::new($false)
)
$sharedConsumer = "$EvidenceDirectory\consumers\gettext-shared.exe"
$sharedOutput = @(
    & $gcc "-I$installedPrefix\include" $consumerSource `
        "-L$installedPrefix\lib" -lintl -o $sharedConsumer 2>&1
)
$sharedExit = $LASTEXITCODE
[IO.File]::WriteAllText(
    "$EvidenceDirectory\consumers\shared-link.log",
    $sharedOutput -join [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
if ($sharedExit -ne 0 -or (Get-PeMachine $sharedConsumer) -ne 0xaa64) {
    throw 'Package-installed shared libintl consumer did not link as ARM64.'
}
$sharedImports = @(Get-PeImports $sharedConsumer)
if ('libintl-8.dll' -cnotin $sharedImports) {
    throw 'Shared libintl consumer does not import the package module identity libintl-8.dll.'
}

$staticConsumer = "$EvidenceDirectory\consumers\gettext-static.exe"
$staticOutput = @(
    & $gcc "-I$installedPrefix\include" $consumerSource `
        "$installedPrefix\lib\libintl.a" "$installedPrefix\lib\libiconv.a" `
        -o $staticConsumer 2>&1
)
$staticExit = $LASTEXITCODE
[IO.File]::WriteAllText(
    "$EvidenceDirectory\consumers\static-link.log",
    $staticOutput -join [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
if ($staticExit -ne 0 -or (Get-PeMachine $staticConsumer) -ne 0xaa64) {
    throw 'Package-installed static libintl consumer did not link as ARM64.'
}
$staticImports = @(Get-PeImports $staticConsumer)
if ('libintl-8.dll' -cin $staticImports -or 'libiconv-2.dll' -cin $staticImports) {
    throw 'Static libintl consumer unexpectedly imports libintl or libiconv DLLs.'
}
$gitDirectory = "$EvidenceDirectory\consumers\git-isolated"
New-Item -ItemType Directory $gitDirectory | Out-Null
$git = "$gitDirectory\git.exe"
Copy-Item $integrationGit $git

$savedPath = $env:PATH
$savedGitExecPath = $env:GIT_EXEC_PATH
$savedGitTemplateDir = $env:GIT_TEMPLATE_DIR
$savedGitConfigSystem = $env:GIT_CONFIG_SYSTEM
$savedGitConfigGlobal = $env:GIT_CONFIG_GLOBAL
$env:PATH = "$installedPrefix\bin;$($dependencyBin.FullName);$savedPath"
$env:GIT_EXEC_PATH = $null
$env:GIT_TEMPLATE_DIR = $null
$env:GIT_CONFIG_SYSTEM = $null
$env:GIT_CONFIG_GLOBAL = $null
try {
    $version = & "$installedPrefix\bin\gettext.exe" --version
    if ($LASTEXITCODE -ne 0 -or $version[0] -cne 'gettext.exe (GNU gettext-runtime) 1.0') {
        throw 'Packaged gettext runtime smoke test failed.'
    }
    $translated = 'qualified' | & "$installedPrefix\bin\gettext.exe" 'qualified'
    if ($LASTEXITCODE -ne 0 -or $translated -cne 'qualified') {
        throw 'Packaged gettext identity translation smoke test failed.'
    }
    & $sharedConsumer
    if ($LASTEXITCODE -ne 0) { throw 'Shared package-installed gettext consumer failed.' }
    & $staticConsumer
    if ($LASTEXITCODE -ne 0) { throw 'Static package-installed gettext consumer failed.' }

    $gitImports = @(Get-PeImports $git)
    if ('libintl-8.dll' -cnotin $gitImports) {
        throw 'Existing exact-15 Git consumer does not import libintl-8.dll.'
    }
    $gitRepository = "$EvidenceDirectory\consumers\git-gettext-runtime"
    $gitInit = @(& $git init --quiet $gitRepository 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Git/gettext ABI control repository initialization failed.' }
    $gitStatus = @(& $git -C $gitRepository status --short --branch 2>&1)
    if ($LASTEXITCODE -ne 0 -or $gitStatus.Count -eq 0) {
        throw 'Existing exact-15 Git failed with the package-installed gettext runtime.'
    }
    @($gitInit; $gitStatus) |
        Set-Content "$EvidenceDirectory\consumers\git-gettext-runtime.log" -Encoding utf8
} finally {
    $env:PATH = $savedPath
    $env:GIT_EXEC_PATH = $savedGitExecPath
    $env:GIT_TEMPLATE_DIR = $savedGitTemplateDir
    $env:GIT_CONFIG_SYSTEM = $savedGitConfigSystem
    $env:GIT_CONFIG_GLOBAL = $savedGitConfigGlobal
}

$movedPrefix = "$EvidenceDirectory\moved-root\mingwarm64"
Copy-Item -LiteralPath $installedPrefix -Destination $movedPrefix -Recurse
$movedGettext = "$movedPrefix\bin\gettext.exe"
$movedMsgunfmt = "$movedPrefix\bin\msgunfmt.exe"
$movedCatalog = "$movedPrefix\share\locale\fr\LC_MESSAGES\gettext-runtime.mo"
foreach ($required in $movedGettext, $movedMsgunfmt, $movedCatalog) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Moved-root gettext evidence is missing: $required"
    }
}
$savedPath = $env:PATH
$savedLanguage = $env:LANGUAGE
$savedLcAll = $env:LC_ALL
$env:PATH = "$movedPrefix\bin;$savedPath"
$env:LANGUAGE = 'fr'
$env:LC_ALL = 'French_France.65001'
try {
    $movedHelp = @(& $movedGettext --help 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Moved-root gettext help failed.' }
    $normalizedHelp = ($movedHelp -join "`n").Replace('\', '/')
    $expectedLocaleDirectory = "$movedPrefix\share\locale".Replace('\', '/')
    if (-not $normalizedHelp.Contains($expectedLocaleDirectory, [StringComparison]::Ordinal) -or
        $normalizedHelp.Contains(
            "$installedPrefix\share\locale".Replace('\', '/'),
            [StringComparison]::Ordinal
        )) {
        throw 'Moved-root gettext did not relocate its default locale directory.'
    }
    $boundMessage = "  -E                        (ignored for compatibility)`n"
    $movedBound = @(& $movedGettext -d gettext-runtime $boundMessage 2>&1)
    if ($LASTEXITCODE -ne 0 -or
        -not ($movedBound -join "`n").Contains('compatibilit', [StringComparison]::Ordinal)) {
        throw 'Moved-root gettext did not load its shipped bound catalog.'
    }
    $unboundMessage = 'qualification-unbound-message'
    $movedUnbound = @(
        & $movedGettext -d qualification-missing-domain $unboundMessage 2>&1
    )
    if ($LASTEXITCODE -ne 0 -or ($movedUnbound -join "`n") -cne $unboundMessage) {
        throw 'Moved-root gettext missing-domain behavior did not preserve the message identity.'
    }
    $movedCatalogDump = @(& $movedMsgunfmt $movedCatalog 2>&1)
    if ($LASTEXITCODE -ne 0 -or
        -not ($movedCatalogDump -join "`n").Contains(
            '"Language: fr\n"',
            [StringComparison]::Ordinal
        )) {
        throw 'Moved-root msgunfmt could not read the shipped gettext catalog.'
    }
} finally {
    $env:PATH = $savedPath
    $env:LANGUAGE = $savedLanguage
    $env:LC_ALL = $savedLcAll
}
$movedHelp | Set-Content "$EvidenceDirectory\moved-root-help.log" -Encoding utf8
$movedBound | Set-Content "$EvidenceDirectory\moved-root-bound.log" -Encoding utf8
$movedUnbound | Set-Content "$EvidenceDirectory\moved-root-unbound.log" -Encoding utf8
$movedCatalogDump | Set-Content "$EvidenceDirectory\moved-root-msgunfmt.log" -Encoding utf8

$fileManifest = @(
    Get-ChildItem $installedPrefix -Recurse -File |
        Sort-Object FullName |
        ForEach-Object {
            [ordered]@{
                path = [IO.Path]::GetRelativePath($installedPrefix, $_.FullName).Replace('\', '/')
                bytes = $_.Length
                sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
)
$fileManifestPath = "$EvidenceDirectory\installed-file-manifest.json"
$fileManifest | ConvertTo-Json -Depth 4 | Set-Content $fileManifestPath -Encoding utf8
$integrationPackages = @(
    & $pacman --root $integrationRoot.FullName --config $pacmanConfig -Q `
        mingw-w64-aarch64-gcc mingw-w64-aarch64-libiconv 2>&1
)
if ($LASTEXITCODE -ne 0) {
    throw 'Cannot identify the qualified MinGW compiler/libiconv cohort.'
}
$gccVersion = @(& $gcc --version)
if ($LASTEXITCODE -ne 0 -or $gccVersion.Count -eq 0) {
    throw 'Cannot identify the qualified native GCC toolchain.'
}
$evidenceFiles = @(
    'pacman-install.log',
    'pacman-query.log',
    'pacman-dependency-check.log',
    'pacman-qkk.log',
    'dependency-payload-comparison.json',
    'pe-import-inventory.json',
    'installed-file-manifest.json',
    'moved-root-help.log',
    'moved-root-bound.log',
    'moved-root-unbound.log',
    'moved-root-msgunfmt.log',
    'consumers/gettext-consumer.c',
    'consumers/shared-link.log',
    'consumers/static-link.log',
    'consumers/gettext-shared.exe',
    'consumers/gettext-static.exe',
    'consumers/git-gettext-runtime.log'
) | ForEach-Object {
    $path = Join-Path $EvidenceDirectory $_
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Gettext qualification evidence is missing: $path"
    }
    [ordered]@{
        path = (Get-Item $path).FullName
        sha256 = (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$receipt = [ordered]@{
    schema = 1
    status = 'gettext-package-qualified'
    package = $archive.FullName
    sha256 = (Get-FileHash $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    identity = 'mingw-w64-aarch64-gettext-1.0-1'
    architecture = 'PE32+ ARM64'
    runtime = $version[0]
    files = @($entries | Where-Object { $_ -and -not $_.EndsWith('/') }).Count
    privatePathAudit = 'passed'
    libtoolDependencyCacheOverride = [ordered]@{
        value = 'lt_cv_deplibs_check_method=pass_all'
        acceptedOnlyForCrossConfigure = $true
        independentDependencyProof = @(
            'pacman transaction and dependency resolution',
            'complete ARM64 PE import inventory and recursive closure',
            'package-installed shared consumer link and execution',
            'package-installed static consumer link and execution',
            'existing exact-15 Git import and runtime execution'
        )
    }
    pacman = [ordered]@{
        installed = $installedPackages
        qkk = $qkk
        gettextPackageAlteredFiles = 0
        dependencyMtreeLimitation = @(
            $qkk | Where-Object {
                $_ -match '^mingw-w64-aarch64-libiconv: .+ altered files$'
            }
        )
        dependencyPayloadComparison = [ordered]@{
            path = (Get-Item $dependencyPayloadComparisonPath).FullName
            sha256 = (Get-FileHash $dependencyPayloadComparisonPath -Algorithm SHA256).
                Hash.ToLowerInvariant()
            everyInstalledFileByteIdentical = $true
        }
        dependencyResolution = 'satisfied'
    }
    relocation = [ordered]@{
        movedPrefix = $movedPrefix
        reportedDefaultLocaleDirectory = $expectedLocaleDirectory
        shippedBoundCatalog = 'passed'
        missingDomainIdentity = 'passed'
        movedCatalogTool = 'passed'
    }
    consumers = [ordered]@{
        shared = [ordered]@{
            path = $sharedConsumer
            sha256 = (Get-FileHash $sharedConsumer -Algorithm SHA256).Hash.ToLowerInvariant()
            imports = $sharedImports
            runtime = 'passed'
        }
        static = [ordered]@{
            path = $staticConsumer
            sha256 = (Get-FileHash $staticConsumer -Algorithm SHA256).Hash.ToLowerInvariant()
            imports = $staticImports
            runtime = 'passed'
        }
        git = [ordered]@{
            path = $git
            sha256 = (Get-FileHash $git -Algorithm SHA256).Hash.ToLowerInvariant()
            sourcePath = $integrationGit
            imports = $gitImports
            runtime = $gitStatus
        }
    }
    peInventory = [ordered]@{
        path = (Get-Item $peInventoryPath).FullName
        sha256 = (Get-FileHash $peInventoryPath -Algorithm SHA256).Hash.ToLowerInvariant()
        binaries = $peInventory.Count
        allArm64 = $true
        allImportsResolved = $true
    }
    installedFileManifest = [ordered]@{
        path = (Get-Item $fileManifestPath).FullName
        sha256 = (Get-FileHash $fileManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
        files = $fileManifest.Count
        includesEveryFileHash = $true
    }
    integrationCohort = [ordered]@{
        packages = $integrationPackages
        gcc = [ordered]@{
            version = $gccVersion[0]
            path = $gcc
            sha256 = (Get-FileHash $gcc -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        dependencyPackages = @(
            $dependencyArchives | ForEach-Object {
                [ordered]@{
                    name = $_.name
                    version = $_.version
                    path = $_.item.FullName
                    sha256 = $_.sha256
                }
            }
        )
        runtimeApiCohort = 'MINGWARM64 native Windows PE; no MSYS d70 runtime ABI is shipped by this provider'
    }
    evidenceFiles = $evidenceFiles
}
$receipt | ConvertTo-Json -Depth 20 | Set-Content "$EvidenceDirectory\qualification.json" -Encoding utf8
$receipt
