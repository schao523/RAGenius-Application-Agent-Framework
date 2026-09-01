param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "Installing RAGenius Python dependencies for the active python executable..."
python -c "import sys; print(sys.executable)"

Push-Location $repoRoot
try {
  python -m pip install -e ".[dev]"
  python -m pip install -r ".\ragenius_builder\requirements.txt"
  python -m pip install -r ".\ragenius_app_skeleton\backend\requirements.txt"
}
finally {
  Pop-Location
}

Write-Host "Python dependency installation complete."
