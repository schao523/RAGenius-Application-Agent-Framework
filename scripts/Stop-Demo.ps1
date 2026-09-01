param(
  [string]$RuntimeRoot = ".\runtime\demo",
  [switch]$SkipPortCleanup
)

$ErrorActionPreference = "Stop"

$processFile = Join-Path $RuntimeRoot "demo-processes.json"
$knownDemoPorts = @(3001, 8000, 8011, 5173)

function Stop-KnownDemoPortListeners([int[]]$Ports) {
  if ($SkipPortCleanup) {
    return 0
  }
  if ($null -eq (Get-Command "Get-NetTCPConnection" -ErrorAction SilentlyContinue)) {
    Write-Host "Get-NetTCPConnection is unavailable; skipping demo port listener cleanup."
    return 0
  }

  $stoppedByPort = 0
  foreach ($port in $Ports) {
    $connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
      $pidValue = [int]$connection.OwningProcess
      if ($pidValue -le 0 -or $pidValue -eq $PID) {
        continue
      }
      $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
      if ($null -eq $process) {
        continue
      }
      Write-Host "Stopping listener on demo port $port (PID $pidValue, $($process.ProcessName))..."
      Stop-Process -Id $pidValue -Force
      $stoppedByPort += 1
    }
  }
  return $stoppedByPort
}

if (-not (Test-Path -LiteralPath $processFile)) {
  Write-Host "No demo process file found at $processFile. Checking known demo ports."
  $portStopped = Stop-KnownDemoPortListeners -Ports $knownDemoPorts
  Write-Host "Stopped $portStopped listener(s) on known RAGenius demo ports."
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
$portStopped = Stop-KnownDemoPortListeners -Ports $knownDemoPorts
Write-Host "Stopped $stopped recorded RAGenius demo process(es)."
Write-Host "Stopped $portStopped listener(s) on known RAGenius demo ports."
