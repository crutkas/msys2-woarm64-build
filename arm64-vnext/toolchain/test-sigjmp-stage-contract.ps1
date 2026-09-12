[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $RuntimeReceipt,
    [Parameter(Mandatory)][string] $OutputDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Use a new negative-control evidence directory.' }
$out = [IO.Directory]::CreateDirectory($OutputDirectory).FullName
$original = Get-Content -Raw -LiteralPath $RuntimeReceipt
$cohort = $original | ConvertFrom-Json
$cases = if ($cohort.status -ceq 'coherent-runtime-ucontext-and-bounded-upstream-consumer-qualified') {
    @(
        @{ Name = 'unaligned-stack'; Change = { param($r) $r.results.arm64_entry_sp_alignment = 8 }; Expected = 'entry/return and consumer contract' },
        @{ Name = 'active-writer'; Change = { param($r) $r.ownership.active_runtime_jobs = 1 }; Expected = 'entry/return and consumer contract' },
        @{ Name = 'missing-stack-args'; Change = { param($r) $r.results.argument_counts_executed = @(0,1,8) }; Expected = 'entry/return and consumer contract' },
        @{ Name = 'failed-return'; Change = { param($r) $r.results.lr_continuation_and_linked_return = $false }; Expected = 'required result' },
        @{ Name = 'failed-invalid-context'; Change = { param($r) $r.results.invalid_context_returns_minus_one_einval_and_restores_mask = $false }; Expected = 'required result' },
        @{ Name = 'missing-inventory'; Change = { param($r) }; Expected = 'complete sealed runtime/header input inventory' }
    )
} else { @(
    @{ Name = 'old-layout'; Change = { param($r) $r.layout.new_jmp_buf_bytes = 176 }; Expected = 'required public buffer ABI' },
    @{ Name = 'active-writer'; Change = { param($r) $r.ownership.active_runtime_jobs = 1 }; Expected = 'required public buffer ABI' },
    @{ Name = 'failed-mask'; Change = { param($r) $r.results.unmasked_after_every_siglongjmp = $false }; Expected = 'required public buffer ABI' },
    @{ Name = 'missing-inventory'; Change = { param($r) }; Expected = 'complete sealed runtime/header input inventory' }
) }
$results = @()
foreach ($case in $cases) {
    $record = $original | ConvertFrom-Json
    & $case.Change $record
    $path = Join-Path $out "$($case.Name).json"
    $record | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $path -Encoding utf8
    $prefix = Join-Path $out "$($case.Name)-sdk"
    $evidence = Join-Path $out "$($case.Name)-stage.json"
    $message = ''
    try {
        & "$PSScriptRoot\Stage-NativeMsysRuntime.ps1" -Baseline "$out\not-a-compiler-prefix" `
            -RuntimeSysroot "$out\not-a-runtime-sysroot" -RuntimeDll "$out\not-a-runtime.dll" `
            -RuntimeReceipt $path -RuntimeReceiptSHA256 (Get-FileHash $path).Hash.ToLowerInvariant() `
            -Prefix $prefix -StageReceipt $evidence
    } catch {
        $message = $_.Exception.Message
    }
    if (-not $message.Contains($case.Expected) -or
        (Test-Path -LiteralPath $prefix) -or (Test-Path -LiteralPath $evidence)) {
        throw "Invalid input was not rejected before staging/compiler execution: $($case.Name): $message"
    }
    $results += [pscustomobject]@{ Name = $case.Name; ExpectedFailure = $message; NoOutputCreated = $true }
}
$results | ConvertTo-Json -Depth 4 | Set-Content "$out\result.json" -Encoding utf8
Write-Output "$($cases.Count) runtime ABI contract negatives rejected before any SDK or compiler access."
