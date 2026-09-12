$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot '..\.github\scripts\get-toolchain-epoch.ps1'
$rows = @(
    @{ Path = 'bin\gcc.exe'; SHA256 = 'a' * 64 },
    @{ Path = 'libexec\cc1.exe'; SHA256 = 'b' * 64 },
    @{ Path = 'lib\libgcc.a'; SHA256 = 'c' * 64 }
)
$baseline = & $script -Inputs $rows
$reversed = & $script -Inputs @($rows[2], $rows[1], $rows[0])
if ($baseline -cne $reversed) { throw 'Inventory ordering changed the epoch.' }
'PASS: inventory order does not change epoch'
foreach ($index in 1, 2) {
    $changed = @($rows | ForEach-Object { @{ Path = $_.Path; SHA256 = $_.SHA256 } })
    $changed[$index].SHA256 = 'd' * 64
    if ((& $script -Inputs $changed) -ceq $baseline) { throw 'Support/library change did not invalidate epoch.' }
    "PASS: $($changed[$index].Path) invalidates epoch with gcc.exe unchanged"
}
foreach ($invalid in @(
    ,@($rows[0], $rows[0])
    ,@(@{ Path = 'bin\gcc.exe'; SHA256 = 'bad' })
    ,@(@{ Path = 'C:\external\gcc.exe'; SHA256 = 'a' * 64 })
)) {
    $rejected = $false
    try { $null = & $script -Inputs $invalid } catch {
        if ($_.Exception.Message -notlike 'Invalid or duplicate cache input:*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Invalid inventory accepted.' }
    'PASS: invalid inventory rejected'
}
