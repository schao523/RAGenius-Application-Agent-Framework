param(
  [string]$RuntimeRoot = ".\runtime\demo"
)

$ErrorActionPreference = "Stop"

$processFile = Join-Path $RuntimeRoot "demo-processes.json"

if (-not (Test-Path -LiteralPath $processFile)) {
  Write-Host "No demo process file found at $processFile. Nothing to stop."
  exit 0
}

$processRecords = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
$stopped = 0

foreach ($record in @($processRecords)) {
  $pidValue = [int]$record.pid
  $name = if ($record.name) { [string]$record.name } else { "process" }
  if ($pidValue -le 0) {
    continue
  }

  $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
  if ($null -eq $process) {
    Write-Host "$name is not running (PID $pidValue)."
    continue
  }

  Write-Host "Stopping $name (PID $pidValue)..."
  Stop-Process -Id $pidValue -Force
  $stopped += 1
}

Remove-Item -LiteralPath $processFile -Force
Write-Host "Stopped $stopped RAGenius demo process(es)."
