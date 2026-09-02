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

Invoke-DemoCompose pull

Write-Host ""
Write-Host "Images downloaded. Start the demo with:"
Write-Host "  .\Setup-Embeddings.ps1"
Write-Host "  .\Start.ps1"
Write-Host ""
Write-Host "URLs after startup:"
Write-Host "  Application Runner: http://127.0.0.1:5173"
Write-Host "  Builder:            http://127.0.0.1:8011"
