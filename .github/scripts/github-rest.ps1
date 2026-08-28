Set-StrictMode -Version Latest

function Assert-GitHubRepository {
    param([Parameter(Mandatory)][object]$Repository)

    if ($Repository -isnot [string] -or
        $Repository -cnotmatch '^(?<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/(?<name>[A-Za-z0-9_.-]{1,100})$') {
        throw "Invalid GitHub repository identity: $Repository"
    }
    $name = $Matches.name
    if ($name -in @('.', '..') -or $name.EndsWith('.git')) {
        throw "Invalid GitHub repository identity: $Repository"
    }
    return $Repository
}

function Assert-GitHubObjectId {
    param(
        [Parameter(Mandatory)][object]$Value,
        [string]$Context = 'GitHub object ID'
    )

    if ($Value -isnot [string] -or
        $Value -cnotmatch '^[0-9a-f]{40}$' -or $Value -ceq ('0' * 40)) {
        throw "$Context must be an exact lowercase nonzero 40-hex object ID."
    }
    return $Value
}

function Assert-GitHubPositiveId {
    param(
        [Parameter(Mandatory)][object]$Value,
        [string]$Context = 'GitHub numeric ID'
    )

    $parsed = 0L
    if ($Value -is [bool] -or "$Value" -cnotmatch '^[1-9][0-9]*$') {
        throw "$Context must be a positive numeric ID."
    }
    if (-not [long]::TryParse(
            "$Value",
            [Globalization.NumberStyles]::None,
            [Globalization.CultureInfo]::InvariantCulture,
            [ref]$parsed
        )) {
        throw "$Context must be a positive numeric ID."
    }
    return $parsed
}

function ConvertTo-GitHubEncodedRef {
    param(
        [Parameter(Mandatory)][object]$Value,
        [string]$Context = 'GitHub ref'
    )

    if ($Value -isnot [string] -or $Value.Length -gt 255 -or
        $Value -cnotmatch '^[A-Za-z0-9._/-]+$' -or
        $Value.StartsWith('/') -or $Value.EndsWith('/') -or
        $Value.Contains('//') -or $Value.Contains('..') -or
        $Value.Contains('@{') -or $Value.EndsWith('.') -or $Value.EndsWith('.lock')) {
        throw "Invalid $Context."
    }
    $parts = @($Value.Split('/'))
    if ($parts.Count -eq 0 -or @($parts | Where-Object { $_ -in @('', '.', '..') }).Count -ne 0) {
        throw "Invalid $Context."
    }
    return ($parts | ForEach-Object { [Uri]::EscapeDataString($_) }) -join '/'
}

function ConvertTo-GitHubEncodedPath {
    param([Parameter(Mandatory)][object]$Path)

    if ($Path -isnot [string] -or $Path.Length -gt 1024 -or
        $Path -cnotmatch '^[A-Za-z0-9._/-]+$' -or
        $Path.StartsWith('/') -or $Path.EndsWith('/') -or
        $Path.Contains('//') -or $Path.Contains('\')) {
        throw 'Invalid repository-relative GitHub path.'
    }
    $parts = @($Path.Split('/'))
    if ($parts.Count -eq 0 -or @($parts | Where-Object { $_ -in @('', '.', '..') }).Count -ne 0) {
        throw 'Repository-relative GitHub paths cannot traverse directories.'
    }
    return ($parts | ForEach-Object { [Uri]::EscapeDataString($_) }) -join '/'
}

function Assert-GitHubRestUri {
    param([Parameter(Mandatory)][Uri]$Uri)

    if (-not $Uri.IsAbsoluteUri -or
        $Uri.Scheme -cne 'https' -or
        $Uri.Host -cne 'api.github.com' -or
        -not $Uri.IsDefaultPort -or
        -not [string]::IsNullOrEmpty($Uri.UserInfo) -or
        -not [string]::IsNullOrEmpty($Uri.Fragment) -or
        -not $Uri.AbsoluteUri.StartsWith('https://api.github.com/', [StringComparison]::Ordinal)) {
        throw 'GitHub REST requests are restricted to https://api.github.com.'
    }

    $path = $Uri.GetComponents([UriComponents]::Path, [UriFormat]::UriEscaped)
    $query = $Uri.Query
    if ($path -cnotmatch '^repos/(?<owner>[A-Za-z0-9-]+)/(?<name>[A-Za-z0-9_.-]+)/') {
        throw 'GitHub REST URI has no valid repository identity.'
    }
    [void](Assert-GitHubRepository "$($Matches.owner)/$($Matches.name)")
    $repository = '[A-Za-z0-9-]+/[A-Za-z0-9_.-]+'
    $sha = '[0-9a-f]{40}'
    $positive = '[1-9][0-9]*'
    $safePath = '[A-Za-z0-9._/-]+'
    $route = "^repos/$repository/(?:" +
        "releases/$positive(?:/assets)?|" +
        "git/ref/tags/$safePath|git/tags/$sha|git/commits/$sha|git/trees/$sha|git/blobs/$sha|" +
        "compare/$sha\.\.\.$sha|" +
        "actions/runs/$positive(?:/attempts/$positive/jobs|/artifacts)?|" +
        "contents/$safePath)$"
    if ($path -cnotmatch $route -or $path.Contains('//') -or
        $path.Contains('/./') -or $path.Contains('/../') -or $path.Contains('%')) {
        throw 'GitHub REST URI does not match an approved endpoint shape.'
    }
    foreach ($objectId in [regex]::Matches($path, '[0-9a-f]{40}')) {
        [void](Assert-GitHubObjectId $objectId.Value 'GitHub REST URI object ID')
    }
    foreach ($numericPattern in @('/releases/(?<id>[1-9][0-9]*)', '/runs/(?<id>[1-9][0-9]*)',
            '/attempts/(?<id>[1-9][0-9]*)')) {
        foreach ($numericMatch in [regex]::Matches($path, $numericPattern)) {
            [void](Assert-GitHubPositiveId $numericMatch.Groups['id'].Value 'GitHub REST URI numeric ID')
        }
    }

    if ($path -cmatch "/releases/$positive/assets$") {
        if ($query -cnotmatch '^\?per_page=(?<perPage>[1-9][0-9]*)&page=(?<page>[1-9][0-9]*)$') {
            throw 'GitHub release asset query is invalid.'
        }
        $queryPerPage = $Matches.perPage
        $queryPage = $Matches.page
        if ((Assert-GitHubPositiveId $queryPerPage 'per_page') -gt 100) {
            throw 'GitHub release asset query is invalid.'
        }
        [void](Assert-GitHubPositiveId $queryPage 'page')
    }
    elseif ($path -cmatch "/actions/runs/$positive/(?:attempts/$positive/jobs|artifacts)$") {
        if ($query -cne '?per_page=100') {
            throw 'GitHub Actions list query is invalid.'
        }
    }
    elseif ($path -cmatch '/contents/') {
        if ($query -cnotmatch "^\?ref=$sha$" -or $query.Substring(5) -ceq ('0' * 40)) {
            throw 'GitHub contents ref query is invalid.'
        }
    }
    elseif ($path -cmatch "/git/trees/$sha$") {
        if ($query -cne '?recursive=1') {
            throw 'GitHub recursive tree query is invalid.'
        }
    }
    elseif (-not [string]::IsNullOrEmpty($query)) {
        throw 'Unexpected GitHub REST query string.'
    }
}

function New-GitHubRestRequest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Repository,
        [Parameter(Mandatory)]
        [ValidateSet(
            'Release', 'ReleaseAssets', 'TagRef', 'TagObject', 'Commit', 'Tree', 'Blob', 'Compare',
            'WorkflowRun', 'AttemptJobs', 'RunArtifacts', 'Contents'
        )]
        [string]$Endpoint,
        [object]$ReleaseId,
        [object]$RunId,
        [object]$Attempt,
        [object]$ObjectId,
        [object]$BaseObjectId,
        [object]$HeadObjectId,
        [object]$TagName,
        [object]$Path,
        [object]$RefObjectId,
        [object]$Page,
        [object]$PerPage,
        [long]$MaxResponseBytes = 2MB
    )

    $repositoryValue = Assert-GitHubRepository $Repository
    if ($MaxResponseBytes -le 0 -or $MaxResponseBytes -gt 8MB) {
        throw 'GitHub REST response cap must be between 1 byte and 8 MiB.'
    }

    $route = switch ($Endpoint) {
        'Release' {
            $id = Assert-GitHubPositiveId $ReleaseId 'release ID'
            "releases/$id"
        }
        'ReleaseAssets' {
            $id = Assert-GitHubPositiveId $ReleaseId 'release ID'
            $pageValue = Assert-GitHubPositiveId $Page 'page'
            $perPageValue = Assert-GitHubPositiveId $PerPage 'per_page'
            if ($perPageValue -gt 100) {
                throw 'per_page cannot exceed 100.'
            }
            "releases/$id/assets?per_page=$perPageValue&page=$pageValue"
        }
        'TagRef' {
            $encodedTag = ConvertTo-GitHubEncodedRef $TagName 'GitHub tag name'
            "git/ref/tags/$encodedTag"
        }
        'TagObject' {
            $sha = Assert-GitHubObjectId $ObjectId 'tag object ID'
            "git/tags/$sha"
        }
        'Commit' {
            $sha = Assert-GitHubObjectId $ObjectId 'commit object ID'
            "git/commits/$sha"
        }
        'Tree' {
            $sha = Assert-GitHubObjectId $ObjectId 'tree object ID'
            "git/trees/$sha?recursive=1"
        }
        'Blob' {
            $sha = Assert-GitHubObjectId $ObjectId 'blob object ID'
            "git/blobs/$sha"
        }
        'Compare' {
            $base = Assert-GitHubObjectId $BaseObjectId 'compare base object ID'
            $head = Assert-GitHubObjectId $HeadObjectId 'compare head object ID'
            "compare/$base...$head"
        }
        'WorkflowRun' {
            $id = Assert-GitHubPositiveId $RunId 'workflow run ID'
            "actions/runs/$id"
        }
        'AttemptJobs' {
            $id = Assert-GitHubPositiveId $RunId 'workflow run ID'
            $attemptValue = Assert-GitHubPositiveId $Attempt 'workflow run attempt'
            "actions/runs/$id/attempts/$attemptValue/jobs?per_page=100"
        }
        'RunArtifacts' {
            $id = Assert-GitHubPositiveId $RunId 'workflow run ID'
            "actions/runs/$id/artifacts?per_page=100"
        }
        'Contents' {
            $encodedPath = ConvertTo-GitHubEncodedPath $Path
            $sha = Assert-GitHubObjectId $RefObjectId 'contents ref object ID'
            "contents/$encodedPath?ref=$sha"
        }
    }

    $uri = [Uri]"https://api.github.com/repos/$repositoryValue/$route"
    Assert-GitHubRestUri $uri
    return [pscustomobject][ordered]@{
        Method           = 'GET'
        Uri              = $uri
        MaxResponseBytes = $MaxResponseBytes
    }
}

function Assert-GitHubJsonNoDuplicateProperties {
    param(
        [Parameter(Mandatory)][Text.Json.JsonElement]$Element,
        [string]$Context = '$'
    )

    if ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Object) {
        $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($property in $Element.EnumerateObject()) {
            if (-not $names.Add($property.Name)) {
                throw "Duplicate JSON object property at ${Context}: $($property.Name)"
            }
            Assert-GitHubJsonNoDuplicateProperties `
                -Element $property.Value `
                -Context "$Context.$($property.Name)"
        }
    }
    elseif ($Element.ValueKind -eq [Text.Json.JsonValueKind]::Array) {
        $index = 0
        foreach ($item in $Element.EnumerateArray()) {
            Assert-GitHubJsonNoDuplicateProperties -Element $item -Context "$Context[$index]"
            $index++
        }
    }
}

function ConvertFrom-GitHubRestResponse {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Response,
        [long]$MaxResponseBytes = 2MB
    )

    if ($MaxResponseBytes -le 0 -or $MaxResponseBytes -gt 8MB) {
        throw 'GitHub REST response cap must be between 1 byte and 8 MiB.'
    }
    if ($null -eq $Response.StatusCode) {
        throw 'GitHub REST response has no status code.'
    }
    $statusCode = [int]$Response.StatusCode
    if ($statusCode -lt 200 -or $statusCode -gt 299) {
        throw "GitHub REST request failed closed with HTTP status $statusCode."
    }
    if ($null -eq $Response.Content) {
        throw 'GitHub REST response has no content.'
    }

    $contentType = $Response.Content.Headers.ContentType
    $mediaType = if ($null -eq $contentType) { '' } else { [string]$contentType.MediaType }
    if ([string]::IsNullOrWhiteSpace($mediaType) -or
        ($mediaType -cne 'application/json' -and -not $mediaType.EndsWith('+json', [StringComparison]::Ordinal))) {
        throw "GitHub REST response content type is not JSON: $mediaType"
    }
    $declaredLength = $Response.Content.Headers.ContentLength
    if ($null -ne $declaredLength -and [long]$declaredLength -lt 0) {
        throw 'GitHub REST response has an invalid declared content length.'
    }
    if ($null -ne $declaredLength -and [long]$declaredLength -gt $MaxResponseBytes) {
        throw 'GitHub REST response exceeds its declared byte cap.'
    }

    $stream = $Response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
    $buffer = [byte[]]::new(8192)
    $output = [IO.MemoryStream]::new()
    try {
        while (($read = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($output.Length + $read -gt $MaxResponseBytes) {
                throw 'GitHub REST response exceeds its actual byte cap.'
            }
            $output.Write($buffer, 0, $read)
        }
        if ($null -ne $declaredLength -and $output.Length -ne [long]$declaredLength) {
            throw 'GitHub REST response was truncated or has an incorrect content length.'
        }
        $bytes = $output.ToArray()
    }
    finally {
        $output.Dispose()
        $stream.Dispose()
    }

    try {
        $text = [Text.UTF8Encoding]::new($false, $true).GetString($bytes)
    }
    catch {
        throw 'GitHub REST response is not valid UTF-8.'
    }
    try {
        $document = [Text.Json.JsonDocument]::Parse(
            $text,
            [Text.Json.JsonDocumentOptions]@{
                AllowTrailingCommas = $false
                CommentHandling    = [Text.Json.JsonCommentHandling]::Disallow
                MaxDepth           = 64
            }
        )
    }
    catch {
        throw 'GitHub REST response is not valid JSON.'
    }
    try {
        Assert-GitHubJsonNoDuplicateProperties -Element $document.RootElement
    }
    finally {
        $document.Dispose()
    }

    try {
        return $text | ConvertFrom-Json -Depth 64 -NoEnumerate
    }
    catch {
        throw 'GitHub REST response cannot be represented safely as PowerShell JSON.'
    }
}

function Invoke-GitHubRestGet {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object]$Request,
        [Parameter(Mandatory)][string]$Token
    )

    $requestProperties = @($Request.PSObject.Properties.Name)
    if ($requestProperties -cnotcontains 'Method' -or
        $requestProperties -cnotcontains 'Uri' -or
        $requestProperties -cnotcontains 'MaxResponseBytes') {
        throw 'GitHub REST request object is incomplete.'
    }
    if ($Request.Method -cne 'GET') {
        throw 'GitHub REST transport permits GET only.'
    }
    $uri = [Uri]$Request.Uri
    Assert-GitHubRestUri $uri
    $cap = [long]$Request.MaxResponseBytes
    if ($cap -le 0 -or $cap -gt 8MB) {
        throw 'GitHub REST response cap must be between 1 byte and 8 MiB.'
    }
    if ([string]::IsNullOrWhiteSpace($Token) -or $Token.Length -gt 1024 -or
        $Token -cnotmatch '^[A-Za-z0-9_.-]+$') {
        throw 'The GitHub token has an invalid transport format.'
    }

    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseCookies = $false
    $handler.AutomaticDecompression = [Net.DecompressionMethods]::None
    $HttpClient = [Net.Http.HttpClient]::new($handler, $true)
    $HttpClient.Timeout = [TimeSpan]::FromSeconds(30)
    $message = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Get, $uri)
    try {
        $message.Headers.Accept.ParseAdd('application/vnd.github+json')
        $message.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Token)
        $message.Headers.Add('X-GitHub-Api-Version', '2022-11-28')
        $message.Headers.UserAgent.ParseAdd('arm64-authoritative-collector/1')
        $response = $HttpClient.SendAsync(
            $message,
            [Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        try {
            return ConvertFrom-GitHubRestResponse -Response $response -MaxResponseBytes $cap
        }
        finally {
            $response.Dispose()
        }
    }
    finally {
        $message.Dispose()
        $HttpClient.Dispose()
    }
}
