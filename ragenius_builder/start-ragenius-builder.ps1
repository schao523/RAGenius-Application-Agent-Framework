$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Import-DotEnv([string]$Path) {
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        $separator = $line.IndexOf("=")
        if ($separator -le 0) { continue }
        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ([Environment]::GetEnvironmentVariable($key, "Process") -eq $null) {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

$envPath = Join-Path $Root ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    throw ".env not found in $Root. Configure Builder before startup."
}

Import-DotEnv $envPath
$repoRoot = (Resolve-Path (Join-Path $Root "..")).Path
$ragBackend = if ($env:RAG_VECTOR_STORE_BACKEND) { $env:RAG_VECTOR_STORE_BACKEND.Trim().ToLowerInvariant() } else { "pgvector" }
if ($ragBackend -in @("pgvector", "postgres", "postgresql")) {
    $ragDsn = if ($env:RAG_VECTOR_STORE_DSN) { $env:RAG_VECTOR_STORE_DSN } else { "postgresql://ragenius:ragenius@localhost:5433/ragenius" }
    & (Join-Path $repoRoot "scripts\Test-RageniusPostgres.ps1") -ConnectionString $ragDsn -Label "RAG database"
}
Set-Location (Join-Path $Root "flask_scaffold")
Write-Host "Starting ragenius_builder on port 8011..."
python -m flask --app app.py run --host 127.0.0.1 --port 8011
