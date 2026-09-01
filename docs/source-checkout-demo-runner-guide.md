# RAGenius Source-Checkout Demo Runner Developer Guide

This guide explains how the source-checkout demo runner works, how to run it from a cloned repository, and how to refresh the public demo seed after the RAGenius source data changes.

The source-checkout runner is intended for developers, maintainers, and early contributors. It is not a finished end-user installer. The user must first have an up-to-date repository source checkout on the Windows PC where the demo will run.

## What this runner provides

The demo runner starts the integrated RAGenius system from the repository checkout:

- `ragenius_builder` on `http://127.0.0.1:8011`
- `ragenius_app_skeleton` backend on `http://127.0.0.1:8000`
- `ragenius_app_skeleton` frontend on `http://127.0.0.1:5173`
- `ragenius_execution_subsystem` on `http://127.0.0.1:3001`
- PostgreSQL/pgvector through `compose.yml`

It also installs the public demo seed from `demo-data/` into a writable local runtime under `runtime/demo/`.

The important design rule is:

- `demo-data/` is immutable public seed data committed with the repository.
- `runtime/demo/` is writable generated runtime data created on the target machine.

The application should read and mutate `runtime/demo/`, not `demo-data/`.

## Included public demo applications

The official public demo seed currently includes three Builder-backed applications:

| Application | Purpose |
| --- | --- |
| Church Ministry Prompt Designer | Prompt design workflow demo using church-ministry authored documents. |
| Bible Tutor 4.0 | RAG and guided Bible-study workflow demo using public-domain Bible resources. |
| GPT Application Design Assistant | Application-design workflow demo using project-authored design assistant documents. |

The seed contains Builder metadata, file-backed instructions, document files, and instruction-understanding snapshots for these applications.

## Prerequisites

Install these before running the source-checkout demo:

- Windows PowerShell.
- Python 3.11 or newer available as `python`.
- Node.js 20 or newer available as `node`.
- npm available as `npm`.
- Docker Desktop available as `docker`.
- Internet access for:
  - pulling Docker images;
  - npm dependency installation if `node_modules` is absent;
  - Prisma package execution;
  - LLM API calls.
- At least one supported LLM API key.

DeepSeek is the current default provider used by the official demo app settings, so `DEEPSEEK_API_KEY` is the expected first key.

## Get or update the source checkout

The source-checkout runner lives in the repository. If the user's local repository is old, it may not contain `demo-data/`, `.env.template`, or the `scripts\Start-Demo.ps1` runner yet.

### Case 1: The user does not have the repository yet

Clone the repository:

```powershell
git clone https://github.com/<owner>/<repo>.git
cd <repo>
```

Replace `<owner>/<repo>` with the actual GitHub repository path.

If the user does not want to use Git, download the repository ZIP from GitHub:

1. Open the GitHub repository page.
2. Select **Code > Download ZIP**.
3. Extract the ZIP.
4. Open PowerShell in the extracted repository folder.

Then continue with [First-time setup](#first-time-setup).

### Case 2: The user already has the repository, but local `main` is not up to date

Open PowerShell in the existing repository folder:

```powershell
cd C:\path\to\Codex-RAGenius-System
```

Check the current branch and local changes:

```powershell
git branch --show-current
git status --short
```

If the current branch is not `main`, switch to `main`:

```powershell
git switch main
```

If `git status --short` shows no local changes, update `main`:

```powershell
git fetch origin
git pull --ff-only origin main
```

After the pull, verify the source-checkout demo runner files exist:

```powershell
Test-Path .env.template
Test-Path .\demo-data\apps.json
Test-Path .\scripts\Start-Demo.ps1
Test-Path .\scripts\Reset-Demo.ps1
Test-Path .\scripts\Stop-Demo.ps1
```

Each command should print `True`.

If local changes exist, do not run `git pull` until those changes are handled. Use one of these safe options:

```powershell
git status --short
git stash push -u -m "local work before updating RAGenius demo runner"
git fetch origin
git pull --ff-only origin main
```

After confirming the updated demo runner works, restore the stashed local work if needed:

```powershell
git stash list
git stash pop
```

If `git stash pop` reports conflicts, resolve them manually before continuing.

If the local checkout has important uncommitted work that should not be stashed, commit it on a separate branch first:

```powershell
git switch -c my-local-work
git add .
git commit -m "Save local work before updating demo runner"
git switch main
git fetch origin
git pull --ff-only origin main
```

Then continue with [First-time setup](#first-time-setup).

## First-time setup

From the repository root:

```powershell
Copy-Item .env.template .env
notepad .env
```

Set at least:

```powershell
DEEPSEEK_API_KEY=your-real-api-key
```

Then start the demo:

```powershell
.\scripts\Start-Demo.ps1
```

When startup completes, open:

```text
http://127.0.0.1:5173
```

Use the Builder UI at:

```text
http://127.0.0.1:8011
```

## What `Start-Demo.ps1` does

`scripts/Start-Demo.ps1` performs these actions:

1. Loads environment values from:
   - root `.env`;
   - `ragenius_app_skeleton\.env`, if present;
   - `ragenius_builder\.env`, if present;
   - `ragenius_execution_subsystem\.env`, if present.
2. Applies safe demo defaults for local ports, PostgreSQL, pgvector, and execution subsystem URLs.
3. Installs demo seed data from `demo-data/` into `runtime/demo/` if the runtime does not already exist.
4. Writes the effective demo runtime path map to:

   ```text
   runtime/demo/demo-runtime.env.json
   ```

5. Starts Docker PostgreSQL/pgvector infrastructure through `compose.yml`.
6. Installs npm dependencies when needed, unless `-SkipDependencyInstall` is used.
7. Runs Prisma generate/migrate for the execution subsystem.
8. Starts the Builder, app backend, app frontend, and execution subsystem.
9. Records started process IDs in:

   ```text
   runtime/demo/demo-processes.json
   ```

`Stop-Demo.ps1` uses this PID file to stop the demo services later.

## Runtime data layout

After installation, the generated runtime has this shape:

```text
runtime/demo/
  builder/
    rag_app.db
    instructions/{app_id}/instructions.md
    storage/uploads/{app_id}/{document_id}_{filename}
  app/.state/
    runtime_state.db
    session_uploads/
    instruction_understanding_snapshots/{app_id}/understanding.json
  demo-runtime.env.json
  demo-processes.json
```

The installer rewrites document `file_path` values in `runtime/demo/builder/rag_app.db` to absolute paths on the current PC. This is required because the original development-machine paths are not portable.

The committed `demo-data/` files are never used as writable runtime files.

## Common commands

Prepare runtime data without launching services:

```powershell
.\scripts\Start-Demo.ps1 -PrepareOnly
```

Install Python dependencies into the active `python` environment:

```powershell
.\scripts\Install-PythonDependencies.ps1
```

Force reinstall demo seed data into `runtime/demo/`:

```powershell
.\scripts\Start-Demo.ps1 -ForceInstall
```

Reset runtime data without starting services:

```powershell
.\scripts\Reset-Demo.ps1
```

Stop services started by the demo runner:

```powershell
.\scripts\Stop-Demo.ps1
```

`Stop-Demo.ps1` stops recorded demo PIDs and also checks known demo ports `3001`, `8000`, `8011`, and `5173` for leftover listeners. Use `-SkipPortCleanup` only when you intentionally want to leave a process on one of those ports running.

Run with a custom runtime directory:

```powershell
.\scripts\Start-Demo.ps1 -RuntimeRoot .\runtime\my-demo
```

Prepare a custom runtime directory only:

```powershell
.\scripts\Start-Demo.ps1 -RuntimeRoot .\runtime\my-demo -PrepareOnly
```

Skip Docker infrastructure when PostgreSQL/pgvector is already running:

```powershell
.\scripts\Start-Demo.ps1 -SkipInfrastructure
```

Skip dependency installation when dependencies are already installed:

```powershell
.\scripts\Start-Demo.ps1 -SkipDependencyInstall
```

Start only selected services. For example, start infrastructure, execution subsystem, and Builder, but skip the app frontend/backend:

```powershell
.\scripts\Start-Demo.ps1 -SkipAppBackend -SkipAppFrontend
```

Start only the runtime preparation step and avoid all services:

```powershell
.\scripts\Start-Demo.ps1 -PrepareOnly
```

## Seed export and install commands

The demo seed is produced by:

```powershell
.\scripts\Export-DemoSeed.ps1 -Force
```

This exports the current canonical runtime data into `demo-data/`.

The runtime install step is:

```powershell
.\scripts\Install-DemoData.ps1 -DemoDataDir .\demo-data -RuntimeRoot .\runtime\demo -Force
```

`Start-Demo.ps1` calls the installer automatically when `runtime/demo/builder/rag_app.db` does not exist or when `-ForceInstall` is supplied.

## When to regenerate `demo-data/`

Regenerate `demo-data/` when any of these source runtime assets change:

- official demo app metadata in the Builder database;
- official demo app instructions;
- official demo app document set;
- official demo app instruction-understanding snapshots;
- official demo app settings or starter questions.

The canonical source inputs are:

```text
ragenius_builder/flask_scaffold/rag_app.db
ragenius_builder/flask_scaffold/instructions/{app_id}/instructions.md
ragenius_builder/flask_scaffold/storage/uploads/{app_id}/...
ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/{app_id}/understanding.json
```

Do not manually edit generated `demo-data/` unless the change is metadata-only and intentional. Prefer updating the real Builder/runtime data and rerunning:

```powershell
.\scripts\Export-DemoSeed.ps1 -Force
```

Then verify:

```powershell
python -m pytest tests/test_demo_seed_exporter.py tests/test_demo_seed_installer.py tests/test_demo_lifecycle_scripts.py -q
.\scripts\Start-Demo.ps1 -PrepareOnly -ForceInstall
```

## Contributor workflow example

Use this flow when reviewing whether a source checkout can run the public demo:

```powershell
git clone https://github.com/<owner>/<repo>.git
cd <repo>
Copy-Item .env.template .env
notepad .env
.\scripts\Start-Demo.ps1 -PrepareOnly
python -m pytest tests/test_demo_seed_exporter.py tests/test_demo_seed_installer.py tests/test_demo_lifecycle_scripts.py -q
.\scripts\Start-Demo.ps1
```

If the demo starts successfully, open the app frontend:

```text
http://127.0.0.1:5173
```

Then select one of the seeded applications and run a normal query that requires an LLM response.

## Maintainer release workflow example

Use this flow before publishing a release that updates the public demo:

```powershell
.\scripts\Export-DemoSeed.ps1 -Force
.\scripts\Start-Demo.ps1 -PrepareOnly -ForceInstall
python -m pytest tests/test_demo_seed_exporter.py tests/test_demo_seed_installer.py tests/test_demo_lifecycle_scripts.py -q
rg -n "D:\\GitHub|C:\\Users|file_path" demo-data scripts tests .env.template
rg -n "(api[_-]?key|secret|token|password)\s*[:=]\s*['""][^'""]{8,}|sk-[A-Za-z0-9]|ghp_[A-Za-z0-9]|github_pat_|AIza[0-9A-Za-z_-]{20,}|xox[baprs]-" demo-data scripts tests .env.template
git status --short
```

Expected results:

- tests pass;
- no absolute development-machine paths are found in `demo-data/`;
- no obvious committed secrets are found;
- `demo-data/` changes are intentional and reviewable.

## Troubleshooting

### `.env` is missing

Create it from the template:

```powershell
Copy-Item .env.template .env
```

Then add the LLM key.

### LLM responses fail

Check:

- internet access is available;
- `DEEPSEEK_API_KEY` or another supported key is set in `.env`;
- the selected application settings use the provider you configured;
- the API key has sufficient account quota.

### Docker fails to start PostgreSQL

Check Docker Desktop is running:

```powershell
docker ps
```

Then retry:

```powershell
docker compose up -d postgres
.\scripts\Start-Demo.ps1
```

If you already run PostgreSQL/pgvector separately, use:

```powershell
.\scripts\Start-Demo.ps1 -SkipInfrastructure
```

Make sure `DATABASE_URL` and `RAG_VECTOR_STORE_DSN` in `.env` point to the correct database endpoints.

### Demo data exists but looks stale

Reset the writable runtime:

```powershell
.\scripts\Reset-Demo.ps1
```

Or force reinstall during startup:

```powershell
.\scripts\Start-Demo.ps1 -ForceInstall
```

### Ports are already in use

The default ports are:

| Service | Port |
| --- | --- |
| app frontend | `5173` |
| app backend | `8000` |
| Builder | `8011` |
| execution subsystem | `3001` |
| PostgreSQL on host | `5433` |

Stop the conflicting process or change the relevant component startup command before running the demo.

### Backend or Builder does not start

The runner starts services as background processes. Logs are written under:

```text
runtime/demo/demo-logs/
```

Check the backend and Builder logs first:

```powershell
Get-Content .\runtime\demo\demo-logs\ragenius_app_skeleton_backend.err.log
Get-Content .\runtime\demo\demo-logs\ragenius_builder.err.log
```

If the error says a Python module such as `flask` or `uvicorn` is missing, install Python dependencies into the same active Python environment used by the runner:

```powershell
python -c "import sys; print(sys.executable)"
.\scripts\Install-PythonDependencies.ps1
python -c "import flask; print('Flask OK')"
python -c "import uvicorn; print('uvicorn OK')"
```

Then restart:

```powershell
.\scripts\Stop-Demo.ps1
.\scripts\Start-Demo.ps1
```

### Stop script says no process file exists

This means `Stop-Demo.ps1` did not find:

```text
runtime/demo/demo-processes.json
```

Either the demo was not started by `Start-Demo.ps1`, it was started with a different `-RuntimeRoot`, or the processes already exited.

## Source-checkout runner versus future packaged demo

The source-checkout runner is useful for contributors and maintainers because it runs directly from the repository and reflects local code changes.

A future packaged demo should have a smaller user surface:

```powershell
Expand-Archive RAGenius-Demo-1.0.0-Windows.zip
cd RAGenius-Demo
Copy-Item .env.template .env
notepad .env
.\Install.ps1
```

That package should likely use public GHCR Docker images plus immutable seed data and writable Docker volumes. The source-checkout runner created here is still valuable because it provides the tested seed export/install lifecycle that the packaged demo can reuse.
