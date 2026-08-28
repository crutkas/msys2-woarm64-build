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

try {
    if (-not (Test-Path -LiteralPath $ModuleManifest -PathType Leaf)) {
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

    Import-Module -Name $ModuleManifest -RequiredVersion '0.4.12' -ErrorAction Stop
    $command = Get-Command ConvertFrom-Yaml -ErrorAction Stop
    if ($null -eq $command.Module -or
        $command.Module.Version.ToString() -cne '0.4.12') {
        exit 14
    }

    $document = $text | ConvertFrom-Yaml
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
