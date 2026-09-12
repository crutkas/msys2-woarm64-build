[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CompilerPrefix,
    [Parameter(Mandatory)][string]$CompilerReceipt,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$CompilerReceiptSHA256,
    [string]$OutputRoot = 'C:\ag-e138920f\ssh-libxcrypt-msys-01'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$output = [System.IO.Path]::GetRelativePath((Get-Location).Path, $OutputRoot)
$arguments = @(
    '-B', (Join-Path $PSScriptRoot 'build-msys-library.py'),
    '--package', 'libxcrypt',
    '--source', 'C:\ag-e138920f\ssh-source-adoption-01\libxcrypt\source',
    '--manifest', 'C:\ag-e138920f\ssh-source-adoption-01\libxcrypt\source.prepare.json',
    '--prefix', $CompilerPrefix,
    '--compiler-receipt', $CompilerReceipt,
    '--compiler-receipt-sha256', $CompilerReceiptSHA256,
    '--bootstrap', 'C:\ag-e138920f\ssh-bootstrap-01\msys64',
    '--bootstrap-receipt', 'C:\ag-e138920f\ssh-bootstrap-01\msys64.copy.json',
    '--native-job-prefix', 'C:\ag-e138920f\native-test-driver-02',
    '--output', $output,
    '--jobs', '1'
)
& 'C:\Program Files\Python314-arm64\python.exe' @arguments
exit $LASTEXITCODE
