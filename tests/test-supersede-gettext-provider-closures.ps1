#requires -Version 7.3
$ErrorActionPreference = 'Stop'
$script = [IO.File]::ReadAllText(
    "$PSScriptRoot\..\.github\scripts\supersede-gettext-provider-closures.ps1"
)
foreach ($required in @(
    '3faec2f42d87e28236dcc451ab6f48c63b67bd54aee746e1ebdf9debf3f1f30f',
    'b2c03126b1250757bd41a6f561e83fd9c0c9cb0f4d5bbf51c2be14ccc43c4677',
    '7abded5bc03698083363a22b1103afc5bacb710561002c21e7c585ed803a7e46',
    '206cffaff0a16fc2b0453d74c923b7830fa62c0d7715327cb5a61d8e35421894',
    'd71f2c02617dbc24e338065f5d5ef5e44f08669240fc40b21a9ad82a8823fc47',
    'CurrentIntakeAudit',
    'OperationalPrefixLineage',
    'b6741cedc7f502822638e9dee22740310f51cdd7eda9bdeec0b8a26e2dae6332',
    'ProviderRejectionEnforcement',
    '69818c620590f23bd38ba7921c515cdf6629d7d20a55c15fbe8427bf6f2779be',
    'without reintroducing the revoked archive or conflating admitted native MSYS gettext splits with the MinGW namespace',
    'd0e624fa2e062a92ca8df971501a33b226dcd7e4c0d76cf8e678c685b07a24fd',
    'CorrectedGitHandoff',
    '947cdb44357f6e6639b0ff87c1b4299f53073477ff9cb5ed8e30b276ed54d911',
    'mingw-w64-aarch64-gettext-1.0-1',
    'GettextProviderExport',
    'Export-SupersededClosure network',
    'Export-SupersededClosure python',
    'unchangedPackageArchives',
    'revoked-free baseline unexpectedly contains',
    'closure_complete',
    'missingClosureDependencies',
    'baseline lacks replacement gettext dependencies',
    'Only the revoked gettext archive is replaced.',
    'No compatibility alias or 0.26 provider identity is emitted.',
    'd060e2d1127b52b49f7956d5eee59681ae160cd79bdac2156a45c05fbdd46669',
    '28dfc8ae4069a3fbf31bd461aff0d1c01d9701fe219c70de199b0087943e22d9'
)) {
    if (-not $script.Contains($required, [StringComparison]::Ordinal)) {
        throw "Gettext closure supersession lost invariant: $required"
    }
}

'PASS: gettext supersession replaces only the revoked archive in both closures'
