param(
    [Parameter(Mandatory = $true)]
    [string]$Compiler,

    [Parameter(Mandatory = $true)]
    [string]$IncludeRoot,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$fixture = Join-Path $repositoryRoot 'tests\arm64-interlocked-exchange-runtime.c'
$executable = Join-Path $OutputDirectory 'interlocked-exchange-runtime.exe'
$stdout = Join-Path $OutputDirectory 'runtime.stdout.txt'
$stderr = Join-Path $OutputDirectory 'runtime.stderr.txt'

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
& $Compiler -O2 -I $IncludeRoot $fixture -o $executable
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$process = Start-Process -FilePath $executable -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
if ($process.ExitCode -ne 0) {
    throw "Interlocked exchange runtime control exited $($process.ExitCode)."
}

$actual = (Get-Content $stdout -Raw).Trim()
if ($actual -ne 'interlocked-exchange-runtime-ok') {
    throw "Unexpected runtime control output: $actual"
}
