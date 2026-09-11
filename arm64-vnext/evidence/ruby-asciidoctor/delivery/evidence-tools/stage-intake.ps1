param([Parameter(Mandatory)][string] $Workspace)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = 'C:\ar07-9047'
$delivery = "$root\delivery"
$artifacts = $PSScriptRoot
$recipe = Join-Path $Workspace 'packages\mingw-w64-asciidoctor'
$lock = Get-Content -Raw "$recipe\ruby-bootstrap.lock.json" | ConvertFrom-Json
$build = Get-Content -Raw "$root\a03\result.json" | ConvertFrom-Json
$epoch = '5382e3f64bfd1314f168e2df67ce1abd79f3574acf32538708e7a2c8432fb3b7'
if ($build.Status -ne 'passed' -or $build.Before.Epoch -ne $epoch -or $build.After.Epoch -ne $epoch) {
    throw 'Asciidoctor package qualification is not the released h1 profile'
}
if (Test-Path -LiteralPath $delivery) { throw 'Delivery directory must be new' }
New-Item -ItemType Directory -Path $delivery | Out-Null

function Get-Binding([string] $Path) {
    [pscustomobject]@{Path=$Path;SHA256=(Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant()}
}
function Copy-Bound([string] $Source, [string] $Destination, [string] $Expected = '') {
    $hash = (Get-FileHash -LiteralPath $Source).Hash.ToLowerInvariant()
    if ($Expected -and $hash -ne $Expected) { throw "Input changed: $Source" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
    if ((Get-FileHash -LiteralPath $Destination).Hash.ToLowerInvariant() -ne $hash) {
        throw "Delivery copy changed: $Destination"
    }
    [pscustomobject]@{Path=$Destination;SHA256=$hash}
}
function Save-Json($Value, [string] $Path) {
    $Value | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $Path -Encoding utf8
}

$runtimeFiles = [Collections.Generic.List[object]]::new()
$runtimePackages = foreach ($package in $lock.packages) {
    $archive = Copy-Bound "$root\sources\$($package.archive)" "$delivery\packages\$($package.archive)" $package.sha256
    $signature = Copy-Bound "$root\sources\$($package.archive).sig" "$delivery\packages\$($package.archive).sig" $package.signatureSha256
    $original = "$artifacts\archive-audit-01\$($package.name)"
    foreach ($metadata in Get-ChildItem -LiteralPath $original -File -Force) {
        $null = Copy-Bound $metadata.FullName "$delivery\metadata\$($package.name)\$($metadata.Name)"
    }
    $packageFiles = @(
        foreach ($file in Get-ChildItem -LiteralPath "$original\clangarm64" -Recurse -File -Force) {
            $relative = $file.FullName.Substring($original.Length + 1)
            $hash = (Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()
            foreach ($copyRoot in "$root\b", "$root\asciidoctor-readback") {
                $path = Join-Path $copyRoot $relative
                if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $hash) {
                    throw "Original runtime payload differs in $copyRoot : $relative"
                }
            }
            $entry = [pscustomobject]@{Package=$package.name;Path=$relative;Bytes=$file.Length;SHA256=$hash}
            $runtimeFiles.Add($entry)
            $entry
        }
    )
    $short = $package.name.Replace('mingw-w64-clang-aarch64-', '')
    $sourceName = if ($short -in 'gmp','libyaml') { "$short-original.PKGBUILD" } else { "$short-c06bdfb1.PKGBUILD" }
    $upstreamRecipe = Copy-Bound "$artifacts\sources\$sourceName" "$delivery\upstream-recipes\$short\PKGBUILD" $package.recipeSha256
    [pscustomobject]@{
        Name=$package.name;Version=$package.version;Archive=$archive;Signature=$signature
        Recipe=$upstreamRecipe;RecipeCommit=$package.recipeCommit;Licenses=$package.licenses
        PayloadFiles=$packageFiles.Count;DeclaredDependencies=$package.declaredDependencies
        SignatureEvidence=Get-Binding "$root\evidence\signature-$($package.name)-02.stdout.log"
    }
}
Save-Json @($runtimeFiles) "$delivery\runtime-payload-inventory.json"

foreach ($inputFile in $build.SourceInputs) {
    $null = Copy-Bound (Join-Path $recipe $inputFile.Path) (Join-Path "$delivery\recipe" $inputFile.Path) $inputFile.SHA256
}
$packageArchive = Copy-Bound $build.Packages[0].Path `
    "$delivery\packages\$(Split-Path -Leaf $build.Packages[0].Path)" $build.Packages[0].SHA256
$stagedPackage = "$root\a03\build\mingw-w64-asciidoctor\pkg\mingw-w64-aarch64-asciidoctor"
$asciidoctorFiles = @(
    foreach ($file in Get-ChildItem -LiteralPath "$root\asciidoctor-readback\mingwarm64" -Recurse -File -Force) {
        $relative = $file.FullName.Substring("$root\asciidoctor-readback\".Length)
        if ($file.Extension -in '.exe','.dll','.so') { throw "Native extension in pure Ruby package: $relative" }
        $hash = (Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()
        if ((Get-FileHash -LiteralPath (Join-Path $stagedPackage $relative)).Hash.ToLowerInvariant() -ne $hash) {
            throw "Packaged Asciidoctor differs from build staging: $relative"
        }
        [pscustomobject]@{Path=$relative;Bytes=$file.Length;SHA256=$hash}
    }
)
foreach ($metadata in Get-ChildItem -LiteralPath "$root\asciidoctor-readback" -File -Force) {
    $null = Copy-Bound $metadata.FullName "$delivery\metadata\mingw-w64-aarch64-asciidoctor\$($metadata.Name)"
}
Save-Json $asciidoctorFiles "$delivery\asciidoctor-payload-inventory.json"

$engine = Get-Content -Raw 'C:\ap06-2160\parallel-v1\engine.json' | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $engine.Inventory).Hash.ToLowerInvariant() -ne $engine.InventorySHA256) {
    throw 'Released engine inventory changed'
}
foreach ($file in (Get-Content -Raw $engine.Inventory | ConvertFrom-Json)) {
    $null = Copy-Bound (Join-Path "$Workspace\.ruby-engine" $file.Path) (Join-Path "$delivery\engine" $file.Path) $file.SHA256
}
$null = Copy-Bound 'C:\ap06-2160\parallel-v1\engine.json' "$delivery\engine.json" `
    '9e87d9c2b7235363ef14f407945078a1488bdca3bc8b3ef15fa26bbc0559f985'
$null = Copy-Bound $engine.Inventory "$delivery\engine.inventory.json" $engine.InventorySHA256
$null = Copy-Bound 'C:\ap06-2160\parallel-v1\leaf-contract.json' "$delivery\leaf-contract.json" `
    'd170effd2f79217135cec79f550310f7068acf80998736eab77a3cff32f5a50e'

$git = "$root\g01\git-32c4f7689275d233577576630e1ac5b7eb354eb0"
$targets = @(Get-Content "$root\evidence\git-doc-target-manifest.stdout.log")
$targets = @($targets | ForEach-Object { "Documentation\$_" }) +
    @('contrib\subtree\git-subtree.html','contrib\subtree\git-subtree.1')
$documents = @(
    foreach ($target in $targets) {
        if ($target -notmatch '\.(html|[157])$' -or $target -match '(^|[\\/])\.\.([\\/]|$)') {
            throw "Unexpected Git target: $target"
        }
        $relative = $target.Replace('/', '\')
        $source = Join-Path $git $relative
        $contents = Get-Content -Raw -LiteralPath $source
        $extension = [IO.Path]::GetExtension($source)
        if ($extension -eq '.html') {
            if ($contents.IndexOf('<html', [StringComparison]::OrdinalIgnoreCase) -lt 0) { throw "Invalid HTML: $relative" }
        } elseif (-not $contents.Contains('.TH ')) { throw "Missing manpage header: $relative" }
        $file = Get-Item -LiteralPath $source
        if ($file.Length -eq 0) { throw "Empty generated target: $relative" }
        $copy = Copy-Bound $source (Join-Path "$delivery\generated-docs" $relative)
        [pscustomobject]@{Target=$relative;Bytes=$file.Length;SHA256=$copy.SHA256}
    }
)
Save-Json $documents "$delivery\git-generated-targets.json"
$html = Get-Content -Raw "$git\Documentation\git-commit.html"
$xml = Get-Content -Raw "$git\Documentation\git-commit.xml"
if (-not ($html.Contains('http://www.w3.org/1999/xhtml') -and
          $html -match '<code>git</code>\s+<code>commit</code>' -and
          $xml -match '<literal>git</literal>\s+<literal>commit</literal>' -and
          $html.Contains('href="git-add.html">git-add(1)</a>') -and
          $xml.Contains('Git 2.55.0.windows.5') -and $xml.Contains('<date>2026-08-20</date>'))) {
    throw 'Pinned Git extension semantics were not preserved'
}
$null = Copy-Bound "$git\Documentation\asciidoctor-extensions.rb" "$delivery\git-inputs\asciidoctor-extensions.rb"
$null = Copy-Bound "$git\Documentation\GIT-ASCIIDOCFLAGS" "$delivery\git-inputs\GIT-ASCIIDOCFLAGS"
$null = Copy-Bound "$root\sources\git-bash.adoc" "$delivery\git-inputs\git-bash.adoc" `
    'c975292adae1f2666f07f8ee9b7d50576da249d9151c6bd211602adc8d37b6ab'
foreach ($file in Get-ChildItem -LiteralPath "$root\source-licenses" -Recurse -File) {
    $relative = $file.FullName.Substring("$root\source-licenses\".Length)
    $null = Copy-Bound $file.FullName (Join-Path "$delivery\supplemental-licenses" $relative)
}
$null = Copy-Bound "$artifacts\sources\asciidoctor-2.0.26.gem" "$delivery\sources\asciidoctor-2.0.26.gem" $lock.asciidoctorGemSha256
$null = Copy-Bound "$root\sources\git-32c4f768.tar.gz" "$delivery\sources\git-32c4f768.tar.gz" `
    'a31334ece26af0c79b2f3666eca7eaf664c456004290c748fddd0df5ab870162'

$full = Get-Content -Raw "$root\evidence\full-git-docs-01\job.json" | ConvertFrom-Json
$focused = Get-Content -Raw "$root\evidence\exact-git-docs-01\job.json" | ConvertFrom-Json
foreach ($job in $full,$focused) {
    if (-not $job.passed -or -not $job.observation_count_matches -or
        @($job.native_target_exits | Where-Object raw_exit -ne 0).Count) { throw 'Incomplete native documentation exit evidence' }
}
$runtime = Get-Content -Raw "$root\evidence\runtime-smoke\result.json" | ConvertFrom-Json
$payloadByPath = @{}
foreach ($file in $runtimeFiles) { $payloadByPath[$file.Path] = $file.SHA256 }
foreach ($module in $runtime.Modules | Where-Object Origin -eq 'signed-ruby-bootstrap') {
    $relative = $module.Path.Substring("$root\b\".Length)
    if ($payloadByPath[$relative] -ne $module.SHA256) { throw "Live module not bound to signed package payload: $relative" }
}
Save-Json ([ordered]@{
    Status='payload-and-generated-document-readback-complete-awaiting-install-seal'
    RuntimePackages=$runtimePackages;AsciidoctorArchive=$packageArchive
    RuntimePayloadFiles=$runtimeFiles.Count;AsciidoctorPayloadFiles=$asciidoctorFiles.Count
    GeneratedTargets=$documents.Count
    HtmlTargets=@($documents | Where-Object Target -like '*.html').Count
    ManTargets=@($documents | Where-Object Target -match '\.[157]$').Count
    NativeDocumentationProcesses=$full.native_target_exits.Count+$focused.native_target_exits.Count
    NativeRuntimeModules=$runtime.Modules.Count;CompilerEpoch=$epoch
    PackageBuild=Get-Binding "$root\a03\result.json"
    RuntimeProof=Get-Binding "$root\evidence\runtime-smoke\result.json"
    FullDocumentationProof=Get-Binding "$root\evidence\full-git-docs-01\job.json"
    FocusedDocumentationProof=Get-Binding "$root\evidence\exact-git-docs-01\job.json"
    GitExtensionSemanticsVerified=$true
}) "$delivery\staged-intake.json"
Get-Content -Raw "$delivery\staged-intake.json"
