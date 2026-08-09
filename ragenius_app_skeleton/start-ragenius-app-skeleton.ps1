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
    throw ".env not found in $Root. Configure the app before startup."
}

Import-DotEnv $envPath
$repoRoot = (Resolve-Path (Join-Path $Root "..")).Path
$pythonPaths = @($repoRoot)
if ($env:PYTHONPATH) { $pythonPaths += $env:PYTHONPATH }
$env:PYTHONPATH = $pythonPaths -join [System.IO.Path]::PathSeparator
$frontendRoot = Join-Path $Root "frontend"
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    Push-Location $frontendRoot
    try { npm install } finally { Pop-Location }
}

Write-Host "Starting ragenius_app_skeleton backend on port 8000..."
$backend = Start-Process -FilePath "python" -ArgumentList @(
    "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"
) -WorkingDirectory $Root -NoNewWindow -PassThru

try {
    Start-Sleep -Seconds 1
    if ($backend.HasExited) {
        throw "ragenius_app_skeleton backend exited during startup."
    }
    Set-Location $frontendRoot
    Write-Host "Starting ragenius_app_skeleton frontend on port 5173..."
    npm run dev -- --host 127.0.0.1 --port 5173
} finally {
    if (-not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}
