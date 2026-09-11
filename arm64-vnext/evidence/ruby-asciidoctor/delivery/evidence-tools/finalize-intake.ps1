param([Parameter(Mandatory)][string] $Workspace)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = 'C:\ar07-9047'
$delivery = "$root\delivery"
$installed = "$root\doc-install-02"
$job = Get-Content -Raw "$root\evidence\git-doc-install-02\job.json" | ConvertFrom-Json
if (-not $job.passed -or $job.timed_out -or -not $job.observation_count_matches -or $job.parent_raw_exit -ne 0) {
    throw 'The complete documentation install must pass before sealing'
}
$stage = Get-Content -Raw "$delivery\staged-intake.json" | ConvertFrom-Json
$fullJob = Get-Content -Raw "$root\evidence\full-git-docs-01\job.json" | ConvertFrom-Json
$staticPe = Get-Content -Raw "$PSScriptRoot\archive-audit-01\static-readback.json" | ConvertFrom-Json
$targets = @(Get-Content -Raw "$delivery\git-generated-targets.json" | ConvertFrom-Json)
foreach ($target in $targets) {
    $extension = [IO.Path]::GetExtension($target.Target)
    if ($extension -eq '.html') {
        $relative = if ($target.Target.StartsWith('Documentation\')) {
            $target.Target.Substring('Documentation\'.Length)
        } else { 'git-subtree.html' }
        $path = Join-Path "$installed\mingwarm64\share\doc\git-doc" $relative
    } else {
        $path = Join-Path "$installed\mingwarm64\share\man\man$($extension.Substring(1))" (Split-Path -Leaf $target.Target)
    }
    if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -ne $target.SHA256) {
        throw "Git's installed target differs from its generated output: $($target.Target)"
    }
}
$installedFiles = @(
    Get-ChildItem -LiteralPath "$installed\mingwarm64" -Recurse -File -Force | ForEach-Object {
        [pscustomobject]@{
            Path=$_.FullName.Substring($installed.Length+1)
            Bytes=$_.Length
            SHA256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        }
    }
)
$installedFiles | ConvertTo-Json -Depth 5 | Set-Content "$delivery\git-installed-payload-inventory.json" -Encoding utf8

function Copy-Evidence([string] $Source, [string] $Destination) {
    $hash = (Get-FileHash -LiteralPath $Source).Hash.ToLowerInvariant()
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination
    if ((Get-FileHash -LiteralPath $Destination).Hash.ToLowerInvariant() -ne $hash) {
        throw "Evidence changed during seal: $Source"
    }
}
$proofs = @(
    'bootstrap-source.json','bootstrap-source.inventory.json','bootstrap-clone.json','bootstrap-empty-directories.json',
    'install-original-ruby-chain-02.json','install-original-ruby-chain-02.stdout.log','install-original-ruby-chain-02.stderr.log',
    'native-ruby-version.json','native-ruby-version.stdout.log','runtime-smoke\result.json','runtime-smoke\ready.json',
    'runtime-smoke\stdout.log','runtime-smoke\stderr.log','asciidoctor-shell\job.json','asciidoctor-shell\job.log',
    'asciidoctor-cmd\job.json','asciidoctor-cmd\job.log','exact-git-docs-01\job.json','exact-git-docs-01\job.log',
    'full-git-docs-01\job.json','full-git-docs-01\job.log','exact-git-docs-01.json','full-git-docs-01.json',
    'git-doc-target-manifest.stdout.log','git-doc-install-02\job.json','git-doc-install-02\job.log','git-doc-install-02.json',
    'docs-driver-exact-dependencies.json','admitted-doc-exact-dependencies.json','upstream-docs-admission.json'
)
foreach ($proof in $proofs) { Copy-Evidence (Join-Path "$root\evidence" $proof) (Join-Path "$delivery\evidence" $proof) }
foreach ($file in Get-ChildItem "$root\evidence\runtime-smoke\native-exits","$root\evidence\native-exits" -File) {
    Copy-Evidence $file.FullName "$delivery\evidence\native-exits\$($file.Name)"
}
$signatureFiles = @(Get-ChildItem "$root\evidence" -File |
    Where-Object { $_.Name -match '^(signature-.*-02|docs-signature-).*\.(stdout\.log|stderr\.log|json)$' })
if ($signatureFiles.Count -ne 39) { throw 'Expected all 13 trusted signature transcripts and process receipts' }
foreach ($file in $signatureFiles) {
    Copy-Evidence $file.FullName "$delivery\evidence\signatures\$($file.Name)"
}
foreach ($file in 'result.json','build.log','native-job.json','native-job.log') {
    Copy-Evidence "$root\a03\$file" "$delivery\evidence\asciidoctor-build\$file"
}
foreach ($file in 'Invoke-LeafProcess.ps1','ruby-runtime-smoke.rb','run-runtime-smoke.ps1','stage-intake.ps1','finalize-intake.ps1') {
    Copy-Evidence "$PSScriptRoot\$file" "$delivery\evidence-tools\$file"
}
Copy-Evidence "$Workspace\.gitattributes" "$delivery\source\.gitattributes"
Copy-Evidence "$Workspace\README.md" "$delivery\source\README.md"
Copy-Evidence "$root\source-licenses\sources.json" "$delivery\supplemental-licenses\sources.json"
Copy-Evidence "$PSScriptRoot\archive-audit-01\static-readback.json" "$delivery\evidence\native-runtime-static-pe.json"
$exitHandoff = 'C:\ap06-2160\parallel-v1\native-exit-handoff.json'
if ((Get-FileHash $exitHandoff).Hash.ToLowerInvariant() -ne '096ec4b08cb96559d5571d693017d081e2f0b234fa4dea94369fe40cd964acbf') {
    throw 'Released native observer contract changed'
}
Copy-Evidence $exitHandoff "$delivery\native-exit-handoff.json"
foreach ($name in 'gmp-6.3.0.tar.xz','libyaml-0.2.5.tar.gz') {
    Copy-Evidence "$root\sources\$name" "$delivery\sources\$name"
}

$driverInputs = @(
    Get-ChildItem -LiteralPath "$root\doc-sources" -File -Filter '*.pkg.tar.zst' | ForEach-Object {
        $signature = if (Test-Path -LiteralPath ($_.FullName+'.sig')) {
            (Get-FileHash -LiteralPath ($_.FullName+'.sig')).Hash.ToLowerInvariant()
        } else { $null }
        [pscustomobject]@{
            Path=$_.FullName;SHA256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()
            SignatureSHA256=$signature
            Trust=if ($signature) { 'Original MSYS2 signature verified with trusted private keyring' }
                  else { 'Local archive explicitly admitted by pipeline receipt 6c452897; not claimed signed' }
            Role='MSYS x64/emulated documentation driver or data, not native distribution payload'
        }
    }
)
$driverInputs | ConvertTo-Json -Depth 5 | Set-Content "$delivery\documentation-driver-inputs.json" -Encoding utf8
$files = @(
    Get-ChildItem -LiteralPath $delivery -Recurse -File -Force | ForEach-Object {
        [pscustomobject]@{
            Path=$_.FullName.Substring($delivery.Length+1)
            Bytes=$_.Length
            SHA256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        }
    }
)
$files | ConvertTo-Json -Depth 5 | Set-Content "$delivery\files.json" -Encoding utf8
$receipt = [ordered]@{
    SchemaVersion=1
    Status='ready-for-pipeline-provider-admission'
    SealedAt=[DateTime]::UtcNow.ToString('o')
    LeafSession='9047acfa-ea57-4a5a-8679-8a1454660e2f'
    CliSession='ab17e048-82a5-4e0d-b480-2ad21a418f8b'
    ProviderOwner='2160ef10-d0c2-4ea7-97a0-d837f02d92b7'
    Coordinator='0724b323-3a13-4c17-95ed-57b16cbad570'
    Root=$delivery
    FileManifest=@{Path="$delivery\files.json";SHA256=(Get-FileHash "$delivery\files.json").Hash.ToLowerInvariant();Files=$files.Count}
    Asciidoctor=@{
        Name='mingw-w64-aarch64-asciidoctor';Version='2.0.26-3';Archive=$stage.AsciidoctorArchive
        PayloadFiles=$stage.AsciidoctorPayloadFiles;NativeExtensions=0
        ExactDependency='mingw-w64-clang-aarch64-ruby=4.0.6-1'
        LocalPackageSignature=$null
        Source='Asciidoctor 2.0.26 gem pinned by accepted upstream SHA256 and checked by RubyGems; upstream recipe has no detached gem PGP signature'
        InstallOptions='Offline/local gem install, no user install; RI/RDoc self-documentation not generated. Real Git XHTML/DocBook/man functionality retained.'
    }
    NativeRuby=@{
        Version='4.0.6-1';Description='Official signed native aarch64-mingw-ucrt Ruby +PRISM bootstrap'
        Compiler='Original upstream Clang 22.1.8-2, not GCC'
        Packages=$stage.RuntimePackages;PayloadFiles=$stage.RuntimePayloadFiles
        OrdinaryArm64PEImages=[int]($staticPe.Packages | Measure-Object ImageCount -Sum).Sum
        Readback='Every runtime payload file matches original archive extraction, private pacman install, and clean extracted execution root'
        LiveModules=$stage.NativeRuntimeModules
        NativeAPIs=@('OpenSSL','zlib','Psych/libyaml','Fiddle/libffi','strscan','JSON','digest','large integer arithmetic')
        Namespace='Original CLANGARM64 names, versions, payloads, and prefix preserved; no synthetic MINGWARM64 Ruby provides'
    }
    GitDocumentation=@{
        RecipeCommit='d65b87de173ac2209a63cef8c4528669b5571fd3'
        SourceCommit='32c4f7689275d233577576630e1ac5b7eb354eb0'
        Version='2.55.0.windows.5';Date='2026-08-20'
        Targets='Unmodified Documentation html/man and contrib/subtree html/man; Git recipe git-bash.adoc included'
        Html=$stage.HtmlTargets;Man=$stage.ManTargets;Total=$stage.GeneratedTargets
        TargetManifest='git-generated-targets.json'
        NativeRubyConversions=$stage.NativeDocumentationProcesses;AllNativeRubyRawExits=0
        FullJobGenerations=@{Created=$fullJob.created_processes;Observed=$fullJob.observed_processes}
        Features=@('XHTML5','DocBook5','man sections 1/5/7','book/user manual','Git synopsis converters','linkgit macro','shared docinfo','Git version/date','subtree manuals')
        InstalledRoot=$installed;InstalledFiles=$installedFiles.Count
        InstalledReadback='All 483 required generated targets match their real Git install-html/install-man output byte-for-byte; complete installed asset inventory retained'
        XmlDrivers='Pipeline-admitted xmlto/DocBook plus signature-verified dependencies; explicitly x64/emulated MSYS host tools'
    }
    Engine=@{
        ContractSHA256='d170effd2f79217135cec79f550310f7068acf80998736eab77a3cff32f5a50e'
        EngineSHA256='9e87d9c2b7235363ef14f407945078a1488bdca3bc8b3ef15fa26bbc0559f985'
        Epoch=$stage.CompilerEpoch
        Scope='Header-only h1 MinGW/LLP64 profile unchanged before/after package build; no later FP/MSYS changes inferred'
        PackageChecks='makepkg --check, source verification, complete job-generation observation; independent native interpreter/module/docs controls'
        WorkerLimit=2;Compression='Private makepkg configs: zstd single-thread, xz -T1'
    }
    Licensing='Original package licenses and upstream recipes retained. Original GMP and libyaml source licenses supplied separately where upstream binary archives omit standalone license files; original signed packages unchanged.'
    RejectedAttempts=@(
        @{Path="$root\a01";Reason='Missing empty bootstrap /tmp; no package admitted'},
        @{Path="$root\a02";Reason='CRLF PKGBUILD; no package admitted'},
        @{Path="$root\doc-install";Reason='First install exceeded 300s bound; partial output excluded, fresh 1800s install passed'}
    )
    SharedPrefixesModified=$false
    FullGitDistributionComplete=$false
    AllMsysToolsNative=$false
    CommitsPushesOrCiActions=$false
    Admission='Only pipeline may install into its integration prefix, after its live readers drain. Recheck the file manifest and original package signatures; no nodeps or fake provides.'
    Resources='No allocation transfer is performed by this receipt. Return of two slots is requested separately after observed leaf process drain.'
}
$receipt | ConvertTo-Json -Depth 14 | Set-Content "$delivery\receipt.json" -Encoding utf8
foreach ($file in Get-ChildItem -LiteralPath $delivery -Recurse -File -Force) { $file.IsReadOnly=$true }
[pscustomobject]@{Path="$delivery\receipt.json";SHA256=(Get-FileHash "$delivery\receipt.json").Hash.ToLowerInvariant();Files=$files.Count;InstalledFiles=$installedFiles.Count}
