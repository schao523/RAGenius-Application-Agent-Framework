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

Set-Location $Root

if (-not (Test-Path ".env")) {
    throw ".env not found. Copy .env.example to .env and configure it first."
}

Import-DotEnv (Join-Path $Root ".env")

$Port = if ($env:PORT) { [int]$env:PORT } else { 3001 }
$portClient = New-Object System.Net.Sockets.TcpClient
$connectResult = $portClient.BeginConnect("127.0.0.1", $Port, $null, $null)
$portInUse = $connectResult.AsyncWaitHandle.WaitOne(1000)
if ($portInUse) {
    try { $portClient.EndConnect($connectResult) } catch { }
}
$portClient.Close()

if ($portInUse) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 3
        if ($health.status -eq "ok") {
            Write-Host "ragenius_execution_subsystem is already running on port $Port."
            Write-Host "Stop the existing runtime with Ctrl+C before restarting it."
            exit 0
        }
    }
    catch {
        # The listener is not a healthy execution-subsystem instance.
    }

    throw "Port $Port is already in use. Stop the process using that port before starting ragenius_execution_subsystem."
}

Write-Host "Synchronizing execution dependencies..."
npm install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Generating Prisma client..."
npx prisma generate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Applying pending Prisma migrations..."
npx prisma migrate deploy
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Starting ragenius_execution_subsystem on port $env:PORT..."
npm run dev
