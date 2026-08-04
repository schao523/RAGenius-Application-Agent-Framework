$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'docker-compose.pgvector.yml'
$sqlFile = Join-Path $root 'sql\init_pgvector.sql'

Write-Host 'Starting pgvector container...'
docker compose -f $composeFile up -d

Write-Host 'Waiting for container health...'
for ($i=0; $i -lt 60; $i++) {
  $status = docker inspect -f "{{.State.Health.Status}}" ragenius-pgvector 2>$null
  if ($status -eq 'healthy') { break }
  Start-Sleep -Seconds 2
}

$status = docker inspect -f "{{.State.Health.Status}}" ragenius-pgvector
if ($status -ne 'healthy') {
  throw "Container did not become healthy. Current status: $status"
}

Write-Host 'Applying schema...'
Get-Content $sqlFile | docker exec -i ragenius-pgvector psql -U ragenius -d ragenius -f -

Write-Host 'Verifying...'
docker exec -i ragenius-pgvector psql -U ragenius -d ragenius -c "SELECT extname FROM pg_extension WHERE extname='vector';"
docker exec -i ragenius-pgvector psql -U ragenius -d ragenius -c "SELECT to_regclass('public.rag_chunks') AS rag_chunks;"

Write-Host 'Done.'
Write-Host 'DSN: postgresql://ragenius:ragenius@localhost:5433/ragenius'
