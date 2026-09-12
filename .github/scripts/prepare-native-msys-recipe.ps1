#requires -Version 7.3
param(
    [Parameter(Mandatory)][ValidateSet('less', 'pcre2')][string] $Package,
    [Parameter(Mandatory)][string] $SourceRecipe,
    [Parameter(Mandatory)][string] $OutputRecipe
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$recipes = @{
    less = @{
        Commit = 'fc03a3300db9bcdd0ccc082749e006abf1a04414'
        Blob = 'df539c5719125fc5915a69858dd10dd5882296ff'
        RecipeSHA256 = '9d443477b3a9ae72d677736d555b523ac947e6305cf1918922f4ad899827b522'
        SourceSHA256 = '0a801a147af1e41c1d9daa273316ce6d560053534659b5487ed5de6fc5032de4'
        RequiredText = @(
            "depends=('ncurses' 'libpcre2_8')"
            '--with-regex=pcre2'
        )
    }
    pcre2 = @{
        Commit = 'fc03a3300db9bcdd0ccc082749e006abf1a04414'
        Blob = '05ab02df2b4cc1d34697a4c6edc627b273a13026'
        RecipeSHA256 = 'df23b70c3950ef49b010a1fdf0ea010211e5d1365c0c10eb0ce6f32153f241a3'
        SourceSHA256 = 'b6c68fdf6f3ac31388b50aa89ff0fc49c00c987c16e7b5146491d12003f2c8ed'
        RequiredText = @(
            '--disable-jit'
            '--enable-pcre2-8'
            '--enable-pcre2-16'
            '--enable-pcre2-32'
            '--enable-unicode'
        )
    }
}

$contract = $recipes[$Package]
$source = (Resolve-Path -LiteralPath $SourceRecipe).ProviderPath
$output = [IO.Path]::GetFullPath($OutputRecipe)
if (Test-Path -LiteralPath $output) {
    throw 'Prepared recipe output must be new.'
}
$sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sourceHash -cne $contract.RecipeSHA256) {
    throw "Unexpected pinned $Package recipe hash: $sourceHash"
}

$before = [IO.File]::ReadAllText($source).Replace("`r`n", "`n")
if ([regex]::Matches($before, "(?m)^arch=\('i686' 'x86_64'\)$").Count -ne 1) {
    throw 'Expected exactly one unchanged upstream MSYS architecture declaration.'
}
foreach ($required in $contract.RequiredText) {
    if (-not $before.Contains($required, [StringComparison]::Ordinal)) {
        throw "Pinned recipe lost required feature/dependency text: $required"
    }
}
$after = $before.Replace("arch=('i686' 'x86_64')", "arch=('aarch64')")
if ($after -ceq $before) {
    throw 'Native architecture preparation made no change.'
}

$parent = Split-Path -Parent $output
if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}
[IO.File]::WriteAllText($output, $after, [Text.UTF8Encoding]::new($false))

$comparison = $after.Replace("arch=('aarch64')", "arch=('i686' 'x86_64')")
if ($comparison -cne $before) {
    throw 'Prepared recipe changed more than the declared architecture namespace.'
}
$preparedHash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
$receipt = [ordered]@{
    schema = 1
    status = 'native-msys-recipe-prepared-not-built'
    package = $Package
    repository = 'msys2/MSYS2-packages'
    commit = $contract.Commit
    blob = $contract.Blob
    source_recipe = $source
    source_recipe_sha256 = $sourceHash
    prepared_recipe = $output
    prepared_recipe_sha256 = $preparedHash
    source_archive_sha256 = $contract.SourceSHA256
    architecture_change = "arch=('i686' 'x86_64') -> arch=('aarch64')"
    preserved = 'All source pins, dependencies, package splits, configure features, checks, licenses, and install functions'
}
$receiptPath = "$output.preparation.json"
[IO.File]::WriteAllText(
    $receiptPath,
    ($receipt | ConvertTo-Json -Depth 4) + "`n",
    [Text.UTF8Encoding]::new($false)
)
$receipt
