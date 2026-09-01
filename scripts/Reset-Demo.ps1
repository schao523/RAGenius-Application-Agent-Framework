param(
  [string]$DemoDataDir = ".\demo-data",
  [string]$RuntimeRoot = ".\runtime\demo"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installScript = Join-Path $PSScriptRoot "Install-DemoData.ps1"

if (-not (Test-Path -LiteralPath $installScript)) {
  throw "Demo data installer not found: $installScript"
}

Write-Host "Resetting RAGenius demo runtime..."
Write-Host "Demo data: $DemoDataDir"
Write-Host "Runtime root: $RuntimeRoot"

& $installScript -DemoDataDir $DemoDataDir -RuntimeRoot $RuntimeRoot -Force

$resolvedRuntimeRoot = (Resolve-Path -LiteralPath $RuntimeRoot).Path
Write-Host "Demo runtime reset complete: $resolvedRuntimeRoot"
