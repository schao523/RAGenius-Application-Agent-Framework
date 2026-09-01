$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

docker compose -f compose.demo.yml down

Write-Host "RAGenius demo containers stopped. Docker volumes were kept."
