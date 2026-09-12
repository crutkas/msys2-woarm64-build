#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $Prefix,
    [Parameter(Mandatory)][string] $Qualification
)
$ErrorActionPreference = 'Stop'
$reader = "$PSScriptRoot\..\.github\scripts\test-qualified-rust-bootstrap.ps1"
$baseline = '50444850d2359e3841a2daacf98988f06537568ad18199c48200ef2787568836'
$accepted = & $reader -Prefix $Prefix -Qualification $Qualification -GccEpoch $baseline
if ($accepted.Target -cne 'aarch64-pc-windows-gnullvm' -or $accepted.Files.Count -ne 161) { throw 'Wrong Rust bootstrap binding.' }
'PASS: exact installed Rust members and qualified GCC bridge accepted'
$rejected = $false
try {
    $null = & $reader -Prefix $Prefix -Qualification $Qualification -GccEpoch '5382e3f64bfd1314f168e2df67ce1abd79f3574acf32538708e7a2c8432fb3b7'
} catch {
    if ($_.Exception.Message -cne 'Rust bootstrap is not qualified against this exact GCC cohort.') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Rust proof was silently rebound to a different GCC epoch.' }
'PASS: even a header successor requires an explicitly qualified Rust/GCC bridge'
