param(
    [string]$Version = "local",
    [string]$OutputRoot = "dist"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    $outputRootPath = [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    $outputRootPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot))
}
$packageName = "RAGenius-Demo-$Version-Windows"
$packageDir = Join-Path $outputRootPath $packageName
$payloadDir = Join-Path $packageDir "RAGenius-Demo"
$zipPath = "$packageDir.zip"

$requiredPaths = @(
    "packaging/demo/compose.demo.yml",
    "packaging/demo/.env.template",
    "packaging/demo/Install.ps1",
    "packaging/demo/Start.ps1",
    "packaging/demo/Stop.ps1",
    "packaging/demo/Reset.ps1",
    "demo-data",
    "docker/postgres/init/10-create-execution-database.sql",
    "rag_subsystem/sql/init_pgvector.sql"
)

foreach ($relativePath in $requiredPaths) {
    $fullPath = Join-Path $repoRoot $relativePath
    if (-not (Test-Path $fullPath)) {
        throw "Required package input is missing: $relativePath"
    }
}

New-Item -ItemType Directory -Path $outputRootPath -Force | Out-Null

if (Test-Path $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
}

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null

Copy-Item -Path (Join-Path $repoRoot "packaging/demo/*") -Destination $payloadDir -Recurse -Force
Copy-Item -Path (Join-Path $repoRoot "demo-data") -Destination (Join-Path $payloadDir "demo-data") -Recurse -Force

$packageDockerInit = Join-Path $payloadDir "docker/postgres/init"
New-Item -ItemType Directory -Path $packageDockerInit -Force | Out-Null
Copy-Item -Path (Join-Path $repoRoot "docker/postgres/init/10-create-execution-database.sql") -Destination $packageDockerInit -Force

$packageRagSql = Join-Path $payloadDir "rag_subsystem/sql"
New-Item -ItemType Directory -Path $packageRagSql -Force | Out-Null
Copy-Item -Path (Join-Path $repoRoot "rag_subsystem/sql/init_pgvector.sql") -Destination $packageRagSql -Force

$hiddenFlag = [System.IO.FileAttributes]::Hidden
Get-ChildItem -LiteralPath $payloadDir -Recurse -Force | ForEach-Object {
    if (($_.Attributes -band $hiddenFlag) -ne 0) {
        $_.Attributes = [System.IO.FileAttributes]([int]$_.Attributes -band (-bnot [int]$hiddenFlag))
    }
}

Compress-Archive -Path $payloadDir -DestinationPath $zipPath -Force

Write-Host "Created $zipPath"
