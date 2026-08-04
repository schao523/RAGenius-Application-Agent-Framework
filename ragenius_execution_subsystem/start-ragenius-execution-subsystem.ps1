$Root = "D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem"

Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Host ".env not found. Copy .env.example to .env first."
    exit 1
}

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies..."
    npm install
}

if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5433/ragenius_execution?schema=public"
}

if (-not $env:NODE_ENV) {
    $env:NODE_ENV = "development"
}

if (-not $env:PORT) {
    $env:PORT = "3001"
}

if (-not $env:LOG_LEVEL) {
    $env:LOG_LEVEL = "info"
}

Write-Host "Starting ragenius_execution_subsystem..."
npm run dev
