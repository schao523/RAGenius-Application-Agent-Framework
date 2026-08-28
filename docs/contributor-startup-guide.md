# Contributor Startup Guide

This guide starts the integrated RAGenius development environment on Windows.
The supported integrated path consists of:

- PostgreSQL 16 with pgvector
- `ragenius_execution_subsystem`
- `ragenius_builder`
- `ragenius_app_skeleton` backend and frontend

External providers such as Codex, OpenClaw, Gmail, NotebookLM, and browser
control are optional and are not required for basic startup.

## 1. Install Prerequisites

Install the following software:

- Git
- Python 3.10 or newer
- Node.js 20 or newer, including npm
- Docker Desktop or another Docker-compatible runtime with Compose

Confirm that each command is available in a new PowerShell terminal:

```powershell
git --version
python --version
node --version
npm --version
docker version
docker compose version
```

`docker version` must report both client and server information. If it reports
that it cannot connect to the engine, start Docker Desktop and wait for it to
finish initializing. RAGenius does not launch Docker Desktop automatically.

## 2. Clone the Repository

```powershell
git clone https://github.com/schao523/RAGenius-Application-Agent-Framework.git
Set-Location .\RAGenius-Application-Agent-Framework
```

Confirm that the current directory is the repository root:

```powershell
git rev-parse --show-toplevel
Get-ChildItem README.md, ragenius_execution_subsystem, ragenius_builder, ragenius_app_skeleton
```

All remaining commands in this guide start from the repository root unless a
different working directory is shown.

## 3. Start the Databases

Start the canonical PostgreSQL/pgvector service:

```powershell
docker compose up -d --wait postgres
docker compose ps
```

The root Compose configuration:

- exposes PostgreSQL on `127.0.0.1:5433`;
- creates the `ragenius` database for RAG and pgvector data;
- creates the `ragenius_execution` database for governed execution state;
- installs the `vector` extension and initializes `rag_chunks`; and
- persists both databases in a named Docker volume.

Verify the initialization:

```powershell
docker compose exec postgres psql -U ragenius -d ragenius -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
docker compose exec postgres psql -U ragenius -d ragenius -c "SELECT to_regclass('public.rag_chunks');"
docker compose exec postgres psql -U ragenius -d ragenius_execution -c "SELECT current_database();"
```

Expected results are a pgvector version, `rag_chunks`, and
`ragenius_execution`.

### Port 5433 Is Already In Use

Identify the existing listener before stopping anything:

```powershell
Get-NetTCPConnection -LocalPort 5433 -State Listen -ErrorAction SilentlyContinue
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Either stop the conflicting service or use another host port:

```powershell
$env:RAGENIUS_POSTGRES_PORT = "55433"
docker compose up -d --wait postgres
```

If an alternate port is used, replace `5433` with that port in all database
URLs created in step 5. Legacy subsystem-specific Compose volumes are not
automatically adopted by the root Compose stack; migrate important data before
retiring an older database.

## 4. Install Dependencies

Create one repository virtual environment and install the Python dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python -m pip install -r .\ragenius_app_skeleton\backend\requirements.txt
python -m pip install -r .\ragenius_builder\requirements.txt
python -m pip check
```

Install the locked Node.js dependencies:

```powershell
npm --prefix .\ragenius_execution_subsystem ci
npm --prefix .\ragenius_app_skeleton\frontend ci
```

If PowerShell blocks virtual-environment activation, review and apply the
current-user policy instead of using an unrestricted machine-wide policy:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## 5. Create Local Configuration

Copy the tracked templates to ignored local files:

```powershell
Copy-Item .\ragenius_execution_subsystem\.env.example .\ragenius_execution_subsystem\.env
Copy-Item .\ragenius_builder\.env.example .\ragenius_builder\.env
Copy-Item .\ragenius_app_skeleton\.env.example .\ragenius_app_skeleton\.env
git status --short
```

The `.env` files should not appear in Git status. Never commit credentials or
local environment files.

With the default Compose port, verify these values:

```dotenv
# ragenius_execution_subsystem/.env
DATABASE_URL="postgresql://ragenius:ragenius@localhost:5433/ragenius_execution?schema=public"

# ragenius_builder/.env and ragenius_app_skeleton/.env
RAG_VECTOR_STORE_BACKEND=pgvector
RAG_VECTOR_STORE_DSN=postgresql://ragenius:ragenius@localhost:5433/ragenius
RAG_PGVECTOR_BOOTSTRAP=true
```

The tracked password is for an isolated local development database only. Use
proper secret management and distinct credentials for a shared or production
deployment.

Basic startup does not require external-provider credentials. Keep the safe
defaults disabled until the corresponding provider has been deliberately
configured and tested.

## 6. Start the Three Subsystems

Open three PowerShell terminals at the repository root. Activate the same
virtual environment in each terminal.

### Terminal 1: Execution Subsystem

```powershell
.\.venv\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File .\ragenius_execution_subsystem\start-ragenius-execution-subsystem.ps1
```

The script checks database reachability, generates the Prisma client, applies
pending migrations to `ragenius_execution`, and starts port `3001`.

### Terminal 2: Builder

```powershell
.\.venv\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File .\ragenius_builder\start-ragenius-builder.ps1
```

The script checks RAG database reachability and starts Builder on port `8011`.

### Terminal 3: App Skeleton

```powershell
.\.venv\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File .\ragenius_app_skeleton\start-ragenius-app-skeleton.ps1
```

The script checks RAG database reachability, starts the app backend on port
`8000`, and starts the frontend on port `5173`.

## 7. Verify the Runtime

Run these checks from another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:3001/healthz
Invoke-WebRequest http://127.0.0.1:8011 -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:8000/docs -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing | Select-Object StatusCode
```

Open the user interfaces:

- RAGenius app: `http://127.0.0.1:5173`
- Builder: `http://127.0.0.1:8011`
- App API documentation: `http://127.0.0.1:8000/docs`
- Execution health: `http://127.0.0.1:3001/healthz`

## 8. Stop the Environment

Press `Ctrl+C` in each subsystem terminal. Then stop PostgreSQL without
deleting its data:

```powershell
docker compose stop postgres
```

Restart it later with:

```powershell
docker compose up -d --wait postgres
```

Do not use `docker compose down -v` unless an intentional clean reset is
required. The `-v` option permanently deletes the local RAG and execution
database volume.

## Troubleshooting

### Database Preflight Fails

Check Docker and the configured port:

```powershell
docker version
docker compose ps
docker compose logs --tail 100 postgres
Test-NetConnection 127.0.0.1 -Port 5433
```

Confirm that every `.env` URL uses the same port and credentials as the root
Compose service.

### A Runtime Port Is Already In Use

```powershell
Get-NetTCPConnection -State Listen |
    Where-Object LocalPort -In 3001,8011,8000,5173,5433 |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

Identify the owning process before stopping it. Do not terminate unrelated
services or another contributor's runtime.

### Prisma Reports a Locked Windows DLL

Stop every running execution-subsystem Node.js process before regenerating the
Prisma client. A running process can hold
`query_engine-windows.dll.node` open and cause an `EPERM` rename failure.

### Basic Startup Works but an External Provider Does Not

Basic runtime health does not configure Codex, OpenClaw, Gmail, NotebookLM,
browser control, or other external providers. Configure those integrations
separately and preserve the repository's safe default policies.
