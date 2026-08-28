[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ModuleManifest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# This helper is the only place PowerShell-Yaml builds an object model, and it runs as a
# bounded child process. It reads the exact bytes the caller already validated from standard
# input and never opens a candidate path, so a post-validation mutation cannot change what is
# parsed. Exit codes are deterministic and no candidate text is ever written to any stream.
$maximumInputBytes = 1048576
$expectedModuleFiles = [ordered]@{
    'powershell-yaml.psd1' = 'b17d30f63eee0fd5e5bb074043045c499e87b254c044ce5b1a5e71df2dd8c469'
    'powershell-yaml.psm1' = '415b0de1b4d5af6980ec50316d3267fa19663b7dbf809d219783b41ed39b2e5d'
}
$expectedAssemblyVersion = '16.0.0.0'
$expectedAssemblyPublicKey = (
    '0024000004800000940000000602000000240000525341310004000001000100' +
    '65e52a453dde5c5b4be5bbe2205755727fce80244b79b894faf8793d80f7db9a' +
    '96d360b51c220782db32aacee4cb5b8a91bee33aeec700e1f21895c4baadef50' +
    '1eeeac609220d1651603b378173811ee5bb6a002df973d38821bd2fef820c00c1' +
    '74a69faec326a1983b570f07ec66147026b9c8753465de3a8d0c44b613b02af'
)
$expectedAssemblyPublicKeyToken = 'ec19458f3c15af5e'

function Get-FileSha256 {
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

try {
    if (-not [IO.Path]::IsPathFullyQualified($ModuleManifest) -or
        -not (Test-Path -LiteralPath $ModuleManifest -PathType Leaf)) {
        exit 11
    }
    $ModuleManifest = [IO.Path]::GetFullPath($ModuleManifest)
    $moduleBase = Split-Path $ModuleManifest -Parent
    if ((Split-Path $ModuleManifest -Leaf) -cne 'powershell-yaml.psd1' -or
        (Split-Path $moduleBase -Leaf) -cne '0.4.12' -or
        (Split-Path (Split-Path $moduleBase -Parent) -Leaf) -cne
            'powershell-yaml') {
        exit 11
    }
    foreach ($relative in $expectedModuleFiles.Keys) {
        $path = Join-Path $moduleBase $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileSha256 -Path $path) -cne $expectedModuleFiles[$relative]) {
            exit 11
        }
    }
    $platform = if ($PSVersionTable.PSEdition -ceq 'Core') {
        [pscustomobject]@{
            Assembly = 'lib\netstandard2.1\YamlDotNet.dll'
            AssemblySha256 =
                'd7543a03a69f14ca1e302aa2bbb09777200b72e0c6db0d0eb7614593f5c33e0f'
            Serializer = 'lib\netstandard2.1\PowerShellYamlSerializer.dll'
            SerializerSha256 =
                'c9193f2fb5afa40af61d908589fdd0929ab58472be215fc2afb692194d53210d'
        }
    }
    else {
        [pscustomobject]@{
            Assembly = 'lib\net47\YamlDotNet.dll'
            AssemblySha256 =
                'd35c770d92632bd94bba4203db05eee5ebce6e6ea6d92e7ebe8997a942b5321c'
            Serializer = 'lib\net47\PowerShellYamlSerializer.dll'
            SerializerSha256 =
                'a5bdd33675629ca88cf05cd08150a19a69bc20b21cbe1d1e5e55fe63a332062a'
        }
    }
    $assemblyPath = [IO.Path]::GetFullPath((Join-Path $moduleBase $platform.Assembly))
    $serializerPath = [IO.Path]::GetFullPath((Join-Path $moduleBase $platform.Serializer))
    if (-not $assemblyPath.StartsWith(
            "$moduleBase$([IO.Path]::DirectorySeparatorChar)",
            [StringComparison]::OrdinalIgnoreCase
        ) -or
        (Get-FileSha256 -Path $assemblyPath) -cne $platform.AssemblySha256 -or
        (Get-FileSha256 -Path $serializerPath) -cne $platform.SerializerSha256) {
        exit 11
    }

    $standardInput = [Console]::OpenStandardInput()
    $collected = [IO.MemoryStream]::new()
    try {
        $chunk = [byte[]]::new(8192)
        while (($read = $standardInput.Read($chunk, 0, $chunk.Length)) -gt 0) {
            if ($collected.Length + $read -gt $maximumInputBytes) {
                exit 12
            }
            $collected.Write($chunk, 0, $read)
        }
        $bytes = $collected.ToArray()
    }
    finally {
        $collected.Dispose()
    }

    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    }
    catch {
        exit 13
    }

    Import-Module `
        -Name $ModuleManifest `
        -RequiredVersion '0.4.12' `
        -Force `
        -ErrorAction Stop
    $commands = @(Get-Command `
            -Name ConvertFrom-Yaml `
            -Module powershell-yaml `
            -CommandType Function `
            -All `
            -ErrorAction Stop)
    if ($commands.Count -ne 1 -or
        $null -eq $commands[0].Module -or
        $commands[0].Module.Name -cne 'powershell-yaml' -or
        $commands[0].Module.Version.ToString() -cne '0.4.12' -or
        [IO.Path]::GetFullPath($commands[0].Module.Path) -cne
            [IO.Path]::GetFullPath((Join-Path $moduleBase 'powershell-yaml.psm1'))) {
        exit 14
    }
    $yamlAssemblies = @([AppDomain]::CurrentDomain.GetAssemblies() | Where-Object {
            $_.GetName().Name -ceq 'YamlDotNet'
        })
    if ($yamlAssemblies.Count -ne 1 -or
        $yamlAssemblies[0].IsDynamic -or
        [string]::IsNullOrEmpty($yamlAssemblies[0].Location) -or
        [IO.Path]::GetFullPath($yamlAssemblies[0].Location) -cne $assemblyPath) {
        exit 14
    }
    $assemblyName = $yamlAssemblies[0].GetName()
    if ($assemblyName.Version.ToString() -cne $expectedAssemblyVersion -or
        [Convert]::ToHexString($assemblyName.GetPublicKey()).ToLowerInvariant() -cne
            $expectedAssemblyPublicKey -or
        [Convert]::ToHexString(
            $assemblyName.GetPublicKeyToken()
        ).ToLowerInvariant() -cne $expectedAssemblyPublicKeyToken) {
        exit 14
    }

    $document = $text | & $commands[0]
    $json = $document | ConvertTo-Json -Compress -Depth 64
    if ($null -eq $json) {
        $json = 'null'
    }

    $payload = [Text.UTF8Encoding]::new($false).GetBytes([string]$json)
    $standardOutput = [Console]::OpenStandardOutput()
    $standardOutput.Write($payload, 0, $payload.Length)
    $standardOutput.Flush()
    exit 0
}
catch {
    exit 15
}
