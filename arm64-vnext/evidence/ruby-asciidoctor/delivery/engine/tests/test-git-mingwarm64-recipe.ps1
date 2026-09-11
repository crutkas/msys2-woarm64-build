param(
    [Parameter(Mandatory)][string] $PinnedRecipe,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$prepare = Join-Path $PSScriptRoot '..\.github\scripts\prepare-git-mingwarm64-recipe.ps1'
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Control output must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$result = & $prepare -SourceDirectory $PinnedRecipe -OutputDirectory "$OutputDirectory\mapped"
if ($result.Status -cne 'namespace-prepared-not-package-admitted' -or
    $result.Namespace.CC -cne 'gcc' -or $result.Namespace.MINGW_PACKAGE_PREFIX -cne 'mingw-w64-aarch64') {
    throw 'Incorrect namespace mapping.'
}
$text = [IO.File]::ReadAllText("$OutputDirectory\mapped\PKGBUILD")
if ([regex]::Matches($text, '(?m)^package_git[^ ]* \(\)').Count -ne 16 -or
    -not $text.Contains('"${MINGW_PACKAGE_PREFIX}-rust"') -or
    -not $text.Contains('targets="$targets html"') -or -not $text.Contains('targets="$targets man"')) {
    throw 'Original split/features were not retained.'
}
'PASS: exact recipe gets only MINGWARM64 declaration; splits/Rust/docs preserved'
$rejected = $false
try { $null = & $prepare -SourceDirectory "$OutputDirectory\mapped" -OutputDirectory "$OutputDirectory\double-mapped" } catch {
    if ($_.Exception.Message -notlike 'Only the pinned Git*') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Unpinned/already-modified recipe accepted.' }
'PASS: modified recipe is rejected without fake remapping'
$rejected = $false
try { $null = & $prepare -SourceDirectory $PinnedRecipe -OutputDirectory "$OutputDirectory\mapped" } catch {
    if ($_.Exception.Message -cne 'Prepared Git recipe output must be new.') { throw }
    $rejected = $true
}
if (-not $rejected) { throw 'Existing output accepted.' }
'PASS: existing prepared output preserved'
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$OutputDirectory\mapping-result.json" -Encoding utf8
