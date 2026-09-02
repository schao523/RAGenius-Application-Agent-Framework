param(
  [string]$ModelRoot = "",
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

if (-not $ModelRoot) {
  $ModelRoot = Join-Path $scriptRoot "models"
}

function Resolve-SetupPath([string]$PathValue, [string]$BasePath) {
  if ([System.IO.Path]::IsPathRooted($PathValue)) {
    return [System.IO.Path]::GetFullPath($PathValue)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $BasePath $PathValue))
}

function Invoke-CheckedNativeCommand([string]$FilePath, [string[]]$ArgumentList) {
  & $FilePath @ArgumentList
  if ($LASTEXITCODE -ne 0) {
    throw "$FilePath failed with exit code $LASTEXITCODE"
  }
}

$modelRootPath = Resolve-SetupPath -PathValue $ModelRoot -BasePath $scriptRoot
New-Item -ItemType Directory -Force -Path $modelRootPath | Out-Null

$containerCommand = @"
python -m pip install --no-cache-dir huggingface_hub && python /demo/download_embeddings.py --model-root /demo/models
"@

if ($Force) {
  $containerCommand = "$containerCommand --force"
}

$dockerArgs = @(
  "run",
  "--rm",
  "-v",
  "${scriptRoot}:/demo",
  "-w",
  "/demo",
  "python:3.12-slim",
  "sh",
  "-c",
  $containerCommand
)

Invoke-CheckedNativeCommand "docker" $dockerArgs

Write-Host ""
Write-Host "Embedding models are ready under $modelRootPath."
Write-Host "Compose mounts this folder into Builder and app-backend as /models."
Write-Host "Model IDs:"
Write-Host "  BAAI/bge-large-zh-v1.5"
Write-Host "  intfloat/e5-large-v2"
