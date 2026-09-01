param(
  [string]$RepoRoot = ".",
  [string]$OutputDir = ".\demo-data",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "export_demo_seed.py"
$argsList = @($scriptPath, "--repo-root", $RepoRoot, "--output-dir", $OutputDir)

if ($Force) {
  $argsList += "--force"
}

python @argsList
