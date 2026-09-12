#requires -Version 7.3
param(
    [Parameter(Mandatory)][string] $SourceDirectory,
    [Parameter(Mandatory)][string] $OutputDirectory
)
$ErrorActionPreference = 'Stop'
$mapping = & "$PSScriptRoot\prepare-git-mingwarm64-recipe.ps1" @PSBoundParameters
$path = Join-Path $OutputDirectory 'PKGBUILD'
$text = [IO.File]::ReadAllText($path).Replace("`r`n","`n")
$activation = '  source "${startdir}/native-rust-environment.sh" || return 1'
$changes = @(
    @{Before='prepare () {';After="prepare () {`n$activation"},
    @{Before='build() {';After="build() {`n$activation"},
    @{Before='LDFLAGS = $LDFLAGS';After='LDFLAGS = $LDFLAGS $WOARM64_RUST_LDFLAGS'+"`n`t"+'EXTLIBS += $WOARM64_RUST_EXTLIBS'},
    @{Before='  export PATH="$MINGW_PREFIX/bin:$PATH"';After='  export PATH="$MINGW_PREFIX/bin:$PATH"'+"`n$activation"}
)
foreach ($change in $changes) {
    if ([regex]::Matches($text,[regex]::Escape($change.Before)).Count -ne 1) { throw 'Pinned Git Rust integration anchor changed.' }
    $text = $text.Replace($change.Before,$change.After)
}
Copy-Item -LiteralPath "$PSScriptRoot\native-rust-environment.sh" -Destination (Join-Path $OutputDirectory 'native-rust-environment.sh')
[IO.File]::WriteAllText($path,$text,[Text.UTF8Encoding]::new($false))
$mapping.AfterSHA256 = (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()
$mapping.Status = 'native-rust-git-recipe-prepared-not-executed'
$mapping.Preserved = 'All Git package splits, dependencies, docs/Rust defaults, VCS tag/commit/archive checksums and signing/installation behavior'
$mapping.Scope = 'Requires explicit RustPrefix/RustQualification adapter arguments; native LLVM/dynamic-unwind bridge does not replace default BFD'
$mapping
