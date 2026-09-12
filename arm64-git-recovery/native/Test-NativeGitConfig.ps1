param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$EvidenceRoot
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
if (Test-Path -LiteralPath $EvidenceRoot) { throw 'Use a new fixture directory.' }
[void][IO.Directory]::CreateDirectory("$EvidenceRoot\home")
$globalConfigPath = Join-Path "$EvidenceRoot\home" 'empty.gitconfig'
[IO.File]::WriteAllText($globalConfigPath, '', [Text.UTF8Encoding]::new($false))
$source = Join-Path $PSScriptRoot 'Test-NativeGit.ps1'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Native Git harness has parser errors.' }
$function = $ast.Find({
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'New-ToolProcess'
}, $true)
if (-not $function) { throw 'Maintained harness process constructor not found.' }
. ([scriptblock]::Create($function.Extent.Text))
$cases = @()
foreach ($relative in @('clangarm64\bin\git.exe', 'bin\git.exe')) {
    $executable = Join-Path $Root $relative
    $process = New-ToolProcess $executable @('hash-object', '--stdin') $EvidenceRoot
    $inputError = $null
    try {
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errTask = $process.StandardError.ReadToEndAsync()
        try {
            $process.StandardInput.Write("hello`n")
            $process.StandardInput.Close()
        }
        catch [IO.IOException] {
            $inputError = $_.Exception.Message
        }
        if (-not $process.WaitForExit(15000)) { throw 'Hash-object fixture timed out.' }
        $stdout = $outTask.GetAwaiter().GetResult()
        $stderr = $errTask.GetAwaiter().GetResult()
        $cases += [ordered]@{Executable=$executable; ExitCode=$process.ExitCode; Stdout=$stdout; Stderr=$stderr;
            InputError=$inputError;
            ConfigPath=$process.StartInfo.Environment['GIT_CONFIG_GLOBAL'];
            Passed=($null -eq $inputError -and $process.ExitCode -eq 0 -and $stdout.Trim() -ceq 'ce013625030ba8dba906f756967f9e9ca394464a' -and
                $stderr -eq '' -and $process.StartInfo.Environment['GIT_CONFIG_GLOBAL'] -ceq $globalConfigPath)}
    }
    finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
}
$config = Get-Item -LiteralPath $globalConfigPath
$passed = @($cases | Where-Object {-not $_.Passed}).Count -eq 0 -and $config.Length -eq 0 -and
    ($config.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0
[ordered]@{Passed=$passed; Cases=$cases; ConfigPath=$globalConfigPath;
    Scope='Actual maintained process constructor with regular empty global config; no user config or credential access'} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$EvidenceRoot\result.json"
if (-not $passed) { throw 'Native Git config-isolation fixture failed.' }
