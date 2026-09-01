param(
  [string]$DemoDataDir = ".\demo-data",
  [string]$RuntimeRoot = ".\runtime\demo",
  [switch]$ForceInstall,
  [switch]$PrepareOnly,
  [switch]$SkipDependencyInstall,
  [switch]$SkipInfrastructure,
  [switch]$SkipBuilder,
  [switch]$SkipAppBackend,
  [switch]$SkipAppFrontend,
  [switch]$SkipExecutionSubsystem
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-DemoPath([string]$PathValue, [string]$BasePath) {
  if ([System.IO.Path]::IsPathRooted($PathValue)) {
    return [System.IO.Path]::GetFullPath($PathValue)
  }
  return [System.IO.Path]::GetFullPath((Join-Path $BasePath $PathValue))
}

$runtimePath = Resolve-DemoPath -PathValue $RuntimeRoot -BasePath $repoRoot
$demoDataPath = Resolve-DemoPath -PathValue $DemoDataDir -BasePath $repoRoot

function Require-Command([string]$Name, [string]$InstallHint) {
  if ($null -eq (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name is required. $InstallHint"
  }
}

function Add-PythonPath([string]$PathToAdd) {
  $paths = @($PathToAdd)
  if ($env:PYTHONPATH) {
    $paths += $env:PYTHONPATH.Split([System.IO.Path]::PathSeparator)
  }
  $deduped = @()
  foreach ($path in $paths) {
    if ($path -and -not ($deduped -contains $path)) {
      $deduped += $path
    }
  }
  $env:PYTHONPATH = $deduped -join [System.IO.Path]::PathSeparator
}

function Test-PythonModule([string]$ModuleName) {
  $probe = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)"
  python -c $probe *> $null
  return $LASTEXITCODE -eq 0
}

function Require-PythonModule([string]$ModuleName, [string]$InstallHint) {
  if (-not (Test-PythonModule -ModuleName $ModuleName)) {
    throw "Python module '$ModuleName' is required but is not installed for the active python executable. $InstallHint"
  }
}

function Install-PythonDependenciesIfNeeded() {
  if ($SkipDependencyInstall) {
    return
  }
  if ((Test-PythonModule -ModuleName "flask") -and (Test-PythonModule -ModuleName "uvicorn")) {
    return
  }
  & (Join-Path $PSScriptRoot "Install-PythonDependencies.ps1")
}

function Set-DefaultProcessEnvironment([string]$Name, [string]$Value) {
  if ([Environment]::GetEnvironmentVariable($Name, "Process") -eq $null) {
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
  }
}

function Import-DotEnvIfPresent([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }
  foreach ($rawLine in Get-Content -LiteralPath $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#")) { continue }
    $separator = $line.IndexOf("=")
    if ($separator -le 0) { continue }
    $key = $line.Substring(0, $separator).Trim()
    $value = $line.Substring($separator + 1).Trim()
    if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    if ([Environment]::GetEnvironmentVariable($key, "Process") -eq $null) {
      [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
  }
}

function Set-DemoEnvironment([string]$RuntimeRootPath) {
  $builderRoot = Join-Path $RuntimeRootPath "builder"
  $appStateRoot = Join-Path $RuntimeRootPath "app\.state"
  $values = [ordered]@{
    RAGENIUS_DEMO_RUNTIME_ROOT = $RuntimeRootPath
    RAGENIUS_BUILDER_DB = (Join-Path $builderRoot "rag_app.db")
    RAGENIUS_BUILDER_STORAGE_ROOT = $builderRoot
    RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT = (Join-Path $appStateRoot "instruction_understanding_snapshots")
    RAGENIUS_APP_STATE_DB = (Join-Path $appStateRoot "runtime_state.db")
    RAGENIUS_APP_UPLOADS_DIR = (Join-Path $appStateRoot "session_uploads")
    RAGENIUS_EXECUTION_BASE_URL = "http://127.0.0.1:3001"
    RAGENIUS_EXECUTION_SUBSYSTEM_URL = "http://127.0.0.1:3001/v1"
  }

  foreach ($entry in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, [string]$entry.Value, "Process")
  }

  New-Item -ItemType Directory -Force -Path $appStateRoot | Out-Null
  New-Item -ItemType Directory -Force -Path $values.RAGENIUS_APP_UPLOADS_DIR | Out-Null

  $envPath = Join-Path $RuntimeRootPath "demo-runtime.env.json"
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($envPath, ($values | ConvertTo-Json -Depth 4), $utf8NoBom)
  return $values
}

function Invoke-NpmInstallIfNeeded([string]$WorkingDirectory) {
  if ($SkipDependencyInstall) {
    return
  }
  if (-not (Test-Path -LiteralPath (Join-Path $WorkingDirectory "node_modules"))) {
    Write-Host "Installing npm dependencies in $WorkingDirectory..."
    Push-Location $WorkingDirectory
    try {
      npm install
    }
    finally {
      Pop-Location
    }
  }
}

function Start-DemoProcess([string]$Name, [string]$FilePath, [string[]]$ArgumentList, [string]$WorkingDirectory, [string]$LogRoot) {
  Write-Host "Starting $Name..."
  New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
  $stdoutPath = Join-Path $LogRoot "$Name.out.log"
  $stderrPath = Join-Path $LogRoot "$Name.err.log"
  $process = Start-Process `
    -FilePath $FilePath `
    -ArgumentList $ArgumentList `
    -WorkingDirectory $WorkingDirectory `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru
  return [ordered]@{
    name = $Name
    pid = $process.Id
    started_at = (Get-Date).ToString("o")
    working_directory = $WorkingDirectory
    stdout_log = $stdoutPath
    stderr_log = $stderrPath
  }
}

Require-Command "python" "Install Python 3.11+ and ensure python.exe is on PATH."

Import-DotEnvIfPresent -Path (Join-Path $repoRoot ".env")
Import-DotEnvIfPresent -Path (Join-Path $repoRoot "ragenius_app_skeleton\.env")
Import-DotEnvIfPresent -Path (Join-Path $repoRoot "ragenius_builder\.env")
Import-DotEnvIfPresent -Path (Join-Path $repoRoot "ragenius_execution_subsystem\.env")

Set-DefaultProcessEnvironment "POSTGRES_USER" "ragenius"
Set-DefaultProcessEnvironment "POSTGRES_PASSWORD" "ragenius"
Set-DefaultProcessEnvironment "POSTGRES_DB" "ragenius"
Set-DefaultProcessEnvironment "DATABASE_URL" "postgresql://ragenius:ragenius@localhost:5433/ragenius_execution?schema=public"
Set-DefaultProcessEnvironment "RAG_VECTOR_STORE_BACKEND" "pgvector"
Set-DefaultProcessEnvironment "RAG_VECTOR_STORE_DSN" "postgresql://ragenius:ragenius@localhost:5433/ragenius"
Set-DefaultProcessEnvironment "RAG_PGVECTOR_BOOTSTRAP" "true"
Set-DefaultProcessEnvironment "NODE_ENV" "development"
Set-DefaultProcessEnvironment "PORT" "3001"
Set-DefaultProcessEnvironment "RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED" "false"
Set-DefaultProcessEnvironment "AGENT_ASYNC_EXECUTION_ENABLED" "true"
Set-DefaultProcessEnvironment "CODEX_APP_SERVER_INTERACTIVE_ENABLED" "false"
Set-DefaultProcessEnvironment "OPENCLAW_GATEWAY_INTERACTIVE_ENABLED" "false"

if (-not (Test-Path -LiteralPath $demoDataPath)) {
  throw "Demo data directory not found: $demoDataPath"
}

$builderDb = Join-Path $runtimePath "builder\rag_app.db"
$installScript = Join-Path $PSScriptRoot "Install-DemoData.ps1"
if ($ForceInstall -or -not (Test-Path -LiteralPath $builderDb)) {
  if ((Test-Path -LiteralPath $runtimePath) -and -not $ForceInstall -and -not (Test-Path -LiteralPath $builderDb)) {
    throw "Runtime root exists but does not contain builder\rag_app.db. Run scripts\Reset-Demo.ps1 or pass -ForceInstall."
  }
  $installArgs = @{
    DemoDataDir = $demoDataPath
    RuntimeRoot = $runtimePath
  }
  if ($ForceInstall) {
    $installArgs["Force"] = $true
  }
  Write-Host "Installing demo seed data..."
  & $installScript @installArgs
}

$envValues = Set-DemoEnvironment -RuntimeRootPath $runtimePath
Write-Host "Runtime environment written to $(Join-Path $runtimePath "demo-runtime.env.json")"

if ($PrepareOnly) {
  Write-Host "Prepare-only mode complete. No services were launched."
  Write-Host "Builder DB: $($envValues.RAGENIUS_BUILDER_DB)"
  Write-Host "App state DB: $($envValues.RAGENIUS_APP_STATE_DB)"
  exit 0
}

Require-Command "node" "Install Node.js 20+ and ensure node.exe is on PATH."
Require-Command "npm" "Install npm with Node.js and ensure npm.cmd is on PATH."

Add-PythonPath -PathToAdd $repoRoot
Install-PythonDependenciesIfNeeded
Require-PythonModule -ModuleName "flask" -InstallHint "Run .\scripts\Install-PythonDependencies.ps1 from the repository root."
Require-PythonModule -ModuleName "uvicorn" -InstallHint "Run .\scripts\Install-PythonDependencies.ps1 from the repository root."

$logRoot = Join-Path (Split-Path -Parent $runtimePath) "demo-logs"

if (-not $SkipInfrastructure) {
  Require-Command "docker" "Install Docker Desktop and ensure docker.exe is on PATH, or rerun with -SkipInfrastructure if PostgreSQL is already running."
  Write-Host "Starting demo PostgreSQL/pgvector infrastructure..."
  Push-Location $repoRoot
  try {
    docker compose up -d postgres
  }
  finally {
    Pop-Location
  }
}

$processes = @()

if (-not $SkipExecutionSubsystem) {
  $executionDir = Join-Path $repoRoot "ragenius_execution_subsystem"
  Invoke-NpmInstallIfNeeded -WorkingDirectory $executionDir
  Push-Location $executionDir
  try {
    npx prisma generate
    npx prisma migrate deploy
  }
  finally {
    Pop-Location
  }
  $processes += Start-DemoProcess `
    -Name "ragenius_execution_subsystem" `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev") `
    -WorkingDirectory $executionDir `
    -LogRoot $logRoot
}

if (-not $SkipBuilder) {
  $builderDir = Join-Path $repoRoot "ragenius_builder"
  $builderAppDir = Join-Path $builderDir "flask_scaffold"
  $processes += Start-DemoProcess `
    -Name "ragenius_builder" `
    -FilePath "python" `
    -ArgumentList @("-m", "flask", "--app", "app.py", "run", "--host", "127.0.0.1", "--port", "8011") `
    -WorkingDirectory $builderAppDir `
    -LogRoot $logRoot
}

if (-not $SkipAppBackend) {
  $appDir = Join-Path $repoRoot "ragenius_app_skeleton"
  $processes += Start-DemoProcess `
    -Name "ragenius_app_skeleton_backend" `
    -FilePath "python" `
    -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $appDir `
    -LogRoot $logRoot
}

if (-not $SkipAppFrontend) {
  $frontendDir = Join-Path $repoRoot "ragenius_app_skeleton\frontend"
  Invoke-NpmInstallIfNeeded -WorkingDirectory $frontendDir
  $processes += Start-DemoProcess `
    -Name "ragenius_app_skeleton_frontend" `
    -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
    -WorkingDirectory $frontendDir `
    -LogRoot $logRoot
}

$processFile = Join-Path $runtimePath "demo-processes.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($processFile, ($processes | ConvertTo-Json -Depth 6), $utf8NoBom)

Write-Host "RAGenius demo services launched."
Write-Host "App frontend: http://127.0.0.1:5173"
Write-Host "App backend:   http://127.0.0.1:8000"
Write-Host "Builder:       http://127.0.0.1:8011"
Write-Host "Execution:     http://127.0.0.1:3001"
Write-Host "Logs:          $logRoot"
Write-Host "Stop with:     .\scripts\Stop-Demo.ps1"
