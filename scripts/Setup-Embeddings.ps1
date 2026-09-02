param(
  [string]$ModelRoot = "",
  [switch]$SkipDependencyInstall,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $ModelRoot) {
  $ModelRoot = Join-Path $repoRoot "rag_subsystem\models"
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

$modelRootPath = Resolve-SetupPath -PathValue $ModelRoot -BasePath $repoRoot

if (-not $SkipDependencyInstall) {
  Push-Location $repoRoot
  try {
    Invoke-CheckedNativeCommand "python" @("-m", "pip", "install", "-e", ".[local-embeddings]")
  }
  finally {
    Pop-Location
  }
}

$downloadArgs = @(
  (Join-Path $PSScriptRoot "download_embeddings.py"),
  "--model-root",
  $modelRootPath
)

if ($Force) {
  $downloadArgs += "--force"
}

Invoke-CheckedNativeCommand "python" $downloadArgs

$bgePath = Join-Path $modelRootPath "bge-large-zh"
$e5Path = Join-Path $modelRootPath "e5-large"

Write-Host ""
Write-Host "Embedding models are ready."
Write-Host "Source-checkout default model root: $modelRootPath"
Write-Host ""
Write-Host "If you use .env overrides, set:"
Write-Host "RAG_EMBEDDING_BACKEND=local"
Write-Host "RAG_EMBEDDING_MODEL_PATH_BGE_LARGE_ZH=$bgePath"
Write-Host "RAG_EMBEDDING_MODEL_PATH_E5_LARGE=$e5Path"
