param(
    [Parameter(Mandatory = $true)]
    [string]$ConnectionString,

    [string]$Label = "PostgreSQL",

    [int]$TimeoutMs = 1500
)

$ErrorActionPreference = "Stop"

try {
    $uri = [System.Uri]$ConnectionString
}
catch {
    throw "$Label connection string is invalid. Check the configured PostgreSQL URL."
}

if ($uri.Scheme -notin @("postgres", "postgresql") -or [string]::IsNullOrWhiteSpace($uri.Host)) {
    throw "$Label connection string must be a PostgreSQL URL with a host."
}

$port = if ($uri.IsDefaultPort -or $uri.Port -le 0) { 5432 } else { $uri.Port }
$client = New-Object System.Net.Sockets.TcpClient

try {
    $result = $client.BeginConnect($uri.Host, $port, $null, $null)
    if (-not $result.AsyncWaitHandle.WaitOne($TimeoutMs)) {
        throw "connection timed out"
    }
    $client.EndConnect($result)
}
catch {
    throw "$Label is unavailable at $($uri.Host):$port. Start the local database with 'docker compose up -d --wait postgres' from the repository root, or start the configured PostgreSQL service."
}
finally {
    $client.Close()
}

Write-Host "$Label endpoint is reachable at $($uri.Host):$port."
