param(
    [string]$StartUrl = "http://127.0.0.1:50227/en/html/",
    [string]$OutputDir = "$env:USERPROFILE\Downloads\modefrontier-docs",
    [int]$MaxFiles = 10000,
    [int]$TimeoutSec = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Normalize-Url {
    param([string]$Url)
    return ($Url -replace "#.*$", "")
}

function Test-AllowedUrl {
    param(
        [Uri]$Uri,
        [Uri]$BaseUri
    )

    return (
        $Uri.Scheme -in @("http", "https") -and
        $Uri.Authority -eq $BaseUri.Authority -and
        $Uri.AbsolutePath.StartsWith($BaseUri.AbsolutePath)
    )
}

function Get-LocalPath {
    param(
        [Uri]$Uri,
        [Uri]$BaseUri,
        [string]$RootDir
    )

    $relativePath = $Uri.AbsolutePath.Substring($BaseUri.AbsolutePath.Length).TrimStart("/")
    if ([string]::IsNullOrWhiteSpace($relativePath) -or $relativePath.EndsWith("/")) {
        $relativePath = Join-Path $relativePath "index.html"
    }

    $relativePath = [Uri]::UnescapeDataString($relativePath) -replace "/", "\"
    $targetPath = Join-Path $RootDir $relativePath

    if ([string]::IsNullOrWhiteSpace([IO.Path]::GetExtension($targetPath))) {
        $targetPath = "$targetPath.html"
    }

    return $targetPath
}

function Get-LinkedUrls {
    param(
        [string]$Body,
        [Uri]$CurrentUri
    )

    $patterns = @(
        '(?i)(?:href|src)\s*=\s*["'']([^"'']+)["'']',
        '(?i)url\((?:["'']?)([^"'')]+)(?:["'']?)\)'
    )

    foreach ($pattern in $patterns) {
        foreach ($match in [regex]::Matches($Body, $pattern)) {
            $raw = $match.Groups[1].Value.Trim()
            if (
                [string]::IsNullOrWhiteSpace($raw) -or
                $raw.StartsWith("mailto:") -or
                $raw.StartsWith("javascript:")
            ) {
                continue
            }

            try {
                [Uri]::new($CurrentUri, $raw)
            }
            catch {
                continue
            }
        }
    }
}

$StartUrl = Normalize-Url $StartUrl
$BaseUri = [Uri]::new($StartUrl)
if (-not $BaseUri.AbsolutePath.EndsWith("/")) {
    $BaseUri = [Uri]::new($StartUrl.Substring(0, $StartUrl.LastIndexOf("/") + 1))
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$queue = [System.Collections.Generic.Queue[string]]::new()
$seen = [System.Collections.Generic.HashSet[string]]::new()
$queue.Enqueue($BaseUri.AbsoluteUri)
$saved = 0

while ($queue.Count -gt 0 -and $saved -lt $MaxFiles) {
    $url = Normalize-Url $queue.Dequeue()
    if ($seen.Contains($url)) {
        continue
    }
    [void]$seen.Add($url)

    $uri = [Uri]::new($url)
    if (-not (Test-AllowedUrl -Uri $uri -BaseUri $BaseUri)) {
        continue
    }

    try {
        $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec $TimeoutSec
    }
    catch {
        Write-Host "SKIP $url ($($_.Exception.Message))"
        continue
    }

    $targetPath = Get-LocalPath -Uri $uri -BaseUri $BaseUri -RootDir $OutputDir
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($targetPath)) | Out-Null

    if ($response.RawContentStream) {
        $fileStream = [IO.File]::Create($targetPath)
        try {
            $response.RawContentStream.CopyTo($fileStream)
        }
        finally {
            $fileStream.Dispose()
        }
    }
    else {
        Set-Content -Path $targetPath -Value $response.Content -Encoding UTF8
    }

    $saved += 1
    Write-Host ("SAVE {0:D5} {1} -> {2}" -f $saved, $url, $targetPath)

    $contentType = ""
    if ($response.Headers["Content-Type"]) {
        $contentType = $response.Headers["Content-Type"]
    }

    if ($contentType -match "text/html|text/css|javascript" -or $targetPath -match "\.(html|htm|css|js)$") {
        foreach ($linkedUri in Get-LinkedUrls -Body ([string]$response.Content) -CurrentUri $uri) {
            $linkedUrl = Normalize-Url $linkedUri.AbsoluteUri
            if ((Test-AllowedUrl -Uri $linkedUri -BaseUri $BaseUri) -and -not $seen.Contains($linkedUrl)) {
                $queue.Enqueue($linkedUrl)
            }
        }
    }
}

Write-Host "Done. Saved $saved files to $OutputDir"
