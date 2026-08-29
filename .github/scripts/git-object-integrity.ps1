[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:arm64GitIdentity = $null
$script:arm64GitPins = @(
    [pscustomobject][ordered]@{
        Architecture = 'x64'
        PeMachine = 0x8664
        Version = '2.55.0.windows.3'
        RuntimeBinRelativePath = 'mingw64\bin'
        LauncherSha256 = '7b7971dd13f0c3a284e538601f2f9770b3a87dfaccb5fb52d68141c67ed22364'
        EngineSha256 = '1a0043555d254618f2d56c936c3d9a1fbfb878bc878416a133c346bc7835eda9'
        RuntimeTreeSha256 = '20c9c179dd4e9fddaf0b885fc1f3990345a4ad649b82e6a8818521e56b6b4862'
        RuntimeManifestSha256 =
            'cd63c854cb26a8c1140685726374a82405cda7ea813ed86804d7145ecd33ba8c'
        SignerThumbprint = '3e9627155b7a6f29856321ee56d7fc25cf808407'
    },
    [pscustomobject][ordered]@{
        Architecture = 'arm64'
        PeMachine = 0xAA64
        Version = '2.55.0.windows.3'
        RuntimeBinRelativePath = 'clangarm64\bin'
        LauncherSha256 = 'b05b2d7eb80933c602272b5ddf132adf288cf78ad8e32a7a47ca7e200076b9f3'
        EngineSha256 = '4cbb8ef70f1201e534fc3fab8f52b83080748a7115793d957d1b399e1ff55ad7'
        RuntimeTreeSha256 = 'ae2dae0b859e7266b06894dbf377ecb30f04aeffe4b1e45e6d88f50fa8f1bbc0'
        RuntimeManifestSha256 =
            '721d63474d9f16be89a9aa3a00abf1415bd4848616f789d505db3cef1ab5dd4c'
        SignerThumbprint = '3e9627155b7a6f29856321ee56d7fc25cf808407'
    }
)

function Initialize-Arm64RuntimePathResolver {
    if ('Arm64RuntimePathResolverV1' -as [type]) {
        return
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Runtime path provenance is unavailable.'
    }
    Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

public static class Arm64RuntimePathResolverV1
{
    private const uint FileShareRead = 1;
    private const uint FileShareWrite = 2;
    private const uint FileShareDelete = 4;
    private const uint OpenExisting = 3;
    private const uint FileFlagBackupSemantics = 0x02000000;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(
        string name,
        uint access,
        uint share,
        IntPtr security,
        uint creation,
        uint flags,
        IntPtr template);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandleW(
        SafeFileHandle file,
        StringBuilder path,
        uint length,
        uint flags);

    public static string Resolve(string path)
    {
        using (SafeFileHandle handle = CreateFileW(
            path,
            0,
            FileShareRead | FileShareWrite | FileShareDelete,
            IntPtr.Zero,
            OpenExisting,
            FileFlagBackupSemantics,
            IntPtr.Zero))
        {
            if (handle.IsInvalid)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            StringBuilder buffer = new StringBuilder(32768);
            uint length = GetFinalPathNameByHandleW(
                handle,
                buffer,
                (uint)buffer.Capacity,
                0);
            if (length == 0 || length >= buffer.Capacity)
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            string result = buffer.ToString();
            return result.StartsWith(@"\\?\", StringComparison.Ordinal)
                ? result.Substring(4)
                : result;
        }
    }
}
'@
}

function Resolve-Arm64CanonicalRuntimePath {
    param([Parameter(Mandatory)][string]$Path)

    if (-not [IO.Path]::IsPathFullyQualified($Path)) {
        throw 'Runtime path provenance is not approved.'
    }
    $fullPath = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($fullPath)
    $current = $root
    foreach ($segment in $fullPath.Substring($root.Length).Split(
            [IO.Path]::DirectorySeparatorChar,
            [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $segment
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Runtime path provenance is not approved.'
        }
    }
    Initialize-Arm64RuntimePathResolver
    $finalPath = [Arm64RuntimePathResolverV1]::Resolve($fullPath)
    if (-not $finalPath.Equals($fullPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Runtime path provenance is not approved.'
    }
    return $finalPath
}

function Get-Arm64GitFileSha256 {
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

function Get-Arm64GitPeMachine {
    param([Parameter(Mandatory)][string]$Path)

    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    $reader = [IO.BinaryReader]::new($stream)
    try {
        if ($stream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5A4D) {
            throw 'Git runtime provenance is not approved.'
        }
        $stream.Position = 0x3C
        $peOffset = $reader.ReadUInt32()
        if ($peOffset -gt $stream.Length - 6) {
            throw 'Git runtime provenance is not approved.'
        }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw 'Git runtime provenance is not approved.'
        }
        return [int]$reader.ReadUInt16()
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Resolve-Arm64GitRuntimePin {
    param([Parameter(Mandatory)][string]$LauncherPath)

    $launcherSha256 = Get-Arm64GitFileSha256 -Path $LauncherPath
    $peMachine = Get-Arm64GitPeMachine -Path $LauncherPath
    $version = [Diagnostics.FileVersionInfo]::GetVersionInfo(
        $LauncherPath
    ).ProductVersion
    $matches = @($script:arm64GitPins | Where-Object {
            $_.LauncherSha256 -ceq $launcherSha256 -and
            $_.PeMachine -eq $peMachine -and
            $_.Version -ceq $version
        })
    if ($matches.Count -ne 1) {
        throw 'Git runtime provenance is not approved.'
    }
    return $matches[0]
}

function Get-Arm64GitDirectoryTreeSha256 {
    param([Parameter(Mandatory)][string]$Root)

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $paths = [Collections.Generic.Dictionary[string, string]]::new(
        [StringComparer]::Ordinal
    )
    foreach ($file in Get-ChildItem -LiteralPath $rootFull -File -Recurse -Force) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Git runtime provenance is not approved.'
        }
        $relative = $file.FullName.Substring($rootFull.Length + 1).Replace(
            [IO.Path]::DirectorySeparatorChar,
            '/'
        )
        if (-not $paths.TryAdd($relative, $file.FullName)) {
            throw 'Git runtime provenance is not approved.'
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

function Get-Arm64GitDirectoryManifestSha256 {
    param([Parameter(Mandatory)][string]$Root)

    $rootFull = Resolve-Arm64CanonicalRuntimePath -Path $Root
    $paths = [Collections.Generic.Dictionary[string, long]]::new(
        [StringComparer]::Ordinal
    )
    foreach ($file in Get-ChildItem -LiteralPath $rootFull -File -Recurse -Force) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Git runtime provenance is not approved.'
        }
        $relative = $file.FullName.Substring($rootFull.Length + 1).Replace(
            [IO.Path]::DirectorySeparatorChar,
            '/'
        )
        if (-not $paths.TryAdd($relative, [long]$file.Length)) {
            throw 'Git runtime provenance is not approved.'
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

function Reset-Arm64GitRuntimeIdentity {
    if ($null -ne $script:arm64GitIdentity -and
        $null -ne $script:arm64GitIdentity.PSObject.Properties['Locks']) {
        Close-Arm64GitRuntimeLocks -Locks $script:arm64GitIdentity.Locks
    }
    $script:arm64GitIdentity = $null
}

function Assert-Arm64GitRuntimeIdentity {
    param(
        [Parameter(Mandatory)][object]$Identity,
        [switch]$ManifestOnly
    )

    $launcher = Resolve-Arm64CanonicalRuntimePath -Path $Identity.ExecutablePath
    $root = Resolve-Arm64CanonicalRuntimePath -Path $Identity.Root
    $pin = Resolve-Arm64GitRuntimePin -LauncherPath $launcher
    $runtimeRoot = Resolve-Arm64CanonicalRuntimePath `
        -Path (Join-Path $root $pin.RuntimeBinRelativePath)
    $engine = Resolve-Arm64CanonicalRuntimePath `
        -Path (Join-Path $runtimeRoot 'git.exe')
    if (-not $launcher.Equals(
            (Join-Path $root 'cmd\git.exe'),
            [StringComparison]::OrdinalIgnoreCase
        ) -or
        (Get-Arm64GitFileSha256 -Path $launcher) -cne
            $pin.LauncherSha256 -or
        (Get-Arm64GitFileSha256 -Path $engine) -cne
            $pin.EngineSha256 -or
        (Get-Arm64GitPeMachine -Path $engine) -ne $pin.PeMachine -or
        [Diagnostics.FileVersionInfo]::GetVersionInfo($engine).ProductVersion -cne
            $pin.Version) {
        throw 'Git runtime provenance is not approved.'
    }
    if ($ManifestOnly) {
        if ((Get-Arm64GitDirectoryManifestSha256 -Root $runtimeRoot) -cne
            $pin.RuntimeManifestSha256) {
            throw 'Git runtime provenance is not approved.'
        }
    }
    elseif ((Get-Arm64GitDirectoryTreeSha256 -Root $runtimeRoot) -cne
        $pin.RuntimeTreeSha256) {
        throw 'Git runtime provenance is not approved.'
    }
    $signatures = @(
        Microsoft.PowerShell.Security\Get-AuthenticodeSignature `
            -LiteralPath $launcher
        Microsoft.PowerShell.Security\Get-AuthenticodeSignature `
            -LiteralPath $engine
    )
    if (@($signatures | Where-Object {
                $_.Status -ne [Management.Automation.SignatureStatus]::Valid -or
                $null -eq $_.SignerCertificate -or
                $_.SignerCertificate.Thumbprint.ToLowerInvariant() -cne
                    $pin.SignerThumbprint
            }).Count -ne 0) {
        throw 'Git runtime provenance is not approved.'
    }
    return $true
}

function Resolve-Arm64GitExecutable {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Git runtime provenance is unavailable.'
    }
    if ($null -ne $script:arm64GitIdentity) {
        try {
            [void](Assert-Arm64GitRuntimeIdentity `
                    -Identity $script:arm64GitIdentity `
                    -ManifestOnly)
            return $script:arm64GitIdentity
        }
        catch {
            Reset-Arm64GitRuntimeIdentity
            throw 'Git runtime provenance is not approved.'
        }
    }

    $candidates = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    $configured = [Environment]::GetEnvironmentVariable('ARM64_GIT_EXECUTABLE')
    if (-not [string]::IsNullOrWhiteSpace($configured) -and
        [IO.Path]::IsPathFullyQualified($configured)) {
        [void]$candidates.Add([IO.Path]::GetFullPath($configured))
    }
    if ([string]::IsNullOrWhiteSpace($configured)) {
        $programFiles = [Environment]::GetFolderPath(
            [Environment+SpecialFolder]::ProgramFiles
        )
        [void]$candidates.Add([IO.Path]::GetFullPath((
                    Join-Path $programFiles 'Git\cmd\git.exe'
                )))
    }

    $existing = @($candidates | Where-Object {
            Test-Path -LiteralPath $_ -PathType Leaf
        })
    $approved = [Collections.Generic.List[object]]::new()
    foreach ($launcher in $existing) {
        try {
            $launcher = Resolve-Arm64CanonicalRuntimePath -Path $launcher
            $root = Resolve-Arm64CanonicalRuntimePath -Path (
                Join-Path (Split-Path $launcher -Parent) '..'
            )
        }
        catch {
            continue
        }
        $candidateIdentity = [pscustomobject][ordered]@{
            ExecutablePath = $launcher
            Root = $root
            Locks = $null
        }
        $locks = $null
        try {
            $locks = Open-Arm64GitRuntimeLocks -Identity $candidateIdentity
            $candidateIdentity.Locks = $locks
            [void](Assert-Arm64GitRuntimeIdentity -Identity $candidateIdentity)
            [void]$approved.Add($candidateIdentity)
            $locks = $null
        }
        catch {
            Write-Verbose 'Git runtime candidate provenance did not match.'
        }
        finally {
            Close-Arm64GitRuntimeLocks -Locks $locks
        }
    }
    if ($approved.Count -ne 1) {
        foreach ($identity in $approved) {
            Close-Arm64GitRuntimeLocks -Locks $identity.Locks
        }
        throw 'Git runtime provenance is not approved.'
    }
    $script:arm64GitIdentity = $approved[0]
    return $script:arm64GitIdentity
}

function Open-Arm64GitRuntimeLocks {
    param([Parameter(Mandatory)][object]$Identity)

    $paths = [Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    [void]$paths.Add([IO.Path]::GetFullPath($Identity.ExecutablePath))
    $pin = Resolve-Arm64GitRuntimePin -LauncherPath $Identity.ExecutablePath
    foreach ($file in Get-ChildItem `
            -LiteralPath (Join-Path $Identity.Root $pin.RuntimeBinRelativePath) `
            -File `
            -Recurse `
            -Force) {
        [void]$paths.Add($file.FullName)
    }
    $ordered = [string[]]@($paths)
    [Array]::Sort($ordered, [StringComparer]::OrdinalIgnoreCase)
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
        throw 'Git runtime provenance is not approved.'
    }
}

function Close-Arm64GitRuntimeLocks {
    param([AllowNull()][object]$Locks)

    if ($null -ne $Locks) {
        foreach ($stream in $Locks) {
            $stream.Dispose()
        }
    }
}

function Invoke-Arm64Git {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$GitArguments
    )

    # Git is invoked with a scrubbed environment and hardened configuration so that ambient
    # Git variables, system or global config, hooks, replacement objects, or a poisoned
    # fsmonitor cannot influence what bytes an object read returns.
    $gitIdentity = Resolve-Arm64GitExecutable
    $runtimeLocks = Open-Arm64GitRuntimeLocks -Identity $gitIdentity
    try {
        $verifiedIdentity = Resolve-Arm64GitExecutable
        if ($verifiedIdentity.ExecutablePath -cne $gitIdentity.ExecutablePath) {
            throw 'Git runtime provenance is not approved.'
        }

        $startInfo = [Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $verifiedIdentity.ExecutablePath
        foreach ($argument in @(
                '--no-replace-objects',
                '-c', 'core.hooksPath=',
                '-c', 'core.fsmonitor=false',
                '-c', 'core.symlinks=false',
                '-c', 'core.quotePath=false',
                '-c', 'protocol.allow=never',
                '-C', $RepositoryRoot) + $GitArguments) {
            $startInfo.ArgumentList.Add($argument)
        }
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true

        $startInfo.Environment.Clear()
        foreach ($name in @('SystemRoot', 'windir', 'TEMP', 'TMP',
                'PROCESSOR_ARCHITECTURE', 'COMSPEC')) {
            $value = [Environment]::GetEnvironmentVariable($name)
            if (-not [string]::IsNullOrEmpty($value)) {
                $startInfo.Environment[$name] = $value
            }
        }
        $startInfo.Environment['GIT_CONFIG_NOSYSTEM'] = '1'
        $startInfo.Environment['GIT_CONFIG_GLOBAL'] = [IO.Path]::GetFullPath(
            (Join-Path ([IO.Path]::GetTempPath()) 'arm64-absent-git-config')
        )
        $startInfo.Environment['GIT_NO_REPLACE_OBJECTS'] = '1'
        $startInfo.Environment['GIT_TERMINAL_PROMPT'] = '0'
        $startInfo.Environment['GIT_OPTIONAL_LOCKS'] = '0'
        $startInfo.Environment['GIT_ATTR_NOSYSTEM'] = '1'
        $startInfo.Environment['GIT_FLUSH'] = '1'
        $startInfo.Environment['LC_ALL'] = 'C'

        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        try {
            [void]$process.Start()
            $standardOutput = $process.StandardOutput.ReadToEnd()
            [void]$process.StandardError.ReadToEnd()
            if (-not $process.WaitForExit(120000)) {
                try {
                    $process.Kill($true)
                }
                catch {
                    Write-Verbose 'Hardened Git process could not be terminated.'
                }
                throw 'Hardened Git invocation timed out.'
            }
            return [pscustomobject]@{
                ExitCode = [int]$process.ExitCode
                Lines    = @($standardOutput -split "`r?`n" |
                        Where-Object { $_.Length -gt 0 })
            }
        }
        finally {
            $process.Dispose()
        }
    }
    finally {
        Close-Arm64GitRuntimeLocks -Locks $runtimeLocks
    }
}

function Assert-Arm64GitRepositoryHygiene {
    param([Parameter(Mandatory)][string]$RepositoryRoot)

    foreach ($variable in @('GIT_DIR', 'GIT_OBJECT_DIRECTORY',
            'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_WORK_TREE',
            'GIT_INDEX_FILE', 'GIT_NAMESPACE', 'GIT_GRAFT_FILE', 'GIT_REPLACE_REF_BASE',
            'GIT_CEILING_DIRECTORIES')) {
        if (-not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($variable))) {
            throw "Git environment override is not permitted: $variable"
        }
    }

    $directories = Invoke-Arm64Git `
        -RepositoryRoot $RepositoryRoot `
        -GitArguments @('rev-parse', '--absolute-git-dir', '--git-common-dir')
    if ($directories.ExitCode -ne 0 -or $directories.Lines.Count -lt 1) {
        throw 'Git repository directories could not be resolved.'
    }

    $resolved = [Collections.Generic.List[string]]::new()
    foreach ($line in $directories.Lines) {
        $candidate = $line
        if (-not [IO.Path]::IsPathRooted($candidate)) {
            $candidate = Join-Path $RepositoryRoot $candidate
        }
        [void]$resolved.Add([IO.Path]::GetFullPath($candidate))
    }

    foreach ($directory in @($resolved | Sort-Object -Unique)) {
        foreach ($poison in @(
                (Join-Path $directory 'info\grafts'),
                (Join-Path $directory 'objects\info\alternates'),
                (Join-Path $directory 'commondir'))) {
            if ($poison.EndsWith('commondir', [StringComparison]::Ordinal)) {
                continue
            }
            if (Test-Path -LiteralPath $poison -PathType Leaf) {
                throw "Git object poisoning artifact is present: $(Split-Path $poison -Leaf)"
            }
        }
    }

    $replacements = Invoke-Arm64Git `
        -RepositoryRoot $RepositoryRoot `
        -GitArguments @('for-each-ref', '--format=%(refname)', 'refs/replace/')
    if ($replacements.ExitCode -ne 0) {
        throw 'Git replacement references could not be enumerated.'
    }
    if ($replacements.Lines.Count -ne 0) {
        throw 'Git replacement references are not permitted.'
    }
    return $true
}

function Assert-Arm64GitObjectFormatValue {
    param([AllowNull()][object]$Output)

    $values = @(@($Output) |
            Where-Object { $null -ne $_ } |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_.Length -gt 0 })
    if ($values.Count -ne 1) {
        throw 'Git object format is absent or ambiguous.'
    }
    $format = $values[0]
    if ($format -cnotmatch '^[a-z0-9]{1,16}$') {
        throw 'Git object format is not a recognizable identifier.'
    }
    if ($format -cne 'sha1') {
        # Every binding in this policy is a 40-hex SHA-1 object ID. A sha256 (or future)
        # repository is not supported and must fail closed rather than be misread.
        throw "Git object format is not sha1: $format"
    }
    return $format
}

function Assert-Arm64GitObjectFormat {
    param([Parameter(Mandatory)][string]$RepositoryRoot)

    $result = Invoke-Arm64Git `
        -RepositoryRoot $RepositoryRoot `
        -GitArguments @('rev-parse', '--show-object-format')
    if ($result.ExitCode -ne 0) {
        throw 'Git object format could not be determined.'
    }
    return Assert-Arm64GitObjectFormatValue -Output $result.Lines
}

function Test-Arm64GitObjectId {
    param([AllowNull()][object]$Value)

    return $Value -is [string] -and
        $Value -cmatch '^[0-9a-f]{40}$' -and
        $Value -cne ('0' * 40)
}

function Get-Arm64RawPathIdentity {
    param([Parameter(Mandatory)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or
        $Path -cnotmatch '^[\x20-\x7e]+$' -or
        $Path.Contains('\', [StringComparison]::Ordinal) -or
        $Path.StartsWith('/', [StringComparison]::Ordinal) -or
        $Path.EndsWith('/', [StringComparison]::Ordinal) -or
        $Path -match '(?:^|/)\.{1,2}(?:/|$)' -or
        $Path.Normalize([Text.NormalizationForm]::FormC) -cne $Path) {
        throw "Git path is not a canonical ASCII repository path: $Path"
    }

    return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Path))
}

function Get-Arm64GitBlobOid {
    [CmdletBinding(DefaultParameterSetName = 'Stream')]
    param(
        [Parameter(Mandatory, ParameterSetName = 'Stream')]
        [IO.Stream]$Stream,
        [Parameter(Mandatory, ParameterSetName = 'Stream')]
        [long]$Length,
        [Parameter(Mandatory, ParameterSetName = 'Bytes')]
        [AllowEmptyCollection()]
        [byte[]]$Bytes
    )

    if ($PSCmdlet.ParameterSetName -ceq 'Bytes') {
        $Stream = [IO.MemoryStream]::new($Bytes, $false)
        $Length = $Bytes.LongLength
        $disposeStream = $true
    }
    else {
        $disposeStream = $false
    }

    if ($Length -lt 0 -or -not $Stream.CanRead) {
        throw 'Git blob input must be a readable stream with a non-negative length.'
    }

    $sha1 = [Security.Cryptography.SHA1]::Create()
    try {
        $prefix = [Text.Encoding]::UTF8.GetBytes("blob $Length`0")
        [void]$sha1.TransformBlock($prefix, 0, $prefix.Length, $null, 0)

        $remaining = $Length
        $buffer = [byte[]]::new(65536)
        while ($remaining -gt 0) {
            $requested = [int][Math]::Min($buffer.Length, $remaining)
            $read = $Stream.Read($buffer, 0, $requested)
            if ($read -le 0) {
                throw 'Git blob stream ended before its declared byte length.'
            }
            [void]$sha1.TransformBlock($buffer, 0, $read, $null, 0)
            $remaining -= $read
        }
        if ($Stream.ReadByte() -ne -1) {
            throw 'Git blob stream exceeds its declared byte length.'
        }
        [void]$sha1.TransformFinalBlock([byte[]]::new(0), 0, 0)
        return -join ($sha1.Hash | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $sha1.Dispose()
        if ($disposeStream) {
            $Stream.Dispose()
        }
    }
}

function Get-Arm64FileBlobIdentity {
    param([Parameter(Mandatory)][string]$Path)

    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    try {
        $length = $stream.Length
        $oid = Get-Arm64GitBlobOid -Stream $stream -Length $length
        return [pscustomobject][ordered]@{
            byte_length = [long]$length
            oid         = [string]$oid
        }
    }
    finally {
        $stream.Dispose()
    }
}

function New-Arm64SourceBinding {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Mode,
        [Parameter(Mandatory)][string]$ObjectType,
        [Parameter(Mandatory)][long]$ByteLength,
        [Parameter(Mandatory)][string]$Oid
    )

    if ($Mode -notin @('100644', '100755') -or
        $ObjectType -cne 'blob' -or
        $ByteLength -lt 0 -or
        -not (Test-Arm64GitObjectId $Oid)) {
        throw "Invalid Git blob source binding: $Path"
    }

    return [pscustomobject][ordered]@{
        path                 = $Path
        raw_path_utf8_base64 = Get-Arm64RawPathIdentity -Path $Path
        mode                 = $Mode
        object_type          = $ObjectType
        byte_length          = $ByteLength
        oid                  = $Oid
    }
}

function Assert-Arm64SourceBinding {
    param(
        [Parameter(Mandatory)][object]$Binding,
        [Parameter(Mandatory)][string]$Label
    )

    $expectedProperties = @(
        'path',
        'raw_path_utf8_base64',
        'mode',
        'object_type',
        'byte_length',
        'oid'
    )
    $actualProperties = @($Binding.PSObject.Properties.Name | Sort-Object)
    if (($actualProperties -join "`0") -cne (($expectedProperties | Sort-Object) -join "`0")) {
        throw "Source binding schema is not exact: $Label"
    }
    $expectedRawPath = Get-Arm64RawPathIdentity -Path ([string]$Binding.path)
    if ($Binding.raw_path_utf8_base64 -cne $expectedRawPath -or
        $Binding.mode -notin @('100644', '100755') -or
        $Binding.object_type -cne 'blob' -or
        -not ($Binding.byte_length -is [int] -or $Binding.byte_length -is [long]) -or
        [long]$Binding.byte_length -lt 0 -or
        -not (Test-Arm64GitObjectId $Binding.oid)) {
        throw "Source binding values are invalid: $Label"
    }
}

function Test-Arm64SourceBindingEqual {
    param(
        [Parameter(Mandatory)][object]$Expected,
        [Parameter(Mandatory)][object]$Actual
    )

    Assert-Arm64SourceBinding -Binding $Expected -Label 'expected'
    Assert-Arm64SourceBinding -Binding $Actual -Label 'actual'
    foreach ($property in @(
            'path',
            'raw_path_utf8_base64',
            'mode',
            'object_type',
            'byte_length',
            'oid')) {
        if ($Expected.$property -cne $Actual.$property) {
            return $false
        }
    }
    return $true
}

function Assert-Arm64SourceBindingSetsEqual {
    param(
        [Parameter(Mandatory)][object[]]$Expected,
        [Parameter(Mandatory)][object[]]$Actual,
        [string]$Label = 'source'
    )

    $expectedSorted = @($Expected | Sort-Object path)
    $actualSorted = @($Actual | Sort-Object path)
    if ($expectedSorted.Count -ne $actualSorted.Count) {
        throw "$Label-set-mismatch"
    }
    for ($index = 0; $index -lt $expectedSorted.Count; $index++) {
        if (-not (Test-Arm64SourceBindingEqual `
                -Expected $expectedSorted[$index] `
                -Actual $actualSorted[$index])) {
            throw "$Label-binding-mismatch:$($expectedSorted[$index].path)"
        }
    }
}

function Get-Arm64LocalGitTreeEntries {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [string]$Revision = 'HEAD'
    )

    if ($Revision -cnotmatch '^(?:HEAD|[0-9a-f]{40})$') {
        throw "Invalid Git revision for source binding: $Revision"
    }
    [void](Assert-Arm64GitObjectFormat -RepositoryRoot $RepositoryRoot)
    [void](Assert-Arm64GitRepositoryHygiene -RepositoryRoot $RepositoryRoot)
    $topLevelResult = Invoke-Arm64Git `
        -RepositoryRoot $RepositoryRoot `
        -GitArguments @('rev-parse', '--show-toplevel')
    if ($topLevelResult.ExitCode -ne 0 -or $topLevelResult.Lines.Count -ne 1) {
        throw 'Git source-binding root must be the exact repository top level.'
    }
    $topLevel = $topLevelResult.Lines[0].Trim()
    if ([IO.Path]::GetFullPath($topLevel) -cne [IO.Path]::GetFullPath($RepositoryRoot)) {
        throw 'Git source-binding root must be the exact repository top level.'
    }
    $treeResult = Invoke-Arm64Git `
        -RepositoryRoot $RepositoryRoot `
        -GitArguments @('ls-tree', '-r', '-t', '-l', '--full-tree', $Revision)
    if ($treeResult.ExitCode -ne 0) {
        throw "Unable to enumerate Git tree: $Revision"
    }
    $lines = @($treeResult.Lines)

    $entries = [Collections.Generic.List[object]]::new()
    $exactPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $aliasPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($line in $lines) {
        if ($line -cnotmatch '^(?<mode>[0-9]{6}) (?<type>[a-z]+) (?<oid>[0-9a-f]+) +(?<size>[0-9]+|-)\t(?<path>.+)$') {
            throw 'Malformed or truncated Git tree entry.'
        }
        $mode = $Matches.mode
        $type = $Matches.type
        $oid = $Matches.oid
        $sizeText = $Matches.size
        $path = $Matches.path
        [void](Get-Arm64RawPathIdentity -Path $path)
        if (-not (Test-Arm64GitObjectId $oid)) {
            throw "Git tree entry has an invalid object ID: $path"
        }

        $validShape = ($type -ceq 'tree' -and $mode -ceq '040000' -and $sizeText -ceq '-') -or
            ($type -ceq 'blob' -and $mode -in @('100644', '100755', '120000') -and
                $sizeText -cmatch '^[0-9]+$') -or
            ($type -ceq 'commit' -and $mode -ceq '160000' -and $sizeText -ceq '-')
        if (-not $validShape) {
            throw "Git tree entry has an invalid type/mode/size tuple: $path"
        }

        if (-not $exactPaths.Add($path)) {
            throw "Git tree contains a duplicate path: $path"
        }
        $aliasKey = $path.Normalize([Text.NormalizationForm]::FormC).ToUpperInvariant()
        if (-not $aliasPaths.Add($aliasKey)) {
            throw "Git tree contains a casefold or NFC path alias: $path"
        }

        [void]$entries.Add([pscustomobject][ordered]@{
                path        = $path
                mode        = $mode
                object_type = $type
                oid         = $oid
                byte_length = if ($sizeText -ceq '-') { $null } else { [long]$sizeText }
            })
    }
    return @($entries)
}

function Get-Arm64ValidatedRestTreeEntries {
    param(
        [Parameter(Mandatory)][object]$TreeResponse,
        [Parameter(Mandatory)][string]$ExpectedTree,
        [int]$MaximumRecords = 10000
    )

    if (-not (Test-Arm64GitObjectId $ExpectedTree) -or
        $TreeResponse.sha -cne $ExpectedTree -or
        $TreeResponse.truncated -isnot [bool] -or
        $TreeResponse.truncated -or
        $TreeResponse.tree -is [string] -or
        $TreeResponse.tree -isnot [Collections.IEnumerable]) {
        throw 'Candidate tree response is malformed, moved, or truncated.'
    }
    $rawEntries = @($TreeResponse.tree)
    if ($rawEntries.Count -gt $MaximumRecords) {
        throw 'Candidate tree response exceeds the record limit.'
    }

    $entries = [Collections.Generic.List[object]]::new()
    $exactPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $aliasPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($entry in $rawEntries) {
        foreach ($propertyName in @('path', 'mode', 'type', 'sha', 'url')) {
            if ($null -eq $entry.PSObject.Properties[$propertyName]) {
                throw "Candidate tree entry is missing $propertyName."
            }
        }
        $path = [string]$entry.path
        $mode = [string]$entry.mode
        $type = [string]$entry.type
        $oid = [string]$entry.sha
        [void](Get-Arm64RawPathIdentity -Path $path)
        if (-not (Test-Arm64GitObjectId $oid)) {
            throw "Candidate tree entry has an invalid object ID: $path"
        }
        if (-not $exactPaths.Add($path)) {
            throw "Candidate tree contains a duplicate path: $path"
        }
        $aliasKey = $path.Normalize([Text.NormalizationForm]::FormC).ToUpperInvariant()
        if (-not $aliasPaths.Add($aliasKey)) {
            throw "Candidate tree contains a casefold or NFC path alias: $path"
        }

        $sizeProperty = $entry.PSObject.Properties['size']
        $validShape = ($type -ceq 'tree' -and $mode -ceq '040000' -and
                $null -eq $sizeProperty) -or
            ($type -ceq 'blob' -and $mode -in @('100644', '100755', '120000') -and
                $null -ne $sizeProperty -and
                ($sizeProperty.Value -is [int] -or $sizeProperty.Value -is [long]) -and
                [long]$sizeProperty.Value -ge 0) -or
            ($type -ceq 'commit' -and $mode -ceq '160000' -and
                $null -eq $sizeProperty)
        if (-not $validShape) {
            throw "Candidate tree entry has an invalid type/mode/size tuple: $path"
        }

        if ($type -ceq 'commit' -or $mode -ceq '120000') {
            throw "Candidate tree contains a gitlink or symlink: $path"
        }
        if ($path -in @('.github/workflows', '.github/scripts', '.github/policies') -and
            $type -cne 'tree') {
            throw "Candidate blob occupies a protected directory namespace: $path"
        }
        if ($path.StartsWith('.github/workflows/', [StringComparison]::Ordinal) -and
            (($type -ceq 'tree') -or
                ($type -ceq 'blob' -and $path -cnotmatch '^\.github/workflows/[^/]+\.ya?ml$'))) {
            throw "Candidate workflow namespace contains an unexpected entry: $path"
        }

        [void]$entries.Add([pscustomobject][ordered]@{
                path        = $path
                mode        = $mode
                object_type = $type
                oid         = $oid
                byte_length = if ($null -eq $sizeProperty) {
                    $null
                }
                else {
                    [long]$sizeProperty.Value
                }
                api_url     = [string]$entry.url
            })
    }
    return @($entries)
}

function Get-Arm64ProtectedGitSourceBindings {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [string]$Revision = 'HEAD'
    )

    $protectedPrefixes = @('.github/workflows/', '.github/scripts/', '.github/policies/')
    $directoryNamespaces = @('.github/workflows', '.github/scripts', '.github/policies')
    $protectedRootFiles = @('.gitattributes', 'package-lock.json', 'package.json')
    $bindings = [Collections.Generic.List[object]]::new()
    foreach ($entry in Get-Arm64LocalGitTreeEntries `
            -RepositoryRoot $RepositoryRoot `
            -Revision $Revision) {
        $isProtected = @($protectedPrefixes | Where-Object {
                $entry.path.StartsWith($_, [StringComparison]::Ordinal)
            }).Count -gt 0 -or $protectedRootFiles -ccontains $entry.path
        if (-not $isProtected -and $directoryNamespaces -cnotcontains $entry.path) {
            continue
        }
        if ($entry.object_type -ceq 'commit' -or $entry.mode -ceq '120000') {
            throw "Protected Git namespace contains a gitlink or symlink: $($entry.path)"
        }
        if ($directoryNamespaces -ccontains $entry.path) {
            if ($entry.object_type -cne 'tree') {
                throw "Protected directory namespace is not a tree: $($entry.path)"
            }
            continue
        }
        if ($entry.path.StartsWith('.github/workflows/', [StringComparison]::Ordinal) -and
            ($entry.object_type -cne 'blob' -or
                $entry.path.Substring('.github/workflows/'.Length).Contains(
                    '/',
                    [StringComparison]::Ordinal
                ) -or
                $entry.path -cnotmatch '\.ya?ml$')) {
            throw "Unexpected entry under the active workflow namespace: $($entry.path)"
        }
        if ($entry.object_type -ceq 'tree') {
            continue
        }
        if ($entry.object_type -cne 'blob') {
            throw "Unexpected protected Git tree entry: $($entry.path)"
        }

        $filePath = Join-Path $RepositoryRoot (
            $entry.path.Replace('/', [IO.Path]::DirectorySeparatorChar)
        )
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) {
            throw "Protected Git blob is absent from the checkout: $($entry.path)"
        }
        $identity = Get-Arm64FileBlobIdentity -Path $filePath
        if ($identity.byte_length -ne $entry.byte_length -or $identity.oid -cne $entry.oid) {
            throw "Protected checkout bytes differ from the Git object: $($entry.path)"
        }
        [void]$bindings.Add((New-Arm64SourceBinding `
                    -Path $entry.path `
                    -Mode $entry.mode `
                    -ObjectType $entry.object_type `
                    -ByteLength $entry.byte_length `
                    -Oid $entry.oid))
    }
    return @($bindings | Sort-Object path)
}

if ($MyInvocation.InvocationName -ne '.') {
    throw 'git-object-integrity.ps1 is a dot-source-only helper.'
}
