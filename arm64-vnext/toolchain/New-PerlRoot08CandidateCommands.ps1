[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $CandidateRoot,
    [string] $PreparedSource = 'C:\ap06-78\perl-recovery-20260911-08\perl-root08-source-prep-01\source-deref',
    [string] $PreparedSourceReceipt = 'C:\ap06-78\perl-recovery-20260911-08\perl-root08-source-prep-01\root08-source-prep-01.json',
    [string] $ToolchainPrefix = 'C:\ap06-78\perl-recovery-20260910-06\toolchain',
    [string] $V12SdkExport = 'C:\ap11-native-provider-intake\cygwin-w32api-arm64-v12-admitted-v1\export.json',
    [string] $V12SdkCohort,
    [string] $DbPrefix,
    [string] $GdbmPrefix,
    [string] $LibxcryptPrefix,
    [string] $RuntimeDepsPrefix,
    [int] $Jobs = 2,
    [int] $TestJobs = $Jobs,
    [switch] $RequireReady
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$expectedSourceReceipt = 'afca365af10f7b8fe9a966b76d658fc8514320fdb64d3d8919663cd48cb99ec9'
$expectedV12SdkExport = 'e8f15ea9837a75be2fb133f9dbd6b7ce31f0d628ca29ce06c933e5fb2f8017f7'

function Get-Sha256([string] $Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-FileHash([string] $Path, [string] $Expected) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing required file: $Path"
    }
    $actual = Get-Sha256 $Path
    if ($actual -cne $Expected) {
        throw "Hash mismatch for $Path. Expected $Expected, got $actual."
    }
    $actual
}

function ConvertTo-MsysPath([string] $Path) {
    if (-not $Path) { return $null }
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $tail = $Matches[2].Replace('\', '/')
        return "/cygdrive/$drive/$tail"
    }
    throw "Cannot convert non-drive path to MSYS syntax: $Path"
}

function Resolve-CandidatePrefix([string] $Prefix, [string] $Name) {
    if ($Prefix) {
        if (-not (Test-Path -LiteralPath $Prefix -PathType Container)) {
            throw "$Name prefix does not exist: $Prefix"
        }
        return [ordered]@{
            name = $Name
            status = 'provided'
            windowsPath = [IO.Path]::GetFullPath($Prefix)
            msysPath = ConvertTo-MsysPath $Prefix
        }
    }
    if ($RequireReady) { throw "$Name prefix is required for a ready root08 candidate." }
    $placeholderName = $Name.ToUpperInvariant()
    [ordered]@{
        name = $Name
        status = 'pending'
        windowsPath = $null
        msysPath = "__PENDING_${placeholderName}_PREFIX__"
    }
}

function Find-UnderPrefix([string] $Prefix, [string[]] $Patterns) {
    if (-not $Prefix) { return @() }
    $hits = @()
    foreach ($pattern in $Patterns) {
        $hits += @(Get-ChildItem -LiteralPath $Prefix -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like (Join-Path $Prefix $pattern) } |
            Select-Object -First 8 FullName, Length)
    }
    $hits | Sort-Object FullName -Unique
}

function Assert-PrefixContent([hashtable] $Spec) {
    if (-not $Spec.Prefix) { return @() }
    $hits = Find-UnderPrefix $Spec.Prefix $Spec.Patterns
    if ($RequireReady -and $hits.Count -eq 0) {
        throw "No $($Spec.Name) files matched expected patterns under $($Spec.Prefix)."
    }
    @($hits | ForEach-Object {
        [ordered]@{
            path = $_.FullName
            length = $_.Length
            sha256 = Get-Sha256 $_.FullName
        }
    })
}

$sourceReceiptSha = Assert-FileHash $PreparedSourceReceipt $expectedSourceReceipt
if (-not (Test-Path -LiteralPath $PreparedSource -PathType Container)) {
    throw "Missing prepared source: $PreparedSource"
}
$v12SdkExportSha = Assert-FileHash $V12SdkExport $expectedV12SdkExport
if (-not $V12SdkCohort) {
    $V12SdkCohort = Join-Path (Split-Path -Parent $V12SdkExport) 'upstream\cohort'
}
if (-not (Test-Path -LiteralPath $V12SdkCohort -PathType Container)) {
    throw "Missing v12 SDK cohort directory: $V12SdkCohort"
}
if (-not (Test-Path -LiteralPath $ToolchainPrefix -PathType Container)) {
    throw "Missing native MSYS toolchain prefix: $ToolchainPrefix"
}
if ($Jobs -lt 1 -or $Jobs -gt 2) {
    throw 'This recovery lane may use at most two compiler jobs.'
}
if ($TestJobs -lt 1 -or $TestJobs -gt 2) {
    throw 'This recovery lane may use at most two test harness jobs.'
}
$candidateFull = [IO.Path]::GetFullPath($CandidateRoot)
if (Test-Path -LiteralPath $candidateFull) {
    if (@(Get-ChildItem -LiteralPath $candidateFull -Force).Count -ne 0) {
        throw "Use a new empty candidate command directory: $candidateFull"
    }
} else {
    [void][IO.Directory]::CreateDirectory($candidateFull)
}
$candidateSource = Join-Path $candidateFull 'source-deref'
if (Test-Path -LiteralPath $candidateSource) {
    throw "Candidate source already exists: $candidateSource"
}
Copy-Item -LiteralPath $PreparedSource -Destination $candidateSource -Recurse

$candidateSourceCorrections = @()
$dbBtreeTestPath = Join-Path $candidateSource 'cpan\DB_File\t\db-btree.t'
$dbBtreeText = Get-Content -LiteralPath $dbBtreeTestPath -Raw
if ($dbBtreeText -match "(?m)^:cn`r?`n") {
    $oldHash = Get-Sha256 $dbBtreeTestPath
    $dbBtreeText = [regex]::Replace($dbBtreeText, "(?m)^:cn`r?`n", '', 1)
    Set-Content -LiteralPath $dbBtreeTestPath -Value $dbBtreeText -NoNewline -Encoding UTF8
    $candidateSourceCorrections += [ordered]@{
        path = 'cpan\DB_File\t\db-btree.t'
        reason = 'Remove inherited stray :cn line that made the DB_File btree test syntactically invalid in the fresh candidate copy.'
        oldSha256 = $oldHash
        newSha256 = Get-Sha256 $dbBtreeTestPath
    }
}

$customizedDataPath = Join-Path $candidateSource 't\porting\customized.dat'
if (Test-Path -LiteralPath $customizedDataPath -PathType Leaf) {
    $customizedUpdates = @(
        [ordered]@{ module = 'Pod::Perldoc'; file = 'cpan/Pod-Perldoc/lib/Pod/Perldoc.pm' },
        [ordered]@{ module = 'Win32API::File'; file = 'cpan/Win32API-File/File.pm' }
    )
    $customizedText = Get-Content -LiteralPath $customizedDataPath -Raw
    $customizedChanged = $false
    $customizedChanges = @()
    foreach ($entry in $customizedUpdates) {
        $sourceFile = Join-Path $candidateSource ($entry.file -replace '/', '\')
        if (-not (Test-Path -LiteralPath $sourceFile -PathType Leaf)) {
            throw "Missing customized source file: $sourceFile"
        }
        $newSha1 = (Get-FileHash -Algorithm SHA1 -LiteralPath $sourceFile).Hash.ToLowerInvariant()
        $pattern = "(?m)^$([regex]::Escape($entry.module))\s+$([regex]::Escape($entry.file))\s+([0-9a-f]{40})$"
        $match = [regex]::Match($customizedText, $pattern)
        if (-not $match.Success) {
            throw "Unable to find customized.dat entry for $($entry.file)"
        }
        $oldSha1 = $match.Groups[1].Value
        if ($oldSha1 -cne $newSha1) {
            $customizedText = [regex]::Replace($customizedText, $pattern, "$($entry.module) $($entry.file) $newSha1", 1)
            $customizedChanged = $true
            $customizedChanges += [ordered]@{
                module = $entry.module
                file = $entry.file
                oldSha1 = $oldSha1
                newSha1 = $newSha1
            }
        }
    }
    if ($customizedChanged) {
        $oldHash = Get-Sha256 $customizedDataPath
        Set-Content -LiteralPath $customizedDataPath -Value $customizedText -NoNewline -Encoding UTF8
        $candidateSourceCorrections += [ordered]@{
            path = 't\porting\customized.dat'
            reason = 'Refresh candidate-local customized hashes for source-prep deltas so porting/customized.t verifies the actual candidate sources.'
            oldSha256 = $oldHash
            newSha256 = Get-Sha256 $customizedDataPath
            entries = $customizedChanges
        }
    }
}

$cygwinTestPath = Join-Path $candidateSource 't\lib\cygwin.t'
$cygwinTestText = Get-Content -LiteralPath $cygwinTestPath -Raw
$cygwinMountPattern = '(?s)my \$mount = join '''', `/usr/bin/mount`;\r?\n\$mount =~ m\|on \(\?:/usr\)\?/bin type \.\+ \\\(\(\\w\+\)\[,\\\)\]\|m;\r?\nmy \$binmode = \$1 =~ /binmode\|binary/;'
$cygwinMountReplacement = "my `$mount = join '', ``mount``;`n`$mount =~ m|on / type .+ \(([^)]*)\)|m;`nmy `$binmode = defined `$1 && `$1 =~ /(?:^|,)(?:binmode|binary)(?:,|`$)/;"
if ([regex]::IsMatch($cygwinTestText, $cygwinMountPattern)) {
    $oldHash = Get-Sha256 $cygwinTestPath
    $cygwinTestText = [regex]::Replace($cygwinTestText, $cygwinMountPattern, $cygwinMountReplacement, 1)
    Set-Content -LiteralPath $cygwinTestPath -Value $cygwinTestText -NoNewline -Encoding UTF8
    $candidateSourceCorrections += [ordered]@{
        path = 't\lib\cygwin.t'
        reason = 'Use PATH-resolved mount from the private runtime utility prefix and parse the root mount flag list instead of assuming the first /usr/bin flag is binmode/binary.'
        oldSha256 = $oldHash
        newSha256 = Get-Sha256 $cygwinTestPath
    }
} else {
    throw 'Unable to patch t/lib/cygwin.t mount command/parser.'
}

$db = Resolve-CandidatePrefix $DbPrefix 'db'
$gdbm = Resolve-CandidatePrefix $GdbmPrefix 'gdbm'
$crypt = Resolve-CandidatePrefix $LibxcryptPrefix 'libxcrypt'
$runtimeDeps = Resolve-CandidatePrefix $RuntimeDepsPrefix 'runtimeDeps'
$sourceMsys = ConvertTo-MsysPath $candidateSource
$toolchainMsys = ConvertTo-MsysPath $ToolchainPrefix
$sdkMsys = ConvertTo-MsysPath $V12SdkCohort
$dependencyBinMsys = @(
    "$($runtimeDeps.msysPath)/usr/bin",
    "$($runtimeDeps.msysPath)/bin",
    "$($db.msysPath)/usr/bin",
    "$($db.msysPath)/bin",
    "$($gdbm.msysPath)/usr/bin",
    "$($gdbm.msysPath)/bin",
    "$($crypt.msysPath)/usr/bin",
    "$($crypt.msysPath)/bin"
) -join ':'

$configurePath = Join-Path $candidateSource 'Configure'
$configureText = Get-Content -LiteralPath $configurePath -Raw
$pathHookNeedle = "PATH=.`$p_`$PATH`nexport PATH"
$pathHookReplacement = @'
PATH=.$p_$PATH
case "${ROOT08_DLL_PATH:-}" in
'') ;;
*) PATH=$PATH$p_$ROOT08_DLL_PATH ;;
esac
export PATH
'@.Replace("`r`n", "`n")
if ($configureText -notlike "*$pathHookNeedle*") {
    throw 'Unable to patch Configure PATH hook for ROOT08_DLL_PATH preservation.'
}
$configureText = $configureText.Replace($pathHookNeedle, $pathHookReplacement)
$dbRunPattern = '(?s)(echo "Checking Berkeley DB version \.\.\." >&4.*?EOCP\n)\tset try\n\tif eval \$compile_ok && \$run \./try; then'
$dbRunReplacement = @'
${1}	set try
	case "${ROOT08_DLL_PATH:-}" in
	'') ;;
	*) PATH=$PATH$p_$ROOT08_DLL_PATH; export PATH ;;
	esac
	if eval $compile_ok && $run ./try; then
'@.Replace("`r`n", "`n")
if (-not [regex]::IsMatch($configureText, $dbRunPattern)) {
    throw 'Unable to patch Configure Berkeley DB runtime PATH hook.'
}
$configureText = [regex]::Replace($configureText, $dbRunPattern, $dbRunReplacement, 1)
Set-Content -LiteralPath $configurePath -Value $configureText -NoNewline -Encoding UTF8

$inputFiles = [ordered]@{
    db = Assert-PrefixContent @{ Name = 'db'; Prefix = $DbPrefix; Patterns = @('usr\include\db.h', 'include\db.h', 'usr\lib\libdb*.dll.a', 'lib\libdb*.dll.a', 'usr\bin\msys-db*.dll', 'bin\msys-db*.dll', '*\usr\include\db.h', '*\include\db.h', '*\usr\lib\libdb*.dll.a', '*\lib\libdb*.dll.a', '*\usr\bin\msys-db*.dll', '*\bin\msys-db*.dll') }
    gdbm = Assert-PrefixContent @{ Name = 'gdbm'; Prefix = $GdbmPrefix; Patterns = @('usr\include\gdbm*.h', 'include\gdbm*.h', 'usr\include\gdbm\*.h', 'include\gdbm\*.h', 'usr\lib\libgdbm*.dll.a', 'lib\libgdbm*.dll.a', 'usr\bin\msys-gdbm*.dll', 'bin\msys-gdbm*.dll', 'usr\bin\cyggdbm*.dll', 'bin\cyggdbm*.dll', '*\usr\include\gdbm*.h', '*\include\gdbm*.h', '*\usr\include\gdbm\*.h', '*\include\gdbm\*.h', '*\usr\lib\libgdbm*.dll.a', '*\lib\libgdbm*.dll.a', '*\usr\bin\msys-gdbm*.dll', '*\bin\msys-gdbm*.dll', '*\usr\bin\cyggdbm*.dll', '*\bin\cyggdbm*.dll') }
    libxcrypt = Assert-PrefixContent @{ Name = 'libxcrypt'; Prefix = $LibxcryptPrefix; Patterns = @('usr\include\crypt.h', 'include\crypt.h', 'usr\lib\libcrypt*.dll.a', 'lib\libcrypt*.dll.a', 'usr\bin\msys-crypt-2.dll', 'bin\msys-crypt-2.dll', '*\usr\include\crypt.h', '*\include\crypt.h', '*\usr\lib\libcrypt*.dll.a', '*\lib\libcrypt*.dll.a', '*\usr\bin\msys-crypt-2.dll', '*\bin\msys-crypt-2.dll') }
    runtimeDeps = Assert-PrefixContent @{ Name = 'runtimeDeps'; Prefix = $RuntimeDepsPrefix; Patterns = @('usr\bin\msys-intl-8.dll', 'bin\msys-intl-8.dll', 'usr\bin\msys-iconv-2.dll', 'bin\msys-iconv-2.dll', '*\usr\bin\msys-intl-8.dll', '*\bin\msys-intl-8.dll', '*\usr\bin\msys-iconv-2.dll', '*\bin\msys-iconv-2.dll') }
}

$requiredModules = @(
    'Config', 'Cwd', 'Data::Dumper', 'Digest::SHA', 'Encode', 'Fcntl',
    'File::Basename', 'File::Copy', 'File::Find', 'File::Path',
    'File::Spec', 'File::Temp', 'Getopt::Long', 'IO::Handle',
    'IO::Select', 'IO::Socket', 'IPC::Open2', 'IPC::Open3',
    'List::Util', 'MIME::Base64', 'POSIX', 'Scalar::Util', 'Socket',
    'Storable', 'Time::HiRes', 'Win32', 'Win32API::File',
    'DB_File', 'GDBM_File'
)
$gitPackageModules = @(
    'Error', 'LWP::UserAgent', 'Term::ReadKey',
    'Authen::SASL', 'MIME::Parser', 'Net::SMTP::SSL', 'DBI',
    'HTML::Parser', 'Locale::gettext', 'Net::SSLeay',
    'XML::Parser', 'YAML::Syck', 'IO::Socket::SSL'
)

$configure = @"
#!/usr/bin/env bash
set -euo pipefail

cd '$sourceMsys'
export PATH='/usr/bin:${toolchainMsys}/bin:${dependencyBinMsys}:'"`$PATH"
export LD_LIBRARY_PATH="${dependencyBinMsys}:`${LD_LIBRARY_PATH:-}"
export ROOT08_DLL_PATH='${dependencyBinMsys}'
export MSYS='winsymlinks:native'
export CHOST=aarch64-pc-cygwin
CC_TOOL='${toolchainMsys}/bin/gcc'
export CC="`$CC_TOOL"
export LD="`$CC_TOOL"

SDK_COHORT='$sdkMsys'
DB_PREFIX='$($db.msysPath)'
GDBM_PREFIX='$($gdbm.msysPath)'
LIBXCRYPT_PREFIX='$($crypt.msysPath)'

LOCINCPTH="`$DB_PREFIX/usr/include `$DB_PREFIX/include `$GDBM_PREFIX/usr/include `$GDBM_PREFIX/usr/include/gdbm `$GDBM_PREFIX/include `$GDBM_PREFIX/include/gdbm `$LIBXCRYPT_PREFIX/usr/include `$LIBXCRYPT_PREFIX/include"
LOCLIBPTH="`$DB_PREFIX/usr/lib `$DB_PREFIX/lib `$GDBM_PREFIX/usr/lib `$GDBM_PREFIX/lib `$LIBXCRYPT_PREFIX/usr/lib `$LIBXCRYPT_PREFIX/lib"

cat > root08-dependency-probe.c <<'EOF'
#include <db.h>
#include <gdbm.h>
#include <crypt.h>
#include <stdio.h>
int main(void) {
    int major = 0, minor = 0, patch = 0;
    (void)db_version(&major, &minor, &patch);
    if (major != DB_VERSION_MAJOR || minor != DB_VERSION_MINOR || patch != DB_VERSION_PATCH) {
        return 10;
    }
    GDBM_FILE dbf = gdbm_open("root08-dependency-probe.gdbm", 0, GDBM_WRCREAT, 0600, 0);
    if (!dbf) {
        return 11;
    }
    if (gdbm_close(dbf) != 0) {
        return 12;
    }
    printf("db=%d.%d.%d gdbm-open-close crypt-link-ok\n", major, minor, patch);
    return 0;
}
EOF
"`$CC_TOOL" -o root08-dependency-probe root08-dependency-probe.c \
  -I"`$DB_PREFIX/usr/include" -I"`$GDBM_PREFIX/usr/include" -I"`$LIBXCRYPT_PREFIX/usr/include" \
  -L"`$DB_PREFIX/usr/lib" -L"`$GDBM_PREFIX/usr/lib" -L"`$LIBXCRYPT_PREFIX/usr/lib" \
  -ldb -lgdbm -lcrypt
./root08-dependency-probe

./Configure -des \
  -Dusethreads \
  -Ud_thread_local \
  -Dosname=msys \
  -Doptimize='-O2 -g' \
  -Dprefix=/usr \
  -Dvendorprefix=/usr \
  -Dprivlib=/usr/share/perl5/core_perl \
  -Darchlib=/usr/lib/perl5/core_perl \
  -Dsitelib=/usr/share/perl5/site_perl \
  -Dsitearch=/usr/lib/perl5/site_perl \
  -Dvendorlib=/usr/share/perl5/vendor_perl \
  -Dvendorarch=/usr/lib/perl5/vendor_perl \
  -Dscriptdir=/usr/bin/core_perl \
  -Dsitescript=/usr/bin/site_perl \
  -Dvendorscript=/usr/bin/vendor_perl \
  -Dinc_version_list=none \
  -Dman1ext=1perl \
  -Dman3ext=3perl \
  -Darchname=aarch64-msys-threads \
  -Dmyarchname=aarch64-msys \
  -Dlibperl=msys-perl5_38.dll \
  -Dcc="`$CC_TOOL" \
  -Dld="`$CC_TOOL" \
  -Dlocincpth="`$LOCINCPTH" \
  -Dloclibpth="`$LOCLIBPTH" \
  -Accflags="-O2 -g -fwrapv -isysroot `$SDK_COHORT" \
  -Aldflags="-isysroot `$SDK_COHORT"
"@

$verify = @"
#!/usr/bin/env bash
set -euo pipefail
cd '$sourceMsys'
grep "^useithreads='define'" config.sh
grep "^usethreads='define'" config.sh
grep "^usemultiplicity='define'" config.sh
grep "^useshrplib='true'" config.sh
grep "^d_thread_local='undef'" config.sh
grep "^i_db='define'" config.sh
grep "^i_gdbm='define'" config.sh
grep "^d_crypt='define'" config.sh
grep "^dynamic_ext=.*DB_File" config.sh
grep "^dynamic_ext=.*GDBM_File" config.sh
grep -- '-O2 -g' config.sh
grep -- '-fstack-protector-strong' config.sh
"@

$build = @"
#!/usr/bin/env bash
set -euo pipefail
cd '$sourceMsys'
export PATH='/usr/bin:${toolchainMsys}/bin:${dependencyBinMsys}:'"`$PATH"
export LD_LIBRARY_PATH="${dependencyBinMsys}:`${LD_LIBRARY_PATH:-}"
export MSYS='winsymlinks:native'
make -j$Jobs
make test_prep
for root08_dll_dir in `$(printf '%s\n' '${dependencyBinMsys}' | tr ':' ' '); do
  for root08_dll in msys-crypt-2.dll msys-db-6.2.dll cyggdbm-6.dll cyggdbm_compat-4.dll msys-intl-8.dll msys-iconv-2.dll; do
    if test -f "`$root08_dll_dir/`$root08_dll"; then
      for root08_dll_target in . t; do
        cp -f "`$root08_dll_dir/`$root08_dll" "`$root08_dll_target/`$root08_dll"
      done
    fi
  done
done
export PATH='${sourceMsys}:${sourceMsys}/t:'"`$PATH"
TEST_JOBS=$TestJobs TESTFILE=harness ./runtests choose
if test -z "`${DESTDIR:-}"; then
  DESTDIR='$sourceMsys/root08-dest'
fi
make DESTDIR="`$DESTDIR" install
"@

$smoke = @"
use strict;
use warnings;

my @modules = qw(
  $($requiredModules -join ' ')
  $($gitPackageModules -join ' ')
);
my @failed;
for my `$module (@modules) {
    eval "require `$module; 1" or push @failed, [`$module, `$@];
}
if (@failed) {
    for my `$failure (@failed) {
        my (`$module, `$error) = @`$failure;
        `$error =~ s/\s+\z//;
        print STDERR "not ok - `$module - `$error\n";
    }
    exit 1;
}
print "ok - root08 core and Git-facing Perl module smoke\n";
"@

Set-Content -LiteralPath (Join-Path $candidateFull 'configure-root08.sh') -Value $configure -Encoding UTF8
Set-Content -LiteralPath (Join-Path $candidateFull 'verify-config-root08.sh') -Value $verify -Encoding UTF8
Set-Content -LiteralPath (Join-Path $candidateFull 'build-install-test-root08.sh') -Value $build -Encoding UTF8
Set-Content -LiteralPath (Join-Path $candidateFull 'root08-git-module-smoke.pl') -Value $smoke -Encoding UTF8

$manifest = [ordered]@{
    status = 'commands-generated-not-run'
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    source = [ordered]@{
        preparedSource = [IO.Path]::GetFullPath($PreparedSource)
        candidateSource = [IO.Path]::GetFullPath($candidateSource)
        preparedSourceReceipt = [IO.Path]::GetFullPath($PreparedSourceReceipt)
        preparedSourceReceiptSha256 = $sourceReceiptSha
        sourcePrepBoundary = 'candidate source is a fresh copy from the authorized root08 source-prep; do not mutate the sealed prepared source or rebuild from symlink cookies'
        candidateSourceCorrections = $candidateSourceCorrections
    }
    toolchain = [ordered]@{
        prefix = [IO.Path]::GetFullPath($ToolchainPrefix)
        jobs = $Jobs
        testJobs = $TestJobs
    }
    sdk = [ordered]@{
        export = [IO.Path]::GetFullPath($V12SdkExport)
        exportSha256 = $v12SdkExportSha
        cohort = [IO.Path]::GetFullPath($V12SdkCohort)
        usage = 'explicit -isysroot for the fresh candidate only'
    }
    dependencyPrefixes = [ordered]@{
        db = $db
        gdbm = $gdbm
        libxcrypt = $crypt
        runtimeDeps = $runtimeDeps
    }
    inputFiles = $inputFiles
    gitFacingPackages = [ordered]@{
        gitPerl = @('perl', 'perl-Error', 'perl-libwww', 'perl-TermReadKey')
        gitSendEmail = @('perl-Authen-SASL', 'perl-MIME-tools', 'perl-Net-SMTP-SSL')
        gitSvn = @('subversion')
        gitCvs = @('perl-DBI')
        gitSdkProfile = @('perl-HTML-Parser', 'perl-Locale-Gettext', 'perl-Net-SSLeay', 'perl-XML-Parser', 'perl-YAML-Syck')
    }
    requiredSmokeModules = $requiredModules
    gitPackageSmokeModules = $gitPackageModules
    testRuntimeStaging = @(
        'After make test_prep, build-install-test-root08.sh copies admitted dependency DLLs beside both ./perl.exe and t/perl.exe so tests that intentionally reduce PATH can still fork/exec the shared-libperl Perl.',
        'The script invokes TESTFILE=harness ./runtests choose directly after staging instead of make test_harness, because test_harness has a phony test_prep dependency that would rerun after staging.',
        'The copied DLL set is limited to DB, GDBM, libxcrypt, intl, and iconv runtime files already supplied through the hash-bound private prefixes.'
    )
    outputs = @('configure-root08.sh', 'verify-config-root08.sh', 'build-install-test-root08.sh', 'root08-git-module-smoke.pl')
    prohibitedInputs = @(
        'revoked libdb dffab36f/ebf75d4e/aff9e103/b81d6185',
        'revoked assembler input 161b8d63',
        'old DB four-package export',
        'older/historical crypt packages for final candidate mapping',
        'unadmitted GDBM roots from this Perl lane'
    )
}
$manifestPath = Join-Path $candidateFull 'root08-candidate-command-manifest.json'
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

[ordered]@{
    manifest = $manifestPath
    manifestSha256 = Get-Sha256 $manifestPath
    outputs = $manifest.outputs
    ready = ($db.status -eq 'provided' -and $gdbm.status -eq 'provided' -and $crypt.status -eq 'provided')
} | ConvertTo-Json -Depth 6
