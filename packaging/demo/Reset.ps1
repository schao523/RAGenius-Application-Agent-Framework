$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

docker compose -f compose.demo.yml down -v
docker compose -f compose.demo.yml up -d

Write-Host ""
Write-Host "RAGenius demo reset complete. Runtime data was recreated from demo-data."
Write-Host "Application Runner: http://127.0.0.1:5173"
Write-Host "Builder:            http://127.0.0.1:8011"
