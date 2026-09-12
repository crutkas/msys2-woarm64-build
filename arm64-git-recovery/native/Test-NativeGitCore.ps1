param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$Output = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $Output) { throw 'A new disposable local fixture is required.' }
[void][IO.Directory]::CreateDirectory("$Output\home")
$config = Join-Path "$Output\home" 'empty.gitconfig'
[IO.File]::WriteAllText($config, '', [Text.UTF8Encoding]::new($false))
$git = "$Root\clangarm64\bin\git.exe"
$cases = [Collections.Generic.List[object]]::new()
function Invoke-FixtureGit([string]$Name, [string[]]$Arguments, [int]$ExpectedExit = 0) {
    $start = [Diagnostics.ProcessStartInfo]::new($git)
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.WorkingDirectory = $Output
    $start.Environment.Clear()
    foreach ($envName in @('SystemRoot','WINDIR')) { $start.Environment[$envName] = [Environment]::GetEnvironmentVariable($envName) }
    $start.Environment['PATH'] = "$Root\clangarm64\bin;$Root\usr\bin;$env:SystemRoot\System32"
    $start.Environment['HOME'] = "$Output\home"
    $start.Environment['GIT_CONFIG_NOSYSTEM'] = '1'
    $start.Environment['GIT_CONFIG_GLOBAL'] = $config
    $start.Environment['GIT_TERMINAL_PROMPT'] = '0'
    $start.Environment['GIT_EXEC_PATH'] = "$Root\clangarm64\libexec\git-core"
    $start.Environment['GIT_AUTHOR_NAME'] = 'Native local fixture'
    $start.Environment['GIT_COMMITTER_NAME'] = 'Native local fixture'
    $start.Environment['GIT_AUTHOR_EMAIL'] = 'fixture@example.invalid'
    $start.Environment['GIT_COMMITTER_EMAIL'] = 'fixture@example.invalid'
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::Start($start)
    try {
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errTask = $process.StandardError.ReadToEndAsync()
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(60000)) { throw "Timed out: $Name" }
        $record = [ordered]@{Name=$Name; Arguments=$Arguments; ExitCode=$process.ExitCode;
            Stdout=$outTask.GetAwaiter().GetResult(); Stderr=$errTask.GetAwaiter().GetResult()}
        $cases.Add($record)
        if ($process.ExitCode -ne $ExpectedExit) { throw "$Name failed with $($process.ExitCode): $($record.Stderr)" }
        return $record.Stdout.Trim()
    }
    finally {
        if (-not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
}
$report = [ordered]@{Passed=$false; Scope='Disposable local repositories only; no credentials, remote server, or installed Git fallback'}
try {
    foreach ($repository in @('child','source')) {
        Invoke-FixtureGit "$repository-init" @('init','--initial-branch=main',"$Output\$repository") | Out-Null
        [IO.File]::WriteAllText("$Output\$repository\payload.txt", "$repository payload`n", [Text.UTF8Encoding]::new($false))
        Invoke-FixtureGit "$repository-add" @('-C',"$Output\$repository",'add','payload.txt') | Out-Null
        Invoke-FixtureGit "$repository-commit" @('-C',"$Output\$repository",'commit','-m','fixture') | Out-Null
    }
    $hook = "$Output\source\.git\hooks\pre-commit"
    [IO.File]::WriteAllText($hook, "#!/bin/sh`nprintf 'native-hook-ok\n' > .git/hook-observed`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::AppendAllText("$Output\source\payload.txt", "hook payload`n")
    Invoke-FixtureGit 'hook-positive' @('-C',"$Output\source",'commit','-am','hook-positive') | Out-Null
    if ((Get-Content "$Output\source\.git\hook-observed" -Raw).Trim() -cne 'native-hook-ok') { throw 'Hook did not execute.' }
    $head = Invoke-FixtureGit 'before-rejected-hook' @('-C',"$Output\source",'rev-parse','HEAD')
    [IO.File]::WriteAllText($hook, "#!/bin/sh`nexit 73`n", [Text.UTF8Encoding]::new($false))
    [IO.File]::AppendAllText("$Output\source\payload.txt", "rejected payload`n")
    Invoke-FixtureGit 'hook-negative' @('-C',"$Output\source",'commit','-am','must-not-commit') 1 | Out-Null
    if ((Invoke-FixtureGit 'after-rejected-hook' @('-C',"$Output\source",'rev-parse','HEAD')) -cne $head) {
        throw 'Failing hook created a commit.'
    }
    [IO.File]::WriteAllText($hook, "#!/bin/sh`nexit 0`n", [Text.UTF8Encoding]::new($false))
    Invoke-FixtureGit 'after-hook-commit' @('-C',"$Output\source",'commit','-am','after-hook') | Out-Null
    Invoke-FixtureGit 'submodule-add' @('-C',"$Output\source",'-c','protocol.file.allow=always','submodule','add',"$Output\child",'sub module') | Out-Null
    Invoke-FixtureGit 'submodule-commit' @('-C',"$Output\source",'commit','-am','submodule') | Out-Null
    Invoke-FixtureGit 'recursive-clone' @('-c','protocol.file.allow=always','clone','--no-local','--recurse-submodules',"$Output\source","$Output\clone") | Out-Null
    if ((Invoke-FixtureGit 'child-original-head' @('-C',"$Output\child",'rev-parse','HEAD')) -cne
        (Invoke-FixtureGit 'child-clone-head' @('-C',"$Output\clone\sub module",'rev-parse','HEAD'))) { throw 'Submodule commit differs.' }
    Invoke-FixtureGit 'fsck' @('-C',"$Output\clone",'fsck','--strict') | Out-Null
    if ((Invoke-FixtureGit 'clean-status' @('-C',"$Output\clone",'status','--porcelain')) -ne '') { throw 'Clone is not clean.' }
    $report.Passed = $true
}
finally {
    $report.Cases = $cases.ToArray()
    $report.GitSHA256 = (Get-FileHash -LiteralPath $git).Hash
    $report.RuntimeSHA256 = (Get-FileHash -LiteralPath "$Root\usr\bin\msys-2.0.dll").Hash
    $report | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath "$Output\result.json"
}
