[CmdletBinding()]
param(
    [string]$CandidateRoot = $env:ARM64_CANDIDATE_ROOT,
    [string]$PolicyPath = (Join-Path $PSScriptRoot '..\policies\arm64-quarantine-policy.json'),
    [ValidateSet('Auto', 'PowerShellYaml', 'RubyPsych', 'Unavailable')]
    [string]$ParserBackend = 'Auto',
    [switch]$FixtureMode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'git-object-integrity.ps1')

function Get-Arm64MapProperty {
    param(
        [AllowNull()][object]$Map,
        [Parameter(Mandatory)][string]$Name
    )

    if ($null -eq $Map) {
        return $null
    }
    if ($Map -is [Collections.IDictionary]) {
        if ($Map.Contains($Name)) {
            return [pscustomobject]@{ Name = $Name; Value = $Map[$Name] }
        }
        return $null
    }
    return $Map.PSObject.Properties[$Name]
}

function Get-Arm64ExactMapProperty {
    param(
        [AllowNull()][object]$Map,
        [Parameter(Mandatory)][string]$Name
    )

    if ($null -eq $Map) {
        return $null
    }
    if ($Map -is [Collections.IDictionary]) {
        foreach ($key in $Map.Keys) {
            if ([string]$key -ceq $Name) {
                return [pscustomobject]@{ Name = [string]$key; Value = $Map[$key] }
            }
        }
        return $null
    }
    foreach ($property in $Map.PSObject.Properties) {
        if ($property.Name -ceq $Name) {
            return $property
        }
    }
    return $null
}

function Get-Arm64MapNames {
    param([AllowNull()][object]$Map)

    if ($null -eq $Map) {
        return @()
    }
    if ($Map -is [Collections.IDictionary]) {
        return @($Map.Keys | ForEach-Object { [string]$_ })
    }
    return @($Map.PSObject.Properties | ForEach-Object { $_.Name })
}

$script:arm64PowerShellYamlPin = [pscustomobject][ordered]@{
    Version = '0.4.12'
    TreeSha256 = '1eb02f54677a67d1dc28aaab55e155b7b298cde6ed1b6a2c6b60fba49058a327'
    TreeManifestSha256 =
        '56392f7acfa2a826bd89385129b6c3afb1f0b29efd27497f70c2a3272ecd556d'
    ManifestSha256 = 'b17d30f63eee0fd5e5bb074043045c499e87b254c044ce5b1a5e71df2dd8c469'
    ModuleSha256 = '415b0de1b4d5af6980ec50316d3267fa19663b7dbf809d219783b41ed39b2e5d'
    AssemblyVersion = '16.0.0.0'
    AssemblyPublicKey = (
        '0024000004800000940000000602000000240000525341310004000001000100' +
        '65e52a453dde5c5b4be5bbe2205755727fce80244b79b894faf8793d80f7db9a' +
        '96d360b51c220782db32aacee4cb5b8a91bee33aeec700e1f21895c4baadef50' +
        '1eeeac609220d1651603b378173811ee5bb6a002df973d38821bd2fef820c00c1' +
        '74a69faec326a1983b570f07ec66147026b9c8753465de3a8d0c44b613b02af'
    )
    AssemblyPublicKeyToken = 'ec19458f3c15af5e'
    Core = [pscustomobject][ordered]@{
        AssemblyRelativePath = 'lib\netstandard2.1\YamlDotNet.dll'
        AssemblySha256 = 'd7543a03a69f14ca1e302aa2bbb09777200b72e0c6db0d0eb7614593f5c33e0f'
        SerializerRelativePath = 'lib\netstandard2.1\PowerShellYamlSerializer.dll'
        SerializerSha256 = 'c9193f2fb5afa40af61d908589fdd0929ab58472be215fc2afb692194d53210d'
    }
    Desktop = [pscustomobject][ordered]@{
        AssemblyRelativePath = 'lib\net47\YamlDotNet.dll'
        AssemblySha256 = 'd35c770d92632bd94bba4203db05eee5ebce6e6ea6d92e7ebe8997a942b5321c'
        SerializerRelativePath = 'lib\net47\PowerShellYamlSerializer.dll'
        SerializerSha256 = 'a5bdd33675629ca88cf05cd08150a19a69bc20b21cbe1d1e5e55fe63a332062a'
    }
}
$script:arm64RubyPin = [pscustomobject][ordered]@{
    RubyVersion = '3.3.0'
    PsychVersion = '5.1.2'
    BinTreeSha256 = '05c6f2c580946850a893462bbd46a663e3393bf8d26b9cc3b3ada2e43134fe1e'
    BinManifestSha256 = 'ca44abaf4ba286472936985163af5e3015da44efe1315218328b6b45d23440bb'
    StandardLibraryTreeSha256 =
        'e4bc69c73bc548d37ad244b08dcb4b5708cfa5df5fac1260651a37e3dd18ee4a'
    StandardLibraryManifestSha256 =
        '9b99bf3259b0eac385604a7d0b397fe42960040878f08ff6a392139c35bfaac8'
    ExecutableSha256 = '8fea462df14744fcccbb9005a2ef812470c3aa030168c6a8e1590ed733f5ab9d'
    CoreSha256 = '6cf4426199da5b317e3db5b64c13041f046a569ae4968c3d26f6fd1da0d656cd'
    PsychNativeSha256 = 'daa1d9fa7e2ab74827190284aa87c2758c10804d14792848e1c5fc921740e13b'
    LibYamlSha256 = '1942ec5a43f1b22dd651283ab2b00efe8ccee907d4bccfa86fd5ba95b0985aba'
    PsychEntrySha256 = '03f728df77848d87d338d4f05624d8bd06adf5772b41acba3982ad97bdcfb21f'
    PsychTreeSha256 = '3e0eab842f936902aa882e8577ac2afbdcce595fc14065c70a027883f6ee2f9f'
    JsonTreeSha256 = '57c472e4434dc31e98e62a84712f57b443bb59dbc84116a90878673f23550073'
    JsonNativeTreeSha256 = '260195a5e34180301471aa0cdff8f491e12fcb769060d4386e1e20d327d0a152'
}
$script:arm64ParserHelperPins = [pscustomobject][ordered]@{
    PowerShell = '4611c4ce230761456c58f686e7211eb160644c49bb98f45d68ea6e8463897bd8'
    Ruby = '454939d1e0544b1af8a10f0b2e2efc239d8594ae65d27686eff711dab513d91c'
}
$script:arm64PowerShellYamlIdentity = $null
$script:arm64RubyIdentity = $null
$script:arm64ApprovedYamlBackends = $null

function Reset-Arm64RuntimeIdentityCache {
    if ($null -ne $script:arm64PowerShellYamlIdentity -and
        $null -ne $script:arm64PowerShellYamlIdentity.PSObject.Properties['Locks']) {
        Close-Arm64ReadLockSet -Locks $script:arm64PowerShellYamlIdentity.Locks
    }
    if ($null -ne $script:arm64RubyIdentity -and
        $null -ne $script:arm64RubyIdentity.PSObject.Properties['Locks']) {
        Close-Arm64ReadLockSet -Locks $script:arm64RubyIdentity.Locks
    }
    $script:arm64PowerShellYamlIdentity = $null
    $script:arm64RubyIdentity = $null
    $script:arm64ApprovedYamlBackends = $null
    if (Test-Path -LiteralPath Function:\Reset-Arm64GitRuntimeIdentity) {
        Reset-Arm64GitRuntimeIdentity
    }
}

function Get-Arm64FileSha256 {
    param([Parameter(Mandatory)][string]$Path)

    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return -join ($sha256.ComputeHash($stream) | ForEach-Object {
                $_.ToString('x2')
            })
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Test-Arm64FileSha256 {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )

    return [IO.Path]::IsPathFullyQualified($Path) -and
        (Test-Path -LiteralPath $Path -PathType Leaf) -and
        (Get-Arm64FileSha256 -Path $Path) -ceq $Expected
}

function Get-Arm64DirectoryManifestSha256 {
    param([Parameter(Mandatory)][string]$Root)

    $rootFull = Resolve-Arm64CanonicalRuntimePath -Path $Root
    $paths = [Collections.Generic.Dictionary[string, long]]::new(
        [StringComparer]::Ordinal
    )
    foreach ($file in Get-ChildItem -LiteralPath $rootFull -File -Recurse -Force) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'semantic-parser-provenance-unapproved'
        }
        $relative = $file.FullName.Substring($rootFull.Length + 1).Replace(
            [IO.Path]::DirectorySeparatorChar,
            '/'
        )
        if (-not $paths.TryAdd($relative, [long]$file.Length)) {
            throw 'semantic-parser-provenance-unapproved'
        }
    }
    $ordered = [string[]]@($paths.Keys)
    [Array]::Sort($ordered, [StringComparer]::Ordinal)
    $hash = [Security.Cryptography.IncrementalHash]::CreateHash(
        [Security.Cryptography.HashAlgorithmName]::SHA256
    )
    try {
        foreach ($relative in $ordered) {
            $metadata = [Text.UTF8Encoding]::new($false, $true).GetBytes(
                "$relative`0$($paths[$relative])`0"
            )
            $hash.AppendData($metadata)
        }
        return [Convert]::ToHexString($hash.GetHashAndReset()).ToLowerInvariant()
    }
    finally {
        $hash.Dispose()
    }
}

function Get-Arm64DirectoryTreeSha256 {
    param([Parameter(Mandatory)][string]$Root)

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    if (-not (Test-Path -LiteralPath $rootFull -PathType Container)) {
        throw 'semantic-parser-provenance-unapproved'
    }

    $paths = [Collections.Generic.Dictionary[string, string]]::new(
        [StringComparer]::Ordinal
    )
    foreach ($file in Get-ChildItem -LiteralPath $rootFull -File -Recurse -Force) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'semantic-parser-provenance-unapproved'
        }
        $relative = $file.FullName.Substring($rootFull.Length + 1).Replace(
            [IO.Path]::DirectorySeparatorChar,
            '/'
        )
        if (-not $paths.TryAdd($relative, $file.FullName)) {
            throw 'semantic-parser-provenance-unapproved'
        }
    }

    $ordered = [string[]]@($paths.Keys)
    [Array]::Sort($ordered, [StringComparer]::Ordinal)
    $hash = [Security.Cryptography.IncrementalHash]::CreateHash(
        [Security.Cryptography.HashAlgorithmName]::SHA256
    )
    try {
        foreach ($relative in $ordered) {
            $stream = [IO.File]::Open(
                $paths[$relative],
                [IO.FileMode]::Open,
                [IO.FileAccess]::Read,
                [IO.FileShare]::Read
            )
            try {
                $metadata = [Text.UTF8Encoding]::new($false, $true).GetBytes(
                    "$relative`0$($stream.Length)`0"
                )
                $hash.AppendData($metadata)
                $buffer = [byte[]]::new(65536)
                while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $hash.AppendData($buffer, 0, $read)
                }
            }
            finally {
                $stream.Dispose()
            }
        }
        return [Convert]::ToHexString($hash.GetHashAndReset()).ToLowerInvariant()
    }
    finally {
        $hash.Dispose()
    }
}

function Add-Arm64AbsoluteCandidate {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [Collections.Generic.HashSet[string]]$Candidates,
        [AllowNull()][string]$Path
    )

    if (-not [string]::IsNullOrWhiteSpace($Path) -and
        [IO.Path]::IsPathFullyQualified($Path)) {
        [void]$Candidates.Add([IO.Path]::GetFullPath($Path))
    }
}

function Resolve-Arm64PowerShellYamlIdentity {
    if ($null -ne $script:arm64PowerShellYamlIdentity) {
        try {
            $cached = $script:arm64PowerShellYamlIdentity
            $manifestPath = Resolve-Arm64CanonicalRuntimePath -Path $cached.ManifestPath
            $moduleBase = Resolve-Arm64CanonicalRuntimePath -Path $cached.ModuleBase
            $assemblyPath = Resolve-Arm64CanonicalRuntimePath -Path $cached.AssemblyPath
            if (-not $manifestPath.StartsWith(
                    "$moduleBase$([IO.Path]::DirectorySeparatorChar)",
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                -not $assemblyPath.StartsWith(
                    "$moduleBase$([IO.Path]::DirectorySeparatorChar)",
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                -not (Test-Arm64FileSha256 `
                    -Path $manifestPath `
                    -Expected $script:arm64PowerShellYamlPin.ManifestSha256) -or
                -not (Test-Arm64FileSha256 `
                    -Path (Join-Path $moduleBase 'powershell-yaml.psm1') `
                    -Expected $script:arm64PowerShellYamlPin.ModuleSha256) -or
                (Get-Arm64DirectoryManifestSha256 -Root $moduleBase) -cne
                    $script:arm64PowerShellYamlPin.TreeManifestSha256 -or
                -not [object]::ReferenceEquals(
                    $cached.ScannerType.Assembly,
                    $cached.Assembly
                )) {
                throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
            }
            return $cached
        }
        catch {
            Close-Arm64ReadLockSet -Locks $script:arm64PowerShellYamlIdentity.Locks
            $script:arm64PowerShellYamlIdentity = $null
            throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
        }
    }

    $comparison = if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        [StringComparer]::OrdinalIgnoreCase
    }
    else {
        [StringComparer]::Ordinal
    }
    $candidates = [Collections.Generic.HashSet[string]]::new($comparison)
    $configuredManifest = [Environment]::GetEnvironmentVariable(
        'ARM64_POWERSHELL_YAML_MANIFEST'
    )
    Add-Arm64AbsoluteCandidate `
        -Candidates $candidates `
        -Path $configuredManifest

    if ([string]::IsNullOrWhiteSpace($configuredManifest) -and
        [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $localPrograms = Join-Path (
            [Environment]::GetFolderPath(
                [Environment+SpecialFolder]::LocalApplicationData
            )
        ) 'Programs'
        Add-Arm64AbsoluteCandidate `
            -Candidates $candidates `
            -Path (Join-Path $localPrograms (
                'Arm64PolicyTools\PowerShell\Modules\' +
                'powershell-yaml\0.4.12\powershell-yaml.psd1'
            ))
    }
    elseif ([string]::IsNullOrWhiteSpace($configuredManifest)) {
        Add-Arm64AbsoluteCandidate `
            -Candidates $candidates `
            -Path '/opt/arm64-policy-tools/powershell-yaml/0.4.12/powershell-yaml.psd1'
    }

    $existing = @($candidates | Where-Object {
            Test-Path -LiteralPath $_ -PathType Leaf
        })
    $approved = [Collections.Generic.List[object]]::new()
    foreach ($manifestPath in $existing) {
        try {
            $manifestPath = Resolve-Arm64CanonicalRuntimePath -Path $manifestPath
            $moduleBase = Resolve-Arm64CanonicalRuntimePath `
                -Path (Split-Path $manifestPath -Parent)
        }
        catch {
            continue
        }
        if ((Split-Path $manifestPath -Leaf) -cne 'powershell-yaml.psd1' -or
            (Split-Path $moduleBase -Leaf) -cne $script:arm64PowerShellYamlPin.Version -or
            (Split-Path (Split-Path $moduleBase -Parent) -Leaf) -cne 'powershell-yaml' -or
            -not (Test-Arm64FileSha256 `
                -Path $manifestPath `
                -Expected $script:arm64PowerShellYamlPin.ManifestSha256) -or
            -not (Test-Arm64FileSha256 `
                -Path (Join-Path $moduleBase 'powershell-yaml.psm1') `
                -Expected $script:arm64PowerShellYamlPin.ModuleSha256) -or
            (Get-Arm64DirectoryTreeSha256 -Root $moduleBase) -cne
                $script:arm64PowerShellYamlPin.TreeSha256) {
            continue
        }

        $platformPin = if ($PSVersionTable.PSEdition -ceq 'Core') {
            $script:arm64PowerShellYamlPin.Core
        }
        else {
            $script:arm64PowerShellYamlPin.Desktop
        }
        try {
            $assemblyPath = Resolve-Arm64CanonicalRuntimePath -Path (
                Join-Path $moduleBase $platformPin.AssemblyRelativePath
            )
            $serializerPath = Resolve-Arm64CanonicalRuntimePath -Path (
                Join-Path $moduleBase $platformPin.SerializerRelativePath
            )
        }
        catch {
            continue
        }
        if (-not $assemblyPath.StartsWith(
                "$([IO.Path]::GetFullPath($moduleBase))$([IO.Path]::DirectorySeparatorChar)",
                [StringComparison]::OrdinalIgnoreCase
            ) -or
            -not (Test-Arm64FileSha256 `
                -Path $assemblyPath `
                -Expected $platformPin.AssemblySha256) -or
            -not (Test-Arm64FileSha256 `
                -Path $serializerPath `
                -Expected $platformPin.SerializerSha256)) {
            continue
        }

        $locks = $null
        try {
            $locks = Open-Arm64ReadLockSet -Paths @(
                Get-ChildItem -LiteralPath $moduleBase -File -Recurse -Force |
                    ForEach-Object { $_.FullName }
            )
            if ((Get-Arm64DirectoryTreeSha256 -Root $moduleBase) -cne
                    $script:arm64PowerShellYamlPin.TreeSha256 -or
                -not (Test-Arm64FileSha256 `
                    -Path $assemblyPath `
                    -Expected $platformPin.AssemblySha256) -or
                -not (Test-Arm64FileSha256 `
                    -Path $serializerPath `
                    -Expected $platformPin.SerializerSha256)) {
                throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
            }

            $assembly = @([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object {
                    -not $_.IsDynamic -and
                    -not [string]::IsNullOrEmpty($_.Location) -and
                    [IO.Path]::GetFullPath($_.Location) -ceq $assemblyPath
                })
            if ($assembly.Count -eq 0) {
                $assembly = @([Reflection.Assembly]::LoadFile($assemblyPath))
            }
            if ($assembly.Count -ne 1) {
                throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
            }
            $assemblyName = $assembly[0].GetName()
            $publicKey = [Convert]::ToHexString(
                $assemblyName.GetPublicKey()
            ).ToLowerInvariant()
            $publicKeyToken = [Convert]::ToHexString(
                $assemblyName.GetPublicKeyToken()
            ).ToLowerInvariant()
            $scannerType = $assembly[0].GetType(
                'YamlDotNet.Core.Scanner',
                $false,
                $false
            )
            if ($assembly[0].IsDynamic -or
                $assemblyName.Name -cne 'YamlDotNet' -or
                $assemblyName.Version.ToString() -cne
                    $script:arm64PowerShellYamlPin.AssemblyVersion -or
                $publicKey -cne $script:arm64PowerShellYamlPin.AssemblyPublicKey -or
                $publicKeyToken -cne
                    $script:arm64PowerShellYamlPin.AssemblyPublicKeyToken -or
                $null -eq $scannerType -or
                -not [object]::ReferenceEquals($scannerType.Assembly, $assembly[0])) {
                throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
            }
            [void]$approved.Add([pscustomobject][ordered]@{
                    ManifestPath = $manifestPath
                    ModuleBase = $moduleBase
                    AssemblyPath = $assemblyPath
                    Assembly = $assembly[0]
                    ScannerType = $scannerType
                    Locks = $locks
                })
            $locks = $null
        }
        catch {
            Write-Verbose 'PowerShell-Yaml candidate provenance did not match.'
        }
        finally {
            Close-Arm64ReadLockSet -Locks $locks
        }
    }
    if ($approved.Count -gt 1) {
        foreach ($identity in $approved) {
            Close-Arm64ReadLockSet -Locks $identity.Locks
        }
        throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
    }
    if ($approved.Count -eq 0) {
        if ($existing.Count -gt 0) {
            throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
        }
        return $null
    }
    $script:arm64PowerShellYamlIdentity = $approved[0]
    return $script:arm64PowerShellYamlIdentity
}

function Resolve-Arm64RubyIdentity {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        return $null
    }
    if ($null -ne $script:arm64RubyIdentity) {
        try {
            $cached = $script:arm64RubyIdentity
            $executable = Resolve-Arm64CanonicalRuntimePath `
                -Path $cached.ExecutablePath
            $root = Resolve-Arm64CanonicalRuntimePath -Path $cached.Root
            if (-not $executable.StartsWith(
                    "$root$([IO.Path]::DirectorySeparatorChar)",
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                (Get-Arm64DirectoryManifestSha256 `
                    -Root (Join-Path $root 'bin')) -cne
                        $script:arm64RubyPin.BinManifestSha256 -or
                (Get-Arm64DirectoryManifestSha256 `
                    -Root (Join-Path $root 'lib\ruby\3.3.0')) -cne
                        $script:arm64RubyPin.StandardLibraryManifestSha256) {
                throw 'semantic-parser-provenance-unapproved:RubyPsych'
            }
            return $cached
        }
        catch {
            Close-Arm64ReadLockSet -Locks $script:arm64RubyIdentity.Locks
            $script:arm64RubyIdentity = $null
            throw 'semantic-parser-provenance-unapproved:RubyPsych'
        }
    }

    $candidates = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    $configuredRuby = [Environment]::GetEnvironmentVariable(
        'ARM64_RUBY_EXECUTABLE'
    )
    Add-Arm64AbsoluteCandidate `
        -Candidates $candidates `
        -Path $configuredRuby
    if ([string]::IsNullOrWhiteSpace($configuredRuby)) {
        Add-Arm64AbsoluteCandidate `
            -Candidates $candidates `
            -Path (Join-Path (
                [Environment]::GetFolderPath(
                    [Environment+SpecialFolder]::LocalApplicationData
                )
            ) 'Programs\Ruby-3.3.0-1-x64\bin\ruby.exe')
        Add-Arm64AbsoluteCandidate `
            -Candidates $candidates `
            -Path 'C:\Ruby33-x64\bin\ruby.exe'
    }

    $existing = @($candidates | Where-Object {
            Test-Path -LiteralPath $_ -PathType Leaf
        })
    $approved = [Collections.Generic.List[object]]::new()
    foreach ($executable in $existing) {
            try {
                $executable = Resolve-Arm64CanonicalRuntimePath -Path $executable
                $root = Resolve-Arm64CanonicalRuntimePath -Path (
                    Join-Path (Split-Path $executable -Parent) '..'
                )
                $binRoot = Resolve-Arm64CanonicalRuntimePath -Path (Join-Path $root 'bin')
                $libraryRoot = Resolve-Arm64CanonicalRuntimePath `
                    -Path (Join-Path $root 'lib\ruby\3.3.0')
            }
            catch {
                continue
            }
            if (-not $executable.Equals(
                    (Join-Path $binRoot 'ruby.exe'),
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                (Get-Arm64DirectoryTreeSha256 -Root $binRoot) -cne
                    $script:arm64RubyPin.BinTreeSha256 -or
                (Get-Arm64DirectoryTreeSha256 -Root $libraryRoot) -cne
                    $script:arm64RubyPin.StandardLibraryTreeSha256) {
                continue
            }

            $locks = $null
            try {
                $locks = Open-Arm64ReadLockSet -Paths @(
                    Get-ChildItem -LiteralPath $binRoot -File -Recurse -Force |
                        ForEach-Object { $_.FullName }
                    Get-ChildItem -LiteralPath $libraryRoot -File -Recurse -Force |
                        ForEach-Object { $_.FullName }
                )
                if ((Get-Arm64DirectoryTreeSha256 -Root $binRoot) -cne
                        $script:arm64RubyPin.BinTreeSha256 -or
                    (Get-Arm64DirectoryTreeSha256 -Root $libraryRoot) -cne
                        $script:arm64RubyPin.StandardLibraryTreeSha256 -or
                    (Get-Arm64DirectoryManifestSha256 -Root $binRoot) -cne
                        $script:arm64RubyPin.BinManifestSha256 -or
                    (Get-Arm64DirectoryManifestSha256 -Root $libraryRoot) -cne
                        $script:arm64RubyPin.StandardLibraryManifestSha256) {
                    throw 'semantic-parser-provenance-unapproved:RubyPsych'
                }
                [void]$approved.Add([pscustomobject][ordered]@{
                        ExecutablePath = $executable
                        Root = $root
                        BinRoot = $binRoot
                        LibraryRoot = $libraryRoot
                        Locks = $locks
                    })
                $locks = $null
            }
            catch {
                Write-Verbose 'Ruby/Psych candidate provenance did not match.'
            }
            finally {
                Close-Arm64ReadLockSet -Locks $locks
            }
        }
        if ($approved.Count -gt 1) {
            foreach ($identity in $approved) {
                Close-Arm64ReadLockSet -Locks $identity.Locks
            }
            throw 'semantic-parser-provenance-unapproved:RubyPsych'
    }
    if ($approved.Count -eq 0) {
        if ($existing.Count -gt 0) {
            throw 'semantic-parser-provenance-unapproved:RubyPsych'
        }
        return $null
    }
    $script:arm64RubyIdentity = $approved[0]
    return $script:arm64RubyIdentity
}

function Test-Arm64RubyVersionOutput {
    param([AllowNull()][byte[]]$Bytes)

    if ($null -eq $Bytes) {
        return $false
    }
    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($Bytes)
    }
    catch {
        return $false
    }
    $expected = (
        "$($script:arm64RubyPin.RubyVersion)|" +
        $script:arm64RubyPin.PsychVersion
    )
    return $text.Equals($expected, [StringComparison]::Ordinal)
}

function Get-Arm64ApprovedYamlBackends {
    if ($null -ne $script:arm64ApprovedYamlBackends) {
        return @($script:arm64ApprovedYamlBackends)
    }
    $backends = [Collections.Generic.List[string]]::new()
    try {
        if ($null -ne (Resolve-Arm64PowerShellYamlIdentity)) {
            [void]$backends.Add('PowerShellYaml')
        }
    }
    catch {
        Write-Verbose 'PowerShell-Yaml provenance is not approved.'
    }
    try {
        $ruby = Resolve-Arm64RubyIdentity
        if ($null -ne $ruby) {
            $versions = Invoke-Arm64BoundedProcess `
                -FilePath $ruby.ExecutablePath `
                -ArgumentList @(
                    '--disable-gems',
                    '--disable-did_you_mean',
                    '--disable-error_highlight',
                    '-rpsych',
                    '-e',
                    'STDOUT.write("#{RUBY_VERSION}|#{Psych::VERSION}")'
                ) `
                -InputBytes ([byte[]]::new(0)) `
                -MaximumOutputBytes 128 `
                -MaximumErrorBytes 1024 `
                -TimeoutMilliseconds 10000
            if ($versions.ExitCode -eq 0 -and
                (Test-Arm64RubyVersionOutput -Bytes $versions.OutputBytes)) {
                [void]$backends.Add('RubyPsych')
            }
        }
    }
    catch {
        Write-Verbose 'Ruby/Psych provenance or version is not approved.'
    }
    $script:arm64ApprovedYamlBackends = [string[]]@($backends)
    return @($script:arm64ApprovedYamlBackends)
}

function Resolve-Arm64YamlBackend {
    param([Parameter(Mandatory)][string]$Requested)

    if ($Requested -ceq 'Unavailable') {
        throw 'semantic-parser-unavailable'
    }
    $approved = @(Get-Arm64ApprovedYamlBackends)
    if ($Requested -ceq 'PowerShellYaml') {
        try {
            $identity = Resolve-Arm64PowerShellYamlIdentity
        }
        catch {
            throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
        }
        if ($null -eq $identity) {
            throw 'semantic-parser-unavailable'
        }
        if ($approved -cnotcontains 'PowerShellYaml') {
            throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
        }
    }
    if ($Requested -ceq 'RubyPsych') {
        try {
            $ruby = Resolve-Arm64RubyIdentity
        }
        catch {
            throw 'semantic-parser-provenance-unapproved:RubyPsych'
        }
        if ($null -eq $ruby) {
            throw 'semantic-parser-unavailable'
        }
        if ($approved -cnotcontains 'RubyPsych') {
            throw 'semantic-parser-version-unapproved:RubyPsych'
        }
    }
    if (($approved -join ',') -cne 'PowerShellYaml,RubyPsych') {
        throw 'semantic-parser-unavailable'
    }
    if ($Requested -ceq 'Auto') {
        return 'PowerShellYaml'
    }
    return $Requested
}

# Deliberate, policy-defined YAML rejection codes. Only these constants may be surfaced to
# an audit caller, so candidate-controlled backend text can never reach the error stream.
$script:arm64DeliberateYamlCodes = @(
    'semantic-yaml-byte-limit-exceeded',
    'semantic-yaml-bom-forbidden',
    'semantic-yaml-utf8-invalid',
    'semantic-yaml-nul-forbidden',
    'semantic-yaml-explicit-document-marker-forbidden',
    'semantic-yaml-anchor-alias-merge-forbidden',
    'semantic-yaml-token-scanner-unavailable',
    'semantic-yaml-token-scan-failed',
    'semantic-yaml-token-scan-timeout',
    'semantic-yaml-token-limit-exceeded',
    'semantic-yaml-backend-parse-failed',
    'semantic-parser-differential',
    'semantic-parser-helper-missing',
    'semantic-parser-unavailable',
    'semantic-parser-provenance-unapproved',
    'semantic-parser-version-unapproved',
    'semantic-parser-version-output-invalid',
    'semantic-parser-input-limit-exceeded',
    'semantic-parser-output-limit-exceeded',
    'semantic-parser-timeout',
    'semantic-parser-containment-unavailable',
    'semantic-parser-transport-failed'
)

# Bounds for the non-composing token scan. A malformed stream can make the scanner emit an
# unbounded run of Error tokens, so the scan is capped by both token count and wall clock.
$script:arm64YamlMaximumTokens = 200000
$script:arm64YamlScanTimeoutMilliseconds = 15000

# Counts every object-backend invocation so tests can prove a forbidden token never reaches
# a backend.
$script:arm64BackendInvocationCount = 0

function Resolve-Arm64YamlErrorCode {
    param(
        [AllowNull()][object]$ErrorRecord,
        [Parameter(Mandatory)][string]$Relative
    )

    $message = ''
    if ($null -ne $ErrorRecord -and $null -ne $ErrorRecord.Exception) {
        $message = [string]$ErrorRecord.Exception.Message
    }
    $separator = $message.IndexOf(':', [StringComparison]::Ordinal)
    $code = if ($separator -lt 0) { $message } else { $message.Substring(0, $separator) }
    if ($script:arm64DeliberateYamlCodes -ccontains $code) {
        return "${code}:$Relative"
    }
    return "semantic-yaml-parse-failed:$Relative"
}

function Resolve-Arm64ParserSelectionErrorCode {
    param([AllowNull()][object]$ErrorRecord)

    $message = ''
    if ($null -ne $ErrorRecord -and $null -ne $ErrorRecord.Exception) {
        $message = [string]$ErrorRecord.Exception.Message
    }
    $separator = $message.IndexOf(':', [StringComparison]::Ordinal)
    $code = if ($separator -lt 0) { $message } else { $message.Substring(0, $separator) }
    if ($script:arm64DeliberateYamlCodes -ccontains $code -and
        $code.StartsWith('semantic-parser-', [StringComparison]::Ordinal)) {
        return $code
    }
    return 'semantic-parser-unavailable'
}

function Resolve-Arm64YamlScannerType {
    try {
        $identity = Resolve-Arm64PowerShellYamlIdentity
        if ($null -eq $identity -or
            $null -eq $identity.ScannerType -or
            -not [object]::ReferenceEquals(
                $identity.ScannerType.Assembly,
                $identity.Assembly
            )) {
            return $null
        }
        return $identity.ScannerType
    }
    catch {
        return $null
    }
}

function Assert-Arm64YamlTokenPolicy {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text)

    $scannerType = Resolve-Arm64YamlScannerType
    if ($null -eq $scannerType) {
        # No trustworthy token layer means no admission decision can be made safely.
        throw 'semantic-yaml-token-scanner-unavailable'
    }

    $reader = [IO.StringReader]::new($Text)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        try {
            $scanner = [Activator]::CreateInstance(
                $scannerType,
                [object[]]@([IO.TextReader]$reader, $true)
            )
        }
        catch {
            throw 'semantic-yaml-token-scanner-unavailable'
        }

        $count = 0
        $previousKind = $null
        while ($true) {
            if ($timer.ElapsedMilliseconds -gt $script:arm64YamlScanTimeoutMilliseconds) {
                throw 'semantic-yaml-token-scan-timeout'
            }
            $advanced = $false
            try {
                $advanced = $scanner.MoveNext()
            }
            catch {
                # A malformed stream is not classifiable, so it is refused rather than handed
                # to an object backend.
                throw 'semantic-yaml-token-scan-failed'
            }
            if (-not $advanced) {
                break
            }

            $count++
            if ($count -gt $script:arm64YamlMaximumTokens) {
                throw 'semantic-yaml-token-limit-exceeded'
            }
            if ($timer.ElapsedMilliseconds -gt $script:arm64YamlScanTimeoutMilliseconds) {
                throw 'semantic-yaml-token-scan-timeout'
            }

            $token = $scanner.Current
            $kind = $token.GetType().Name
            if ($kind -ceq 'Anchor' -or $kind -ceq 'AnchorAlias') {
                throw 'semantic-yaml-anchor-alias-merge-forbidden'
            }
            if ($kind -ceq 'DocumentStart' -or $kind -ceq 'DocumentEnd') {
                throw 'semantic-yaml-explicit-document-marker-forbidden'
            }
            if ($kind -ceq 'Error') {
                throw 'semantic-yaml-token-scan-failed'
            }
            if ($kind -ceq 'Scalar' -and
                [string]$token.Value -ceq '<<' -and
                [string]$token.Style -ceq 'Plain' -and
                $previousKind -ceq 'Key') {
                throw 'semantic-yaml-anchor-alias-merge-forbidden'
            }
            if ($kind -cne 'Tag') {
                $previousKind = $kind
            }
        }
    }
    finally {
        $timer.Stop()
        $reader.Dispose()
    }
}
function Get-Arm64YamlText {
    param([Parameter(Mandatory)][string]$Path)

    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.LongLength -gt 1048576) {
        throw 'semantic-yaml-byte-limit-exceeded'
    }
    if (($bytes.Length -ge 2 -and
            (($bytes[0] -eq 0xff -and $bytes[1] -eq 0xfe) -or
                ($bytes[0] -eq 0xfe -and $bytes[1] -eq 0xff))) -or
        ($bytes.Length -ge 3 -and $bytes[0] -eq 0xef -and
            $bytes[1] -eq 0xbb -and $bytes[2] -eq 0xbf)) {
        throw 'semantic-yaml-bom-forbidden'
    }
    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    }
    catch {
        throw 'semantic-yaml-utf8-invalid'
    }
    if ($text.Contains("`0", [StringComparison]::Ordinal)) {
        throw 'semantic-yaml-nul-forbidden'
    }
    Assert-Arm64YamlTokenPolicy -Text $text
    return $text
}

function Read-Arm64BoundedStreamPair {
    param(
        [Parameter(Mandatory)][IO.Stream]$Primary,
        [Parameter(Mandatory)][IO.Stream]$Secondary,
        [Parameter(Mandatory)][int]$PrimaryLimit,
        [Parameter(Mandatory)][int]$SecondaryLimit,
        [Parameter(Mandatory)][Diagnostics.Stopwatch]$Timer,
        [Parameter(Mandatory)][int]$TimeoutMilliseconds
    )

    $streams = @($Primary, $Secondary)
    $limits = @($PrimaryLimit, $SecondaryLimit)
    $buffers = @([byte[]]::new(8192), [byte[]]::new(8192))
    $sinks = @([IO.MemoryStream]::new(), [IO.MemoryStream]::new())
    $tasks = [object[]]::new(2)
    try {
        for ($slot = 0; $slot -lt 2; $slot++) {
            $tasks[$slot] = $streams[$slot].ReadAsync($buffers[$slot], 0, $buffers[$slot].Length)
        }
        while ($null -ne $tasks[0] -or $null -ne $tasks[1]) {
            $activeSlots = @(0, 1 | Where-Object { $null -ne $tasks[$_] })
            $activeTasks = [Threading.Tasks.Task[]]@($activeSlots | ForEach-Object { $tasks[$_] })
            $remaining = $TimeoutMilliseconds - [int]$Timer.ElapsedMilliseconds
            if ($remaining -le 0) {
                throw 'semantic-parser-timeout'
            }
            $completed = [Threading.Tasks.Task]::WaitAny($activeTasks, $remaining)
            if ($completed -lt 0) {
                throw 'semantic-parser-timeout'
            }
            $slot = $activeSlots[$completed]
            $read = $tasks[$slot].GetAwaiter().GetResult()
            if ($read -le 0) {
                $tasks[$slot] = $null
                continue
            }
            if ($sinks[$slot].Length + $read -gt $limits[$slot]) {
                throw 'semantic-parser-output-limit-exceeded'
            }
            $sinks[$slot].Write($buffers[$slot], 0, $read)
            $tasks[$slot] = $streams[$slot].ReadAsync($buffers[$slot], 0, $buffers[$slot].Length)
        }
        return [pscustomobject]@{
            Primary   = $sinks[0].ToArray()
            Secondary = $sinks[1].ToArray()
        }
    }
    finally {
        $sinks[0].Dispose()
        $sinks[1].Dispose()
    }
}

function New-Arm64ProcessContainment {
    param(
        [Parameter(Mandatory)][uint64]$MaximumProcessMemoryBytes,
        [Parameter(Mandatory)][uint64]$MaximumJobMemoryBytes
    )

    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'semantic-parser-containment-unavailable'
    }
    if ($null -eq ('Arm64PolicyRuntime.JobScope' -as [type])) {
        try {
            Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Arm64PolicyRuntime
{
    public sealed class JobScope : IDisposable
    {
        private const uint JobObjectExtendedLimitInformation = 9;
        private const uint JobObjectLimitProcessMemory = 0x00000100;
        private const uint JobObjectLimitJobMemory = 0x00000200;
        private const uint JobObjectLimitKillOnJobClose = 0x00002000;

        [StructLayout(LayoutKind.Sequential)]
        private struct IoCounters
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct BasicLimitInformation
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ExtendedLimitInformation
        {
            public BasicLimitInformation BasicLimitInformation;
            public IoCounters IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr CreateJobObject(IntPtr jobAttributes, string name);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetInformationJobObject(
            IntPtr job,
            uint informationClass,
            IntPtr information,
            uint informationLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        private readonly SafeFileHandle job;

        public JobScope(ulong processMemoryLimit, ulong jobMemoryLimit)
        {
            IntPtr raw = CreateJobObject(IntPtr.Zero, null);
            if (raw == IntPtr.Zero)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            job = new SafeFileHandle(raw, true);
            ExtendedLimitInformation limits = new ExtendedLimitInformation();
            limits.BasicLimitInformation.LimitFlags =
                JobObjectLimitProcessMemory |
                JobObjectLimitJobMemory |
                JobObjectLimitKillOnJobClose;
            limits.ProcessMemoryLimit = new UIntPtr(processMemoryLimit);
            limits.JobMemoryLimit = new UIntPtr(jobMemoryLimit);
            int size = Marshal.SizeOf<ExtendedLimitInformation>();
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try
            {
                Marshal.StructureToPtr(limits, buffer, false);
                if (!SetInformationJobObject(
                    job.DangerousGetHandle(),
                    JobObjectExtendedLimitInformation,
                    buffer,
                    (uint)size))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
            }
            catch
            {
                job.Dispose();
                throw;
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }

        public void Assign(Process process)
        {
            if (process == null)
            {
                throw new ArgumentNullException(nameof(process));
            }
            if (!AssignProcessToJobObject(job.DangerousGetHandle(), process.Handle))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
        }

        public void Dispose()
        {
            job.Dispose();
        }
    }
}
'@
        }
        catch {
            throw 'semantic-parser-containment-unavailable'
        }
    }
    try {
        return [Arm64PolicyRuntime.JobScope]::new(
            $MaximumProcessMemoryBytes,
            $MaximumJobMemoryBytes
        )
    }
    catch {
        throw 'semantic-parser-containment-unavailable'
    }
}

function Invoke-Arm64BoundedProcess {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$ArgumentList,
        [Parameter(Mandatory)][AllowEmptyCollection()][byte[]]$InputBytes,
        [int]$MaximumInputBytes = 1048576,
        [int]$MaximumOutputBytes = 4194304,
        [int]$MaximumErrorBytes = 65536,
        [int]$TimeoutMilliseconds = 60000,
        [uint64]$MaximumProcessMemoryBytes = 268435456,
        [uint64]$MaximumJobMemoryBytes = 402653184
    )

    if (-not [IO.Path]::IsPathFullyQualified($FilePath) -or
        -not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw 'semantic-parser-provenance-unapproved'
    }
    if ($InputBytes.LongLength -gt $MaximumInputBytes) {
        throw 'semantic-parser-input-limit-exceeded'
    }
    if ($MaximumProcessMemoryBytes -lt 67108864 -or
        $MaximumJobMemoryBytes -lt $MaximumProcessMemoryBytes) {
        throw 'semantic-parser-containment-unavailable'
    }

    $targetConfiguration = [ordered]@{
        FilePath = [IO.Path]::GetFullPath($FilePath)
        ArgumentList = [string[]]@($ArgumentList)
    }
    $configurationBase64 = [Convert]::ToBase64String(
        [Text.UTF8Encoding]::new($false, $true).GetBytes((
                $targetConfiguration | ConvertTo-Json -Compress -Depth 4
            ))
    )
    # The trusted wrapper blocks on standard input. It cannot start the requested target until
    # the parent has assigned the wrapper to the kill-on-close Job Object.
    $wrapperScript = @'
$ErrorActionPreference = 'Stop'
try {
    $configurationText = [Text.UTF8Encoding]::new($false, $true).GetString(
        [Convert]::FromBase64String('__CONFIGURATION__')
    )
    $configuration = $configurationText | ConvertFrom-Json -Depth 4
    $standardInput = [Console]::OpenStandardInput()
    $collected = [IO.MemoryStream]::new()
    try {
        $buffer = [byte[]]::new(8192)
        while (($read = $standardInput.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($collected.Length + $read -gt __MAXIMUM_INPUT_BYTES__) {
                [Environment]::Exit(251)
            }
            $collected.Write($buffer, 0, $read)
        }
        $inputBytes = $collected.ToArray()
    }
    finally {
        $collected.Dispose()
    }

    $targetInfo = [Diagnostics.ProcessStartInfo]::new()
    $targetInfo.FileName = [string]$configuration.FilePath
    foreach ($argument in @($configuration.ArgumentList)) {
        $targetInfo.ArgumentList.Add([string]$argument)
    }
    $targetInfo.RedirectStandardInput = $true
    $targetInfo.RedirectStandardOutput = $true
    $targetInfo.RedirectStandardError = $true
    $targetInfo.UseShellExecute = $false
    $targetInfo.CreateNoWindow = $true
    $targetInfo.WorkingDirectory = [IO.Path]::GetTempPath()
    $targetInfo.Environment.Clear()
    foreach ($name in @(
            'SystemRoot',
            'windir',
            'TEMP',
            'TMP',
            'NUMBER_OF_PROCESSORS',
            'PROCESSOR_ARCHITECTURE',
            'COMSPEC',
            'DOTNET_CLI_TELEMETRY_OPTOUT',
            'POWERSHELL_TELEMETRY_OPTOUT',
            'POWERSHELL_UPDATECHECK')) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrEmpty($value)) {
            $targetInfo.Environment[$name] = $value
        }
    }

    $target = [Diagnostics.Process]::new()
    $target.StartInfo = $targetInfo
    try {
        [void]$target.Start()
        $output = [Console]::OpenStandardOutput()
        $errorOutput = [Console]::OpenStandardError()
        $outputTask = $target.StandardOutput.BaseStream.CopyToAsync($output)
        $errorTask = $target.StandardError.BaseStream.CopyToAsync($errorOutput)
        $writeTask = $target.StandardInput.BaseStream.WriteAsync(
            $inputBytes,
            0,
            $inputBytes.Length
        )
        [void]$writeTask.GetAwaiter().GetResult()
        $target.StandardInput.Close()
        $target.WaitForExit()
        [Threading.Tasks.Task]::WaitAll(
            [Threading.Tasks.Task[]]@($outputTask, $errorTask)
        )
        $output.Flush()
        $errorOutput.Flush()
        $exitCode = $target.ExitCode
    }
    finally {
        if (-not $target.HasExited) {
            $target.Kill($true)
        }
        $target.Dispose()
    }
    [Environment]::Exit($exitCode)
}
catch {
    [Environment]::Exit(252)
}
'@
    $wrapperScript = $wrapperScript.Replace(
        '__CONFIGURATION__',
        $configurationBase64
    ).Replace(
        '__MAXIMUM_INPUT_BYTES__',
        ([string]$MaximumInputBytes)
    )
    $encodedWrapper = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($wrapperScript)
    )

    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Process -Id $PID).Path
    foreach ($argument in @(
            '-NoLogo',
            '-NoProfile',
            '-NonInteractive',
            '-EncodedCommand',
            $encodedWrapper)) {
        $startInfo.ArgumentList.Add($argument)
    }
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WorkingDirectory = [IO.Path]::GetTempPath()

    # The child runs with a scrubbed environment: only the variables needed to start a shell
    # are forwarded, so ambient proxy, Git, culture, or module-path settings cannot reach the
    # parser or redirect anything it does.
    $startInfo.Environment.Clear()
    foreach ($name in @('SystemRoot', 'windir', 'TEMP', 'TMP',
            'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'COMSPEC')) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrEmpty($value)) {
            $startInfo.Environment[$name] = $value
        }
    }
    $startInfo.Environment['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    $startInfo.Environment['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
    $startInfo.Environment['POWERSHELL_UPDATECHECK'] = 'Off'

    $timer = [Diagnostics.Stopwatch]::StartNew()
    $process = [Diagnostics.Process]::new()
    $containment = New-Arm64ProcessContainment `
        -MaximumProcessMemoryBytes $MaximumProcessMemoryBytes `
        -MaximumJobMemoryBytes $MaximumJobMemoryBytes
    $process.StartInfo = $startInfo
    try {
        try {
            [void]$process.Start()
            $containment.Assign($process)
        }
        catch {
            try {
                if (-not $process.HasExited) {
                    $process.Kill($true)
                }
            }
            catch {
                Write-Verbose 'Uncontained parser process could not be terminated.'
            }
            throw 'semantic-parser-containment-unavailable'
        }
        try {
            $inputStream = $process.StandardInput.BaseStream
            $inputStream.Write($InputBytes, 0, $InputBytes.Length)
            $inputStream.Flush()
            $process.StandardInput.Close()
        }
        catch {
            throw 'semantic-parser-transport-failed'
        }

        $streams = Read-Arm64BoundedStreamPair `
            -Primary $process.StandardOutput.BaseStream `
            -Secondary $process.StandardError.BaseStream `
            -PrimaryLimit $MaximumOutputBytes `
            -SecondaryLimit $MaximumErrorBytes `
            -Timer $timer `
            -TimeoutMilliseconds $TimeoutMilliseconds

        $remaining = $TimeoutMilliseconds - [int]$timer.ElapsedMilliseconds
        if ($remaining -le 0 -or -not $process.WaitForExit($remaining)) {
            throw 'semantic-parser-timeout'
        }
        return [pscustomobject]@{
            ExitCode     = [int]$process.ExitCode
            OutputBytes  = $streams.Primary
            ErrorBytes   = $streams.Secondary
            Containment  = 'WindowsJob'
            ProcessMemoryLimitBytes = $MaximumProcessMemoryBytes
            JobMemoryLimitBytes = $MaximumJobMemoryBytes
        }
    }
    finally {
        $timer.Stop()
        try {
            if (-not $process.HasExited) {
                $process.Kill($true)
            }
        }
        catch {
            Write-Verbose 'Bounded parser process could not be inspected or terminated.'
        }
        $containment.Dispose()
        $process.Dispose()
    }
}

function Assert-Arm64JsonElementHasUniqueProperties {
    param([Parameter(Mandatory)][Text.Json.JsonElement]$Element)

    if ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Object) {
        $names = [Collections.Generic.HashSet[string]]::new(
            [StringComparer]::OrdinalIgnoreCase
        )
        foreach ($property in $Element.EnumerateObject()) {
            if (-not $names.Add($property.Name)) {
                throw 'semantic-yaml-backend-parse-failed'
            }
            Assert-Arm64JsonElementHasUniqueProperties -Element $property.Value
        }
    }
    elseif ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Array) {
        foreach ($item in $Element.EnumerateArray()) {
            Assert-Arm64JsonElementHasUniqueProperties -Element $item
        }
    }
}

function ConvertFrom-Arm64StrictBackendJson {
    param([Parameter(Mandatory)][AllowEmptyCollection()][byte[]]$Bytes)

    try {
        $json = [Text.UTF8Encoding]::new($false, $true).GetString($Bytes)
    }
    catch {
        throw 'semantic-yaml-backend-parse-failed'
    }
    if ([string]::IsNullOrWhiteSpace($json) -or
        ($json.Length -gt 0 -and $json[0] -eq [char]0xfeff)) {
        throw 'semantic-yaml-backend-parse-failed'
    }

    $options = [Text.Json.JsonDocumentOptions]::new()
    $options.AllowTrailingCommas = $false
    $options.CommentHandling = [Text.Json.JsonCommentHandling]::Disallow
    $options.MaxDepth = 64
    try {
        $document = [Text.Json.JsonDocument]::Parse($json, $options)
        try {
            Assert-Arm64JsonElementHasUniqueProperties -Element $document.RootElement
        }
        finally {
            $document.Dispose()
        }
        return ConvertFrom-Json `
            -InputObject $json `
            -Depth 64 `
            -NoEnumerate `
            -ErrorAction Stop
    }
    catch {
        throw 'semantic-yaml-backend-parse-failed'
    }
}

function Open-Arm64ReadLockSet {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [string[]]$Paths
    )

    $comparison = if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        [StringComparer]::OrdinalIgnoreCase
    }
    else {
        [StringComparer]::Ordinal
    }
    $unique = [Collections.Generic.HashSet[string]]::new($comparison)
    foreach ($path in $Paths) {
        if (-not [IO.Path]::IsPathFullyQualified($path) -or
            -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'semantic-parser-provenance-unapproved'
        }
        [void]$unique.Add([IO.Path]::GetFullPath($path))
    }
    $ordered = [string[]]@($unique)
    [Array]::Sort($ordered, $comparison)
    $locks = [Collections.Generic.List[IO.FileStream]]::new()
    try {
        foreach ($path in $ordered) {
            [void]$locks.Add([IO.File]::Open(
                    $path,
                    [IO.FileMode]::Open,
                    [IO.FileAccess]::Read,
                    [IO.FileShare]::Read
                ))
        }
        return , $locks
    }
    catch {
        foreach ($stream in $locks) {
            $stream.Dispose()
        }
        throw 'semantic-parser-provenance-unapproved'
    }
}

function Close-Arm64ReadLockSet {
    param([AllowNull()][object]$Locks)

    if ($null -ne $Locks) {
        foreach ($stream in $Locks) {
            $stream.Dispose()
        }
    }
}

function Invoke-Arm64YamlBackend {
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Text,
        [Parameter(Mandatory)]
        [ValidateSet('PowerShellYaml', 'RubyPsych')]
        [string]$Backend
    )

    # Every object backend runs as a bounded child process on validated bytes. Nothing in this
    # process ever composes a candidate document, so alias expansion cannot consume the audit.
    $script:arm64BackendInvocationCount++
    $inputBytes = [Text.UTF8Encoding]::new($false, $true).GetBytes($Text)

    $runtimeLocks = $null
    try {
        if ($Backend -ceq 'PowerShellYaml') {
            $helperPath = Join-Path $PSScriptRoot 'parse-yaml.ps1'
            if (-not (Test-Arm64FileSha256 `
                    -Path $helperPath `
                    -Expected $script:arm64ParserHelperPins.PowerShell)) {
                throw 'semantic-parser-helper-missing'
            }
            try {
                $module = Resolve-Arm64PowerShellYamlIdentity
            }
            catch {
                throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
            }
            if ($null -eq $module) {
                throw 'semantic-parser-unavailable'
            }
            $runtimeLocks = Open-Arm64ReadLockSet -Paths @(
                $helperPath
                Get-ChildItem -LiteralPath $module.ModuleBase -File -Recurse -Force |
                    ForEach-Object { $_.FullName }
            )
            if (-not (Test-Arm64FileSha256 `
                    -Path $helperPath `
                    -Expected $script:arm64ParserHelperPins.PowerShell)) {
                throw 'semantic-parser-helper-missing'
            }
            try {
                $module = Resolve-Arm64PowerShellYamlIdentity
            }
            catch {
                throw 'semantic-parser-provenance-unapproved:PowerShellYaml'
            }
            $shell = @(Get-Process -Id $PID).Path
            if ([string]::IsNullOrWhiteSpace($shell)) {
                throw 'semantic-parser-unavailable'
            }
            $result = Invoke-Arm64BoundedProcess `
                -FilePath $shell `
                -ArgumentList @(
                    '-NoProfile',
                    '-NonInteractive',
                    '-ExecutionPolicy', 'Bypass',
                    '-File', $helperPath,
                    '-ModuleManifest', $module.ManifestPath
                ) `
                -InputBytes $inputBytes
        }
        else {
            $parserPath = Join-Path $PSScriptRoot 'parse-yaml.rb'
            if (-not (Test-Arm64FileSha256 `
                    -Path $parserPath `
                    -Expected $script:arm64ParserHelperPins.Ruby)) {
                throw 'semantic-parser-helper-missing'
            }
            try {
                $ruby = Resolve-Arm64RubyIdentity
            }
            catch {
                throw 'semantic-parser-provenance-unapproved:RubyPsych'
            }
            if ($null -eq $ruby) {
                throw 'semantic-parser-unavailable'
            }
            $runtimeLocks = Open-Arm64ReadLockSet -Paths @(
                $parserPath
                $ruby.ExecutablePath
                Join-Path $ruby.Root 'bin\x64-ucrt-ruby330.dll'
                Join-Path $ruby.Root 'bin\ruby_builtin_dlls\libyaml-0-2.dll'
                Join-Path $ruby.Root 'lib\ruby\3.3.0\x64-mingw-ucrt\psych.so'
                Join-Path $ruby.Root 'lib\ruby\3.3.0\psych.rb'
                Get-ChildItem `
                    -LiteralPath (Join-Path $ruby.Root 'lib\ruby\3.3.0\psych') `
                    -File `
                    -Recurse |
                    ForEach-Object { $_.FullName }
                Get-ChildItem `
                    -LiteralPath (Join-Path $ruby.Root 'lib\ruby\3.3.0\json') `
                    -File `
                    -Recurse |
                    ForEach-Object { $_.FullName }
                Get-ChildItem `
                    -LiteralPath (Join-Path $ruby.Root (
                        'lib\ruby\3.3.0\x64-mingw-ucrt\json'
                    )) `
                    -File `
                    -Recurse |
                    ForEach-Object { $_.FullName }
            )
            if (-not (Test-Arm64FileSha256 `
                    -Path $parserPath `
                    -Expected $script:arm64ParserHelperPins.Ruby)) {
                throw 'semantic-parser-helper-missing'
            }
            try {
                $ruby = Resolve-Arm64RubyIdentity
            }
            catch {
                throw 'semantic-parser-provenance-unapproved:RubyPsych'
            }
            $result = Invoke-Arm64BoundedProcess `
                -FilePath $ruby.ExecutablePath `
                -ArgumentList @(
                    '--disable-gems',
                    '--disable-did_you_mean',
                    '--disable-error_highlight',
                    $parserPath
                ) `
                -InputBytes $inputBytes
        }
    }
    finally {
        Close-Arm64ReadLockSet -Locks $runtimeLocks
    }

    if ($result.ExitCode -ne 0) {
        throw 'semantic-yaml-backend-parse-failed'
    }
    return ConvertFrom-Arm64StrictBackendJson -Bytes $result.OutputBytes
}

function ConvertTo-Arm64CanonicalJson {
    param([AllowNull()][object]$Value)

    # Key order is not semantic and is not stable across backends or hashtable enumerations,
    # so the cross-backend differential compares a canonical, key-sorted rendering.
    if ($null -eq $Value) {
        return 'null'
    }
    if ($Value -is [string]) {
        return $Value | ConvertTo-Json -Compress -Depth 2
    }
    if ($Value -is [Collections.IDictionary]) {
        $parts = @(@($Value.Keys | ForEach-Object { [string]$_ } | Sort-Object -CaseSensitive) |
                ForEach-Object {
                    ($_ | ConvertTo-Json -Compress -Depth 2) + ':' +
                    (ConvertTo-Arm64CanonicalJson -Value $Value[$_])
                })
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [psobject] -and $null -ne $Value.PSObject.Properties -and
        @($Value.PSObject.Properties).Count -gt 0 -and
        $Value -isnot [Collections.IEnumerable] -and
        $Value.GetType().Name -ceq 'PSCustomObject') {
        $parts = @(@($Value.PSObject.Properties | Sort-Object -Property Name -CaseSensitive) |
                ForEach-Object {
                    ($_.Name | ConvertTo-Json -Compress -Depth 2) + ':' +
                    (ConvertTo-Arm64CanonicalJson -Value $_.Value)
                })
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [Collections.IEnumerable]) {
        $parts = @(@($Value) | ForEach-Object { ConvertTo-Arm64CanonicalJson -Value $_ })
        return '[' + ($parts -join ',') + ']'
    }
    return $Value | ConvertTo-Json -Compress -Depth 2
}

function ConvertFrom-Arm64YamlFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Backend
    )

    $text = Get-Arm64YamlText -Path $Path
    $document = Invoke-Arm64YamlBackend -Text $text -Backend $Backend
    $approved = @(Get-Arm64ApprovedYamlBackends)
    if (($approved -join ',') -cne 'PowerShellYaml,RubyPsych') {
        throw 'semantic-parser-unavailable'
    }
    $representations = @(
        @(
            ConvertTo-Arm64CanonicalJson -Value $document
            foreach ($otherBackend in $approved) {
                if ($otherBackend -cne $Backend) {
                    ConvertTo-Arm64CanonicalJson -Value (
                        Invoke-Arm64YamlBackend -Text $text -Backend $otherBackend
                    )
                }
            }
        ) | Sort-Object -Unique -CaseSensitive
    )
    if ($representations.Count -ne 1) {
        throw "semantic-parser-differential:$Path"
    }
    return $document
}

function Get-Arm64GitBlobHash {
    param([Parameter(Mandatory)][string]$Path)

    return (Get-Arm64FileBlobIdentity -Path $Path).oid
}

function Get-Arm64Sha256Text {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text)

    # Identity is the exact UTF-8 bytes of the run body as the parser produced it. Nothing is
    # trimmed and no line ending is normalized, so leading and trailing whitespace, a terminal
    # newline, and CRLF versus LF each produce a distinct identity.
    return -join (
        [Security.Cryptography.SHA256]::HashData(
            [Text.UTF8Encoding]::new($false, $true).GetBytes($Text)
        ) | ForEach-Object { $_.ToString('x2') }
    )
}

function Resolve-Arm64DataPath {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$RelativePath
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath) -or
        $RelativePath -match '^(?:[A-Za-z]:|/|\\)' -or
        $RelativePath -match '(?:^|[\\/])\.\.(?:[\\/]|$)') {
        throw "local-path-invalid:$RelativePath"
    }
    $normalized = $RelativePath.Replace('/', [IO.Path]::DirectorySeparatorChar).
        Replace('\', [IO.Path]::DirectorySeparatorChar)
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $resolved = [IO.Path]::GetFullPath((Join-Path $rootFull $normalized))
    if (-not $resolved.StartsWith(
            "$rootFull$([IO.Path]::DirectorySeparatorChar)",
            [StringComparison]::Ordinal)) {
        throw "local-path-escape:$RelativePath"
    }
    return $resolved
}

function Test-Arm64AuthoritativeSnapshot {
    param([Parameter(Mandatory)][string]$Root)

    $snapshotPath = Join-Path $Root 'authoritative-snapshot.json'
    if (-not (Test-Path -LiteralPath $snapshotPath -PathType Leaf)) {
        throw 'authoritative-snapshot-missing'
    }
    $snapshot = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json -Depth 64
    $snapshotProperties = @($snapshot.PSObject.Properties.Name | Sort-Object)
    $expectedSnapshotProperties = @(
        'authority',
        'repository',
        'commit',
        'tree',
        'complete',
        'files'
    ) | Sort-Object
    if (($snapshotProperties -join "`0") -cne ($expectedSnapshotProperties -join "`0") -or
        $snapshot.authority -cne 'github-rest-api' -or
        $snapshot.complete -isnot [bool] -or -not $snapshot.complete -or
        $snapshot.repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' -or
        -not (Test-Arm64GitObjectId $snapshot.commit) -or
        -not (Test-Arm64GitObjectId $snapshot.tree) -or
        $snapshot.files -is [string] -or
        $snapshot.files -isnot [Collections.IEnumerable]) {
        throw 'authoritative-snapshot-invalid'
    }

    $expectedPaths = [Collections.Generic.List[string]]::new()
    $exactPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $aliasPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($file in @($snapshot.files)) {
        Assert-Arm64SourceBinding -Binding $file -Label 'authoritative snapshot file'
        if (-not $exactPaths.Add([string]$file.path)) {
            throw "authoritative-snapshot-duplicate-path:$($file.path)"
        }
        $aliasKey = ([string]$file.path).Normalize(
            [Text.NormalizationForm]::FormC
        ).ToUpperInvariant()
        if (-not $aliasPaths.Add($aliasKey)) {
            throw "authoritative-snapshot-path-alias:$($file.path)"
        }
        [void]$expectedPaths.Add([string]$file.path)
    }
    $expectedPaths = @($expectedPaths | Sort-Object)
    $actualPaths = @(Get-ChildItem -LiteralPath $Root -File -Recurse -Force | Where-Object {
            $_.FullName -cne $snapshotPath
        } | ForEach-Object {
            $_.FullName.Substring([IO.Path]::GetFullPath($Root).Length + 1).
                Replace([IO.Path]::DirectorySeparatorChar, '/')
        } | Sort-Object)
    if (($expectedPaths -join "`0") -cne ($actualPaths -join "`0")) {
        throw 'authoritative-snapshot-file-set-mismatch'
    }
    foreach ($file in $snapshot.files) {
        $path = Resolve-Arm64DataPath -Root $Root -RelativePath $file.path
        $identity = Get-Arm64FileBlobIdentity -Path $path
        $actualBinding = New-Arm64SourceBinding `
            -Path $file.path `
            -Mode $file.mode `
            -ObjectType 'blob' `
            -ByteLength $identity.byte_length `
            -Oid $identity.oid
        if (-not (Test-Arm64SourceBindingEqual -Expected $file -Actual $actualBinding)) {
            throw "authoritative-snapshot-source-binding-mismatch:$($file.path)"
        }
    }
    return $snapshot
}

function Resolve-Arm64AuthoritativeSnapshotErrorCode {
    param([AllowNull()][object]$ErrorRecord)

    $message = ''
    if ($null -ne $ErrorRecord -and $null -ne $ErrorRecord.Exception) {
        $message = [string]$ErrorRecord.Exception.Message
    }
    if ($message -cmatch '^authoritative-snapshot-(?:missing|invalid|file-set-mismatch)$' -or
        $message -cmatch '^authoritative-snapshot-(?:duplicate-path|path-alias|source-binding-mismatch):[A-Za-z0-9._/-]+$') {
        return $message
    }
    return 'authoritative-snapshot-invalid'
}

function Test-Arm64WorkflowTree {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][object]$Policy,
        [string]$TrustedPolicyPath,
        [ValidateSet('Auto', 'PowerShellYaml', 'RubyPsych', 'Unavailable')]
        [string]$Backend = 'Auto',
        [switch]$SkipAuthoritativeSnapshot
    )

    $errors = [Collections.Generic.List[string]]::new()
    $inventory = [Collections.Generic.List[object]]::new()
    $visitedWorkflows = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::Ordinal
    )
    $visitedScripts = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::Ordinal
    )
    $governanceCheckLocations = [Collections.Generic.List[string]]::new()
    function Add-AuditError {
        param([string]$Code)

        if (-not $errors.Contains($Code)) {
            [void]$errors.Add($Code)
        }
    }

    try {
        $resolvedBackend = Resolve-Arm64YamlBackend -Requested $Backend
    }
    catch {
        Add-AuditError (Resolve-Arm64ParserSelectionErrorCode -ErrorRecord $_)
        return [pscustomobject]@{
            Allowed = $false
            Errors = @($errors)
            Inventory = @()
            Parser = $null
        }
    }

    $publicationProperty = Get-Arm64MapProperty -Map $Policy -Name 'publication'
    if ($null -eq $publicationProperty -or
        $publicationProperty.Value.enabled -isnot [bool] -or
        $publicationProperty.Value.enabled -or
        $publicationProperty.Value.protected_environment_confirmed -isnot [bool] -or
        $publicationProperty.Value.protected_environment_confirmed -or
        $publicationProperty.Value.mode -cne 'unconditional-deny') {
        Add-AuditError 'publication-policy-must-remain-unconditionally-disabled'
    }
    $actionNames = @(Get-Arm64MapNames -Map $Policy.external_action_pins | Sort-Object)
    if (($actionNames -join "`0") -cne 'actions/checkout') {
        Add-AuditError 'active-action-allowlist-not-minimal'
    }

    $rootFull = [IO.Path]::GetFullPath($Root)
    $authoritativeSnapshot = $null
    if (-not $SkipAuthoritativeSnapshot) {
        try {
            $authoritativeSnapshot = Test-Arm64AuthoritativeSnapshot -Root $rootFull
        }
        catch {
            Add-AuditError (Resolve-Arm64AuthoritativeSnapshotErrorCode -ErrorRecord $_)
        }
        $candidatePolicyPath = Join-Path $rootFull '.github\policies\arm64-quarantine-policy.json'
        if ([string]::IsNullOrWhiteSpace($TrustedPolicyPath) -or
            -not (Test-Path -LiteralPath $TrustedPolicyPath -PathType Leaf) -or
            -not (Test-Path -LiteralPath $candidatePolicyPath -PathType Leaf)) {
            Add-AuditError 'protected-policy-data-missing'
        }
        else {
            $trustedPolicy = Get-Arm64FileBlobIdentity -Path $TrustedPolicyPath
            $candidatePolicy = Get-Arm64FileBlobIdentity -Path $candidatePolicyPath
            if ($trustedPolicy.byte_length -ne $candidatePolicy.byte_length -or
                $trustedPolicy.oid -cne $candidatePolicy.oid) {
                Add-AuditError 'protected-policy-source-binding-mismatch'
            }
        }
    }

    $protectedVerifierProperty = Get-Arm64MapProperty `
        -Map $Policy `
        -Name 'protected_verifier'
    if ($null -ne $protectedVerifierProperty) {
        $protectedSourcesProperty = Get-Arm64MapProperty `
            -Map $protectedVerifierProperty.Value `
            -Name 'sources'
        if ($null -eq $protectedSourcesProperty) {
            Add-AuditError 'protected-source-allowlist-missing'
        }
        else {
            foreach ($protectedPath in Get-Arm64MapNames -Map $protectedSourcesProperty.Value) {
                try {
                    $resolvedProtectedPath = Resolve-Arm64DataPath `
                        -Root $rootFull `
                        -RelativePath $protectedPath
                    $expectedProtectedBinding = (
                        Get-Arm64MapProperty `
                            -Map $protectedSourcesProperty.Value `
                            -Name $protectedPath
                    ).Value
                    Assert-Arm64SourceBinding `
                        -Binding $expectedProtectedBinding `
                        -Label $protectedPath
                    $identity = Get-Arm64FileBlobIdentity -Path $resolvedProtectedPath
                    $actualProtectedBinding = New-Arm64SourceBinding `
                        -Path $protectedPath `
                        -Mode $expectedProtectedBinding.mode `
                        -ObjectType 'blob' `
                        -ByteLength $identity.byte_length `
                        -Oid $identity.oid
                    if (-not (Test-Arm64SourceBindingEqual `
                            -Expected $expectedProtectedBinding `
                            -Actual $actualProtectedBinding)) {
                        Add-AuditError "protected-source-binding-mismatch:$protectedPath"
                    }
                }
                catch {
                    Add-AuditError "protected-source-invalid:$protectedPath"
                }
            }
        }
        if (-not $SkipAuthoritativeSnapshot -and $null -ne $authoritativeSnapshot -and
            -not [string]::IsNullOrWhiteSpace($TrustedPolicyPath)) {
            try {
                $trustedRoot = [IO.Path]::GetFullPath((
                        Join-Path (Split-Path $TrustedPolicyPath -Parent) '..\..'
                    ))
                $trustedSources = @(Get-Arm64ProtectedGitSourceBindings `
                        -RepositoryRoot $trustedRoot)
                $candidateSources = @($authoritativeSnapshot.files | Where-Object {
                        $_.path.StartsWith('.github/workflows/', [StringComparison]::Ordinal) -or
                        $_.path.StartsWith('.github/scripts/', [StringComparison]::Ordinal) -or
                        $_.path.StartsWith('.github/policies/', [StringComparison]::Ordinal)
                    } | Sort-Object path)
                Assert-Arm64SourceBindingSetsEqual `
                    -Expected $trustedSources `
                    -Actual $candidateSources `
                    -Label 'protected-source'
            }
            catch {
                Add-AuditError 'protected-source-set-invalid'
            }
        }
    }

    function Get-RelativeDataPath {
        param([Parameter(Mandatory)][string]$Path)

        return [IO.Path]::GetFullPath($Path).Substring($rootFull.Length + 1).
            Replace([IO.Path]::DirectorySeparatorChar, '/')
    }

    function Test-ContainerImage {
        param(
            [AllowNull()][object]$Image,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Image -isnot [string] -or
            $Image -cnotmatch '^[^@\s]+@sha256:[0-9a-f]{64}$') {
            Add-AuditError "container-not-digest-pinned:$Location"
            return
        }
        $expected = Get-Arm64MapProperty -Map $Policy.allowed_container_images -Name $Image
        if ($null -eq $expected) {
            Add-AuditError "container-not-allowlisted:$Location"
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'container'
                Location = $Location
                Target = $Image
            })
    }

    function Test-DelegatedScript {
        param(
            [Parameter(Mandatory)][string]$ScriptPath,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        $relative = Get-RelativeDataPath -Path $ScriptPath
        if (-not $visitedScripts.Add($relative)) {
            return
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'shell'
                Location = $Location
                Target = $relative
            })

        if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
            Add-AuditError "delegated-script-missing:$relative"
            return
        }
        if ([IO.Path]::GetExtension($ScriptPath) -cne '.ps1') {
            Add-AuditError "delegated-script-parser-unavailable:$relative"
            return
        }

        $allowedSourcesProperty = Get-Arm64MapProperty `
            -Map $WorkflowRule `
            -Name 'allowed_local_shell_sources'
        if ($null -eq $allowedSourcesProperty) {
            Add-AuditError "delegated-script-source-allowlist-missing:$relative"
            return
        }
        $expectedSource = Get-Arm64MapProperty `
            -Map $allowedSourcesProperty.Value `
            -Name $relative
        if ($null -eq $expectedSource) {
            Add-AuditError "delegated-script-source-not-allowlisted:$relative"
            return
        }
        try {
            Assert-Arm64SourceBinding -Binding $expectedSource.Value -Label $relative
            $identity = Get-Arm64FileBlobIdentity -Path $ScriptPath
            $actualSource = New-Arm64SourceBinding `
                -Path $relative `
                -Mode $expectedSource.Value.mode `
                -ObjectType 'blob' `
                -ByteLength $identity.byte_length `
                -Oid $identity.oid
            if (-not (Test-Arm64SourceBindingEqual `
                    -Expected $expectedSource.Value `
                    -Actual $actualSource)) {
                Add-AuditError "delegated-script-source-binding-mismatch:$relative"
                return
            }
        }
        catch {
            Add-AuditError "delegated-script-source-invalid:$relative"
            return
        }

        $tokens = $null
        $parseErrors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile(
            $ScriptPath,
            [ref]$tokens,
            [ref]$parseErrors
        )
        if ($parseErrors.Count -ne 0) {
            Add-AuditError "delegated-script-syntax-invalid:$relative"
            return
        }

        $authorityProperty = Get-Arm64MapProperty -Map $WorkflowRule -Name 'authority'
        if ($null -eq $authorityProperty) {
            Add-AuditError "delegated-script-authority-missing:$relative"
            return
        }
        $authority = [string]$authorityProperty.Value
        if ($authority -ceq 'untrusted-diagnostic') {
            $forbiddenCommands = @(
                'invoke-webrequest',
                'invoke-restmethod',
                'start-bitstransfer',
                'curl',
                'curl.exe',
                'wget',
                'wget.exe',
                'pacman',
                'makepkg',
                'repo-add',
                'msbuild',
                'dotnet',
                'npm',
                'pip',
                'gh',
                'git'
            )
            $commands = $ast.FindAll({
                    param($node)
                    return $node -is [Management.Automation.Language.CommandAst]
                }, $true)
            foreach ($command in $commands) {
                $commandName = $command.GetCommandName()
                if ($null -eq $commandName) {
                    Add-AuditError "diagnostic-dynamic-command:$relative"
                    continue
                }
                if ($forbiddenCommands -ccontains $commandName.ToLowerInvariant()) {
                    Add-AuditError "diagnostic-operation-forbidden:${relative}:$commandName"
                }
            }
            $urlFragments = $ast.FindAll({
                    param($node)
                    return ($node -is [Management.Automation.Language.StringConstantExpressionAst] -or
                        $node -is [Management.Automation.Language.ExpandableStringExpressionAst]) -and
                        $node.Value -match '(?i)(?:://|git@)'
                }, $true)
            if (@($urlFragments).Count -ne 0) {
                Add-AuditError "diagnostic-url-forbidden:$relative"
            }
        }
    }

    function Test-RunStep {
        param(
            [AllowNull()][object]$Run,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Run -isnot [string] -or [string]::IsNullOrWhiteSpace($Run)) {
            Add-AuditError "shell-run-invalid:$Location"
            return
        }
        $normalized = $Run.Replace("`r`n", "`n").Trim()
        $scriptMatch = [regex]::Match(
            $normalized,
            '^(?:&\s+)?(?:[''"])?(?<path>(?:\./|\.\\)[A-Za-z0-9_.\\/:-]+\.(?:ps1|sh|bash|cmd|bat|js|cjs|mjs|ts|py|rb))(?:[''"])?$',
            [Text.RegularExpressions.RegexOptions]::CultureInvariant
        )
        $delegatedPrefix = [regex]::IsMatch(
            $normalized,
            '^(?:&\s+)?(?:[''"])?(?:\./|\.\\)[A-Za-z0-9_.\\/:-]+\.(?:ps1|sh|bash|cmd|bat|js|cjs|mjs|ts|py|rb)',
            [Text.RegularExpressions.RegexOptions]::CultureInvariant
        )
        if ($scriptMatch.Success -and $normalized -notmatch "`n") {
            $relative = $scriptMatch.Groups['path'].Value.Substring(2).Replace('\', '/')
            $allowedProperty = Get-Arm64MapProperty `
                -Map $WorkflowRule `
                -Name 'allowed_local_shell_entrypoints'
            $allowed = if ($null -eq $allowedProperty) { @() } else { @($allowedProperty.Value) }
            if ($allowed -cnotcontains $relative) {
                Add-AuditError "shell-entrypoint-not-allowlisted:${Location}:$relative"
            }
            try {
                $resolved = Resolve-Arm64DataPath -Root $rootFull -RelativePath $relative
                Test-DelegatedScript `
                    -ScriptPath $resolved `
                    -WorkflowRule $WorkflowRule `
                    -Location $Location
            }
            catch {
                Add-AuditError "local-path-invalid:$Location"
            }
            return
        }
        if ($delegatedPrefix) {
            if ($normalized -match '[;|><`&\r\n]') {
                Add-AuditError "shell-command-chain-forbidden:$Location"
            }
            else {
                Add-AuditError "shell-arguments-forbidden:$Location"
            }
        }

        $inlineProperty = Get-Arm64MapProperty `
            -Map $WorkflowRule `
            -Name 'allowed_inline_shell_sha256'
        $allowedInline = if ($null -eq $inlineProperty) { @() } else { @($inlineProperty.Value) }
        # The allowlist binds the exact run-body bytes the parser produced, not a trimmed or
        # line-ending-normalized rendering of them.
        $hash = Get-Arm64Sha256Text -Text $Run
        if ($allowedInline -cnotcontains $hash) {
            Add-AuditError "inline-shell-not-allowlisted:$Location"
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'inline-shell'
                Location = $Location
                Target = $hash
            })
    }

    function Test-UsesReference {
        param(
            [AllowNull()][object]$Uses,
            [Parameter(Mandatory)][object]$Owner,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Uses -isnot [string] -or [string]::IsNullOrWhiteSpace($Uses) -or
            $Uses.Contains('${{', [StringComparison]::Ordinal)) {
            Add-AuditError "uses-reference-invalid:$Location"
            return
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'uses'
                Location = $Location
                Target = $Uses
            })

        if ($Uses.StartsWith('docker://', [StringComparison]::Ordinal)) {
            Test-ContainerImage -Image $Uses.Substring(9) -Location $Location
            return
        }
        if ($Uses.StartsWith('./', [StringComparison]::Ordinal)) {
            $relative = $Uses.Substring(2).Replace('\', '/')
            try {
                $resolved = Resolve-Arm64DataPath -Root $rootFull -RelativePath $relative
            }
            catch {
                Add-AuditError "local-path-invalid:$Location"
                return
            }

            if ($relative -match '(?i)\.ya?ml$') {
                Test-WorkflowFile -WorkflowPath $resolved -InvokedFrom $Location
                return
            }

            Add-AuditError "local-action-not-allowlisted:${Location}:$relative"
            $descriptors = @(@(
                    Join-Path $resolved 'action.yml'
                    Join-Path $resolved 'action.yaml'
                ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
            if ($descriptors.Count -ne 1) {
                Add-AuditError "local-action-descriptor-invalid:${Location}:$relative"
                return
            }
            try {
                $action = ConvertFrom-Arm64YamlFile -Path $descriptors[0] -Backend $resolvedBackend
            }
            catch {
                Add-AuditError (Resolve-Arm64YamlErrorCode `
                        -ErrorRecord $_ `
                        -Relative $relative)
                return
            }
            $runsProperty = Get-Arm64MapProperty -Map $action -Name 'runs'
            $usingProperty = if ($null -eq $runsProperty) {
                $null
            }
            else {
                Get-Arm64MapProperty -Map $runsProperty.Value -Name 'using'
            }
            if ($null -eq $usingProperty) {
                Add-AuditError "local-action-runs-missing:${Location}:$relative"
                return
            }
            if ($usingProperty.Value -ceq 'composite') {
                $steps = (Get-Arm64MapProperty -Map $runsProperty.Value -Name 'steps').Value
                Test-Steps -Steps $steps -WorkflowRule $WorkflowRule -Location "${Location}:local-action"
            }
            elseif ($usingProperty.Value -ceq 'docker') {
                Add-AuditError "local-docker-action-forbidden:${Location}:$relative"
            }
            else {
                foreach ($entry in @('main', 'pre', 'post')) {
                    $pathProperty = Get-Arm64MapProperty -Map $runsProperty.Value -Name $entry
                    if ($null -ne $pathProperty) {
                        [void]$inventory.Add([pscustomobject]@{
                                Kind = 'local-action-runtime'
                                Location = "${Location}:$entry"
                                Target = [string]$pathProperty.Value
                            })
                    }
                }
            }
            return
        }

        $separator = $Uses.LastIndexOf('@')
        if ($separator -lt 1) {
            Add-AuditError "remote-uses-unpinned:$Location"
            return
        }
        $action = $Uses.Substring(0, $separator)
        $reference = $Uses.Substring($separator + 1)
        if ($action -match '(?i)(?:^|/)(?:upload-artifact|download-artifact|upload-pages-artifact|configure-pages|deploy-pages|release|pages)(?:$|/)') {
            Add-AuditError "publication-action-forbidden:$Location"
            return
        }
        if ($reference -cnotmatch '^[0-9a-f]{40}$') {
            Add-AuditError "remote-uses-not-commit-pinned:${Location}:$action"
            return
        }
        if ($action -ceq 'msys2/setup-msys2') {
            $withProperty = Get-Arm64MapProperty -Map $Owner -Name 'with'
            $msystemProperty = if ($null -eq $withProperty) {
                $null
            }
            else {
                Get-Arm64MapProperty -Map $withProperty.Value -Name 'msystem'
            }
            if ($null -eq $msystemProperty -or
                $msystemProperty.Value -isnot [string] -or
                @($Policy.forbidden_msystems) -ccontains $msystemProperty.Value) {
                Add-AuditError "unsupported-msystem-before-setup:$Location"
            }
        }
        $pin = Get-Arm64ExactMapProperty -Map $Policy.external_action_pins -Name $action
        if ($null -eq $pin) {
            Add-AuditError "remote-uses-not-reviewed:${Location}:$action"
            return
        }
        $commit = Get-Arm64MapProperty -Map $pin.Value -Name 'commit'
        if ($null -eq $commit -or $reference -cne $commit.Value) {
            Add-AuditError "remote-uses-pin-mismatch:${Location}:$action"
        }

    }

    function Test-Steps {
        param(
            [AllowNull()][object]$Steps,
            [Parameter(Mandatory)][object]$WorkflowRule,
            [Parameter(Mandatory)][string]$Location
        )

        if ($Steps -is [string] -or $Steps -isnot [Collections.IEnumerable]) {
            Add-AuditError "steps-invalid:$Location"
            return
        }
        $index = 0
        foreach ($step in @($Steps)) {
            $usesProperty = Get-Arm64MapProperty -Map $step -Name 'uses'
            $runProperty = Get-Arm64MapProperty -Map $step -Name 'run'
            if ($null -ne $usesProperty -and $null -ne $runProperty) {
                Add-AuditError "step-uses-and-run:${Location}:$index"
            }
            elseif ($null -ne $usesProperty) {
                Test-UsesReference `
                    -Uses $usesProperty.Value `
                    -Owner $step `
                    -WorkflowRule $WorkflowRule `
                    -Location "${Location}:step[$index]"
            }
            elseif ($null -ne $runProperty) {
                if ($runProperty.Value -is [string] -and
                    $runProperty.Value -match '(?i)(?:\bgh\s+release\b|/releases(?:/|\b)|\bartifact(?:s)?\b|\bpages\b)') {
                    Add-AuditError "publication-shell-route-forbidden:${Location}:step[$index]"
                }
                $shellProperty = Get-Arm64MapProperty -Map $step -Name 'shell'
                $allowedShellsProperty = Get-Arm64MapProperty `
                    -Map $WorkflowRule `
                    -Name 'allowed_shells'
                $allowedShells = if ($null -eq $allowedShellsProperty) {
                    @()
                }
                else {
                    @($allowedShellsProperty.Value)
                }
                if ($null -eq $shellProperty -or
                    $shellProperty.Value -isnot [string] -or
                    $allowedShells -cnotcontains $shellProperty.Value) {
                    Add-AuditError "shell-template-not-allowlisted:${Location}:step[$index]"
                }
                Test-RunStep `
                    -Run $runProperty.Value `
                    -WorkflowRule $WorkflowRule `
                    -Location "${Location}:step[$index]"
            }
            else {
                Add-AuditError "step-operation-missing:${Location}:$index"
            }
            $index++
        }
    }

    function Get-WorkflowEvents {
        param(
            [AllowNull()][object]$OnValue,
            [Parameter(Mandatory)][string]$Location
        )

        if ($OnValue -is [string]) {
            return @($OnValue)
        }
        if ($OnValue -is [Collections.IDictionary] -or $OnValue -is [pscustomobject]) {
            return @(Get-Arm64MapNames -Map $OnValue)
        }
        if ($OnValue -is [Collections.IEnumerable]) {
            $events = @($OnValue)
            if (@($events | Where-Object { $_ -isnot [string] }).Count -ne 0) {
                Add-AuditError "workflow-events-invalid:$Location"
                return @()
            }
            return $events
        }
        Add-AuditError "workflow-events-invalid:$Location"
        return @()
    }

    function Test-WorkflowFile {
        param(
            [Parameter(Mandatory)][string]$WorkflowPath,
            [string]$InvokedFrom = 'entrypoint'
        )

        if (-not (Test-Path -LiteralPath $WorkflowPath -PathType Leaf)) {
            Add-AuditError "workflow-file-missing:$WorkflowPath"
            return
        }
        $relative = Get-RelativeDataPath -Path $WorkflowPath
        if (-not $visitedWorkflows.Add($relative)) {
            return
        }
        [void]$inventory.Add([pscustomobject]@{
                Kind = 'workflow'
                Location = $InvokedFrom
                Target = $relative
            })

        $ruleProperty = Get-Arm64MapProperty -Map $Policy.active_workflows -Name $relative
        if ($null -eq $ruleProperty) {
            Add-AuditError "workflow-not-allowlisted:$relative"
            $workflowRule = [pscustomobject]@{
                allowed_events = @()
                allowed_local_shell_entrypoints = @()
                allowed_local_shell_sources = [pscustomobject]@{}
                allowed_inline_shell_sha256 = @()
                allowed_shells = @()
                authority = 'unknown'
            }
        }
        else {
            $workflowRule = $ruleProperty.Value
            $workflowSourceProperty = Get-Arm64MapProperty `
                -Map $workflowRule `
                -Name 'source'
            if ($null -eq $workflowSourceProperty) {
                Add-AuditError "workflow-source-binding-missing:$relative"
            }
            else {
                try {
                    Assert-Arm64SourceBinding `
                        -Binding $workflowSourceProperty.Value `
                        -Label $relative
                    $identity = Get-Arm64FileBlobIdentity -Path $WorkflowPath
                    $actualSource = New-Arm64SourceBinding `
                        -Path $relative `
                        -Mode $workflowSourceProperty.Value.mode `
                        -ObjectType 'blob' `
                        -ByteLength $identity.byte_length `
                        -Oid $identity.oid
                    if (-not (Test-Arm64SourceBindingEqual `
                            -Expected $workflowSourceProperty.Value `
                            -Actual $actualSource)) {
                        Add-AuditError "workflow-source-binding-mismatch:$relative"
                    }
                }
                catch {
                    Add-AuditError "workflow-source-binding-invalid:$relative"
                }
            }
        }

        try {
            $workflow = ConvertFrom-Arm64YamlFile -Path $WorkflowPath -Backend $resolvedBackend
        }
        catch {
            Add-AuditError (Resolve-Arm64YamlErrorCode -ErrorRecord $_ -Relative $relative)
            return
        }
        if ($null -eq $workflow) {
            Add-AuditError "workflow-empty:$relative"
            return
        }

        foreach ($defaultsOwner in @(
                [pscustomobject]@{ Value = $workflow; Location = $relative })) {
            $defaultsProperty = Get-Arm64MapProperty -Map $defaultsOwner.Value -Name 'defaults'
            if ($null -ne $defaultsProperty) {
                $runDefaults = Get-Arm64MapProperty -Map $defaultsProperty.Value -Name 'run'
                $shellDefault = if ($null -eq $runDefaults) {
                    $null
                }
                else {
                    Get-Arm64MapProperty -Map $runDefaults.Value -Name 'shell'
                }
                if ($null -ne $shellDefault) {
                    Add-AuditError "default-shell-template-forbidden:$($defaultsOwner.Location)"
                }
            }
        }

        $onProperty = Get-Arm64MapProperty -Map $workflow -Name 'on'
        if ($null -eq $onProperty) {
            Add-AuditError "workflow-trigger-missing:$relative"
        }
        else {
            $actualEvents = @(Get-WorkflowEvents -OnValue $onProperty.Value -Location $relative |
                    Sort-Object -Unique)
            $allowedEventsProperty = Get-Arm64MapProperty `
                -Map $workflowRule `
                -Name 'allowed_events'
            $allowedEvents = if ($null -eq $allowedEventsProperty) {
                @()
            }
            else {
                @($allowedEventsProperty.Value | Sort-Object -Unique)
            }
            if (($actualEvents -join "`0") -cne ($allowedEvents -join "`0")) {
                Add-AuditError "workflow-trigger-not-allowlisted:$relative"
            }
            if (@($actualEvents | Where-Object {
                        $_ -match '^(?i:release|pages_build|workflow_dispatch)$'
                    }).Count -ne 0) {
                Add-AuditError "publication-trigger-forbidden:$relative"
            }
        }

        $workflowPermissions = Get-Arm64MapProperty -Map $workflow -Name 'permissions'
        if ($null -ne $workflowPermissions -and
            @('write', 'write-all') -ccontains [string]$workflowPermissions.Value) {
            Add-AuditError "publication-permissions-forbidden:$relative"
        }
        elseif ($null -ne $workflowPermissions) {
            foreach ($permissionName in Get-Arm64MapNames -Map $workflowPermissions.Value) {
                $permission = Get-Arm64MapProperty `
                    -Map $workflowPermissions.Value `
                    -Name $permissionName
                if ($null -ne $permission -and $permission.Value -ceq 'write') {
                    Add-AuditError "publication-permissions-forbidden:${relative}:$permissionName"
                }
            }
        }

        $jobsProperty = Get-Arm64MapProperty -Map $workflow -Name 'jobs'
        if ($null -eq $jobsProperty) {
            Add-AuditError "workflow-jobs-missing:$relative"
            return
        }
        foreach ($jobName in Get-Arm64MapNames -Map $jobsProperty.Value) {
            $job = (Get-Arm64MapProperty -Map $jobsProperty.Value -Name $jobName).Value
            $location = "${relative}:job[$jobName]"
            $jobNameProperty = Get-Arm64MapProperty -Map $job -Name 'name'
            $displayName = if ($null -eq $jobNameProperty) {
                [string]$jobName
            }
            else {
                [string]$jobNameProperty.Value
            }
            if ($displayName -ceq 'arm64-governance') {
                [void]$governanceCheckLocations.Add($location)
                $ifProperty = Get-Arm64MapProperty -Map $job -Name 'if'
                $needsProperty = Get-Arm64MapProperty -Map $job -Name 'needs'
                if ($null -ne $ifProperty -or $null -ne $needsProperty) {
                    Add-AuditError "governance-check-can-be-skipped:$location"
                }
            }
            elseif ($displayName.StartsWith(
                    'arm64-governance',
                    [StringComparison]::OrdinalIgnoreCase
                ) -or
                'arm64-governance'.StartsWith(
                    $displayName,
                    [StringComparison]::OrdinalIgnoreCase
                )) {
                Add-AuditError "governance-check-name-alias:$location"
            }
            $environmentProperty = Get-Arm64MapProperty -Map $job -Name 'environment'
            if ($null -ne $environmentProperty) {
                Add-AuditError "publication-environment-forbidden:$location"
            }
            $jobPermissions = Get-Arm64MapProperty -Map $job -Name 'permissions'
            if ($null -ne $jobPermissions -and
                @('write', 'write-all') -ccontains [string]$jobPermissions.Value) {
                Add-AuditError "publication-permissions-forbidden:$location"
            }
            elseif ($null -ne $jobPermissions) {
                foreach ($permissionName in Get-Arm64MapNames -Map $jobPermissions.Value) {
                    $permission = Get-Arm64MapProperty `
                        -Map $jobPermissions.Value `
                        -Name $permissionName
                    if ($null -ne $permission -and $permission.Value -ceq 'write') {
                        Add-AuditError "publication-permissions-forbidden:${location}:$permissionName"
                    }
                }
            }
            $jobDefaults = Get-Arm64MapProperty -Map $job -Name 'defaults'
            if ($null -ne $jobDefaults -and
                $null -ne (Get-Arm64MapProperty -Map $jobDefaults.Value -Name 'run')) {
                Add-AuditError "default-shell-template-forbidden:$location"
            }
            $jobUses = Get-Arm64MapProperty -Map $job -Name 'uses'
            if ($null -ne $jobUses) {
                Test-UsesReference `
                    -Uses $jobUses.Value `
                    -Owner $job `
                    -WorkflowRule $workflowRule `
                    -Location $location
            }

            $containerProperty = Get-Arm64MapProperty -Map $job -Name 'container'
            if ($null -ne $containerProperty) {
                $imageProperty = Get-Arm64MapProperty -Map $containerProperty.Value -Name 'image'
                $image = if ($null -eq $imageProperty) {
                    $containerProperty.Value
                }
                else {
                    $imageProperty.Value
                }
                Test-ContainerImage -Image $image -Location "${location}:container"
            }
            $servicesProperty = Get-Arm64MapProperty -Map $job -Name 'services'
            if ($null -ne $servicesProperty) {
                foreach ($serviceName in Get-Arm64MapNames -Map $servicesProperty.Value) {
                    $service = (Get-Arm64MapProperty -Map $servicesProperty.Value -Name $serviceName).Value
                    $imageProperty = Get-Arm64MapProperty -Map $service -Name 'image'
                    $image = if ($null -eq $imageProperty) { $service } else { $imageProperty.Value }
                    Test-ContainerImage -Image $image -Location "${location}:service[$serviceName]"
                }
            }

            $stepsProperty = Get-Arm64MapProperty -Map $job -Name 'steps'
            if ($null -ne $stepsProperty) {
                Test-Steps `
                    -Steps $stepsProperty.Value `
                    -WorkflowRule $workflowRule `
                    -Location $location
            }
            elseif ($null -eq $jobUses) {
                Add-AuditError "job-operation-missing:$location"
            }
        }
    }

    $workflowRoot = Join-Path $rootFull '.github\workflows'
    if (-not (Test-Path -LiteralPath $workflowRoot -PathType Container)) {
        Add-AuditError 'workflow-directory-missing'
    }
    else {
        $workflowFiles = @(Get-ChildItem -LiteralPath $workflowRoot -File -Recurse -Force |
                Where-Object { $_.Extension -in @('.yml', '.yaml') } |
                Sort-Object FullName)
        foreach ($workflowFile in $workflowFiles) {
            Test-WorkflowFile -WorkflowPath $workflowFile.FullName
        }

        $expectedWorkflows = @(Get-Arm64MapNames -Map $Policy.active_workflows | Sort-Object)
        $actualWorkflows = @($workflowFiles | ForEach-Object {
                Get-RelativeDataPath -Path $_.FullName
            } | Sort-Object)
        if (($expectedWorkflows -join "`0") -cne ($actualWorkflows -join "`0")) {
            Add-AuditError 'active-workflow-set-mismatch'
        }
    }

    if ($null -ne $protectedVerifierProperty) {
        if ($protectedVerifierProperty.Value.check_name -cne 'arm64-governance') {
            Add-AuditError 'protected-check-name-invalid'
        }
        if ($governanceCheckLocations.Count -ne 1) {
            Add-AuditError 'protected-check-name-not-unique'
        }
    }

    return [pscustomobject]@{
        Allowed = $errors.Count -eq 0
        Errors = @($errors)
        Inventory = @($inventory)
        Parser = $resolvedBackend
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if ([string]::IsNullOrWhiteSpace($CandidateRoot) -or
        [string]::IsNullOrWhiteSpace($PolicyPath)) {
        throw 'Specify -CandidateRoot and -PolicyPath.'
    }
    $policy = Get-Content -LiteralPath $PolicyPath -Raw | ConvertFrom-Json -Depth 64
    $result = Test-Arm64WorkflowTree `
        -Root $CandidateRoot `
        -Policy $policy `
        -TrustedPolicyPath $PolicyPath `
        -Backend $ParserBackend `
        -SkipAuthoritativeSnapshot:$FixtureMode
    if (-not $result.Allowed) {
        foreach ($errorCode in $result.Errors) {
            [Console]::Error.WriteLine("Workflow audit denied: $errorCode")
        }
        exit 1
    }

    Write-Output "Semantic workflow audit passed with $($result.Parser)."
}
