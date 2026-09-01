$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

function Invoke-DemoCompose {
    docker compose -f compose.demo.yml @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.template" ".env"
    Write-Host "Created .env from .env.template. Edit .env and set your LLM API key before using chat."
}

Invoke-DemoCompose up -d

Write-Host ""
Write-Host "RAGenius demo is starting."
Write-Host "Application Runner: http://127.0.0.1:5173"
Write-Host "Builder:            http://127.0.0.1:8011"
Write-Host "Backend API:        http://127.0.0.1:8000/apps"
