$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.template" ".env"
    Write-Host "Created .env from .env.template. Edit .env and set your LLM API key before using chat."
}

docker compose -f compose.demo.yml pull

Write-Host ""
Write-Host "Images downloaded. Start the demo with:"
Write-Host "  .\Start.ps1"
Write-Host ""
Write-Host "URLs after startup:"
Write-Host "  Application Runner: http://127.0.0.1:5173"
Write-Host "  Builder:            http://127.0.0.1:8011"
