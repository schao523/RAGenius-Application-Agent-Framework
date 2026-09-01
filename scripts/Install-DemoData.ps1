param(
  [string]$DemoDataDir = ".\demo-data",
  [string]$RuntimeRoot = ".\runtime\demo",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "install_demo_seed.py"
$argsList = @($scriptPath, "--demo-data-dir", $DemoDataDir, "--runtime-root", $RuntimeRoot)

if ($Force) {
  $argsList += "--force"
}

python @argsList
