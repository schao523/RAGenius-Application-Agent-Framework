$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

function Invoke-DemoCompose {
    docker compose -f compose.demo.yml @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

Invoke-DemoCompose down

Write-Host "RAGenius demo containers stopped. Docker volumes were kept."
