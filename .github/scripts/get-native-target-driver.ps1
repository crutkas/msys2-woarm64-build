#requires -Version 7.3
param([Parameter(Mandatory)][string] $Python)
$ErrorActionPreference = 'Stop'
$path = (Resolve-Path -LiteralPath $Python).ProviderPath
$pe = & "$PSScriptRoot\assert-arm64-pe.ps1" -Path $path | ConvertFrom-Json
$version = & $path -I -c 'import os,sys; assert os.name == "nt"; assert sys.version_info >= (3,11); print(sys.version.split()[0])'
if ($LASTEXITCODE -ne 0) { throw 'Native target relay requires Windows ARM64 Python 3.11+.' }
[pscustomobject]@{Path=$path;SHA256=$pe.sha256;Machine=$pe.machine;Version=$version}
