# Open-Source Release Manual Gate Checklist

Date prepared and last reviewed: 2026-08-28

Use this checklist after automated CI passes and before creating or announcing
the first public release. It validates the contributor experience, repository
security controls, clean installation path, and safe runtime defaults.

## Release Candidate Baseline

- Repository: `schao523/RAGenius-Application-Agent-Framework`
- Release-candidate branch: `main`
- Release-candidate commit: record immediately before testing
- Passing GitHub Actions run: record the run URL immediately before testing
- Required CI checks: `python`, `app-frontend`, `execution-subsystem`
- Expected secret-scanning alerts: `0`
- Expected Dependabot alerts: `0`
- Expected high or critical npm audit findings: `0`
- Expected tracked files under `ragenius_execution_subsystem/storage`: `0`

Do not copy a historical commit or CI run into the evidence record. Immediately
before the clean-PC test, obtain the exact `main` commit with:

```powershell
git switch main
git pull --ff-only
git rev-parse HEAD
git status --short
```

Open the repository's Actions page and record the successful workflow run for
that exact commit. If `main` advances afterward, restart the release-candidate
gate against the newer commit.

The dependency, alert, and storage expectations above must be reproduced from
the committed release candidate. A clean-PC tester must report any regression
and must not run `npm audit fix` in the release-candidate checkout.

## Maintainer Handoff Before Gate 1

The maintainer must complete these checks after the release pull request is
merged and before asking the non-maintainer tester to begin:

1. Confirm the required GitHub Actions checks passed on the final `main`
   commit.
2. Open the repository Security tab and confirm secret-scanning and Dependabot
   have no unresolved release-blocking alerts.
3. Run the following commands in a clean checkout of that commit:

```powershell
git status --short
git ls-files "ragenius_execution_subsystem/storage/**"
git ls-files "*.env"
```

Expected result: all three commands print nothing. Provide the tester with the
exact commit SHA and successful Actions run URL. Do not provide credentials,
maintainer cookies, ignored `.env` files, or local database volumes.

## Questions Answered

### Should the test use a different PC?

Prefer a different Windows PC. It provides the strongest evidence that the
repository does not depend on the maintainer machine's ignored files,
credentials, databases, caches, installed skills, or provider sessions.

If a second PC is unavailable, use all of the following:

- A separate non-maintainer GitHub account.
- An incognito window or separate browser profile.
- A fresh clone in a new directory.
- Newly created local `.env` files; do not copy the maintainer `.env` files.

### What should happen after signing in as the non-maintainer?

First open the public repository:

`https://github.com/schao523/RAGenius-Application-Agent-Framework`

Confirm the account can read the repository but has no write or administrator
access. Start all issue, security-reporting, fork, and pull-request checks from
that repository page.

### What is the repository root?

The repository root is the directory containing `README.md`, `.git`,
`ragenius_execution_subsystem`, `ragenius_builder`, and
`ragenius_app_skeleton`.

After cloning, locate it with:

```powershell
git rev-parse --show-toplevel
```

Change to that path before running root-relative commands:

```powershell
Set-Location (git rev-parse --show-toplevel)
```

### Do the startup scripts download dependencies?

Only partially.

| Startup script | Dependency behavior |
| --- | --- |
| Execution subsystem | Runs `npm install`, generates Prisma, and applies Prisma migrations |
| App skeleton | Runs frontend `npm install` only when `frontend/node_modules` is absent |
| Builder | Does not install Python dependencies |

The scripts do not install Git, Python, Node.js, npm, Docker, or the Python
packages, and they do not start Docker Desktop. Install those prerequisites
and start the Docker engine before starting the system.

## Gate 1: Non-Maintainer Repository Access

Perform this gate while signed in to the non-maintainer GitHub account.

### Step 1. Open the repository

Open:

`https://github.com/schao523/RAGenius-Application-Agent-Framework`

Confirm:

- The repository is public and readable.
- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `LICENSE` are visible.
- The account does not see maintainer-only repository settings.

Record `PASS` only if all three conditions hold.

### Step 2. Verify issue templates

Open:

`https://github.com/schao523/RAGenius-Application-Agent-Framework/issues/new/choose`

Confirm the configured issue choices are displayed and their forms open.
Do not submit a fake issue. Close the page after checking the forms.

Expected result: issue templates are visible to the non-maintainer.

### Step 3. Verify private vulnerability reporting

Open:

`https://github.com/schao523/RAGenius-Application-Agent-Framework/security/advisories`

Confirm a `Report a vulnerability` action is available and opens a private
reporting form. Do not submit a test vulnerability report.

Expected result: a researcher can start a private report without opening a
public issue.

### Step 4. Verify the fork workflow

Click `Fork` from the repository page and create a fork under the
non-maintainer account.

In the fork:

1. Create a branch named `manual-gate-probe`.
2. Add a harmless file named `docs/manual-gate-probe.md`.
3. Put only `Manual release gate probe. No product change.` in the file.
4. Commit the file to `manual-gate-probe`, not to the fork's `main`.
5. Open a pull request from the fork branch to the upstream `main` branch.

Expected result: the pull request can be opened, but the contributor cannot
push directly to upstream `main`.

### Step 5. Verify required checks and review protection

On the test pull request, confirm these checks appear:

- `python`
- `app-frontend`
- `execution-subsystem`

Confirm merging is blocked until the checks pass and one maintainer approval
is present. The maintainer may add a review comment to verify that unresolved
conversations block merging, then resolve it.

Do not merge the probe. Close the pull request after recording the result.
Delete the fork and branch later if they are no longer useful.

Expected result: contributor pull requests require current CI, one approval,
and resolved review conversations.

## Gate 2: Clean PC Prerequisites

Perform this gate on the clean test PC. Use PowerShell unless a command says
otherwise.

### Step 6. Confirm required software

Open a new PowerShell terminal and check whether Windows Package Manager is
available:

```powershell
winget --version
```

If `winget` is unavailable, install or update `App Installer` from the
Microsoft Store. Alternatively, download each prerequisite from its official
project website. Do not use third-party download mirrors.

Install missing prerequisites from an Administrator PowerShell. The following
package identifiers are the standard Windows Package Manager identifiers at
the time this guide was prepared:

```powershell
winget install --id Git.Git --exact --source winget
winget install --id Python.Python.3.12 --exact --source winget
winget install --id OpenJS.NodeJS.LTS --exact --source winget
winget install --id Docker.DockerDesktop --exact --source winget
```

The `winget` catalog can change. If an identifier is not found, search before
substituting a package:

```powershell
winget search Git
winget search Python
winget search Node.js
winget search Docker Desktop
```

Review the publisher and source before installing a search result. Prefer the
official Git, Python Software Foundation, OpenJS Foundation, and Docker
packages. Docker Desktop is the tested Windows runtime; another
Docker-compatible runtime is acceptable if it supports Compose.

Launch Docker Desktop after installation and wait until its engine reports
that it is running. RAGenius scripts do not launch the Docker application.

Close and reopen PowerShell after installation so updated `PATH` values are
loaded. Then run:

```powershell
git --version
python --version
py --version
node --version
npm --version
docker version
docker compose version
```

Required baseline:

- Git
- Python 3.10 or newer
- Node.js 20 or newer
- npm
- Docker Engine connectivity
- Docker Compose

If any command is unavailable, install that prerequisite before continuing.
The RAGenius startup scripts do not install it.

Expected version examples:

```text
git version 2.x
Python 3.10 or newer
Node.js v20 or newer
npm 10 or newer
Docker Engine and Compose versions supported by the installed runtime
```

The npm version bundled with a supported Node.js release is sufficient. Do
not install an unrelated global npm version unless the bundled npm is broken.

If PowerShell prevents virtual-environment activation scripts, allow locally
created scripts for the current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

This changes the current user's PowerShell policy. Review the prompt before
accepting it; do not use `Unrestricted` as a workaround.

### Step 7. Clone and enter the repository root

Run:

```powershell
git clone https://github.com/schao523/RAGenius-Application-Agent-Framework.git
Set-Location .\RAGenius-Application-Agent-Framework
$repoRoot = git rev-parse --show-toplevel
$repoRoot
Set-Location $repoRoot
```

Confirm the current directory contains the expected files:

```powershell
Get-ChildItem README.md, ragenius_execution_subsystem, ragenius_builder, ragenius_app_skeleton
```

Expected result: all four paths exist.

### Step 8. Confirm the checked-out revision

Run:

```powershell
git branch --show-current
git log -1 --oneline
git status --short
git ls-files "ragenius_execution_subsystem/storage/**"
```

Expected result:

- Branch is `main`.
- The commit is the release candidate being tested.
- `git status --short` is empty before local configuration begins.
- The `git ls-files` command prints nothing; runtime and test artifacts are not
  version-controlled.

## Gate 3: PostgreSQL and pgvector

The canonical release-test path uses the root `compose.yml`. It runs one
PostgreSQL 16/pgvector server on `127.0.0.1:5433` and creates two separate
databases: `ragenius` and `ragenius_execution`.

### Step 9. Start the canonical database service

Confirm that Docker is responsive, then start PostgreSQL from the repository
root:

```powershell
docker version
docker compose up -d --wait postgres
```

If `docker version` shows client information but reports that it cannot connect
to the engine, open Docker Desktop and wait for startup to complete. Do not
continue until the command reports both client and server information.

Expected result: Compose reports the `postgres` service as healthy.

### Step 10. Inspect service state and logs

Run:

```powershell
docker compose ps
docker compose logs --tail 100 postgres
Test-NetConnection 127.0.0.1 -Port 5433
```

Expected results:

- The `postgres` service is `running` and `healthy`.
- The logs contain no initialization error.
- `TcpTestSucceeded` is `True`.

### Step 11. Verify both databases and pgvector

Use the PostgreSQL client inside the container; no host `psql` installation is
required:

```powershell
docker compose exec postgres psql -U ragenius -d ragenius -c "SELECT current_database();"
docker compose exec postgres psql -U ragenius -d ragenius_execution -c "SELECT current_database();"
docker compose exec postgres psql -U ragenius -d ragenius -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
docker compose exec postgres psql -U ragenius -d ragenius -c "SELECT to_regclass('public.rag_chunks');"
```

Expected results:

- The first two commands identify `ragenius` and `ragenius_execution`.
- The vector query returns an installed version.
- The final query returns `rag_chunks`.

### Step 12. Understand persistent and destructive operations

The named volume preserves data across `docker compose stop` and
`docker compose down`. Do not run the following destructive reset during the
manual gate:

```powershell
docker compose down -v
```

That command permanently deletes the local RAG and execution databases. It is
appropriate only for an intentional clean reset with no data to preserve.

Native PostgreSQL 16 with pgvector is an advanced alternative. If it is used,
the tester must independently create both databases, apply
`rag_subsystem/sql/init_pgvector.sql` to `ragenius`, expose the selected port,
and update every corresponding ignored `.env` file consistently. The Docker
path remains the required clean-PC release gate.

## Gate 4: Dependencies and Local Configuration

### Step 13. Create and activate a Python virtual environment

From the repository root, run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python -m pip install -r ragenius_app_skeleton\backend\requirements.txt
python -m pip install -r ragenius_builder\requirements.txt
python -m pip check
```

Expected result: all commands exit successfully. Keep this virtual environment
active in the Builder and app terminals during startup.

The Python commands install these dependency groups:

| Command | Purpose |
| --- | --- |
| `pip install -e ".[dev]"` | Root RAG subsystem and repository test dependencies |
| App backend requirements | FastAPI, Uvicorn, database, and app runtime dependencies |
| Builder requirements | Flask and Builder runtime dependencies |
| `pip check` | Detects incompatible or missing installed Python packages |

Confirm that the virtual environment, rather than a global Python install, is
active:

```powershell
python -c "import sys; print(sys.executable)"
python -c "import fastapi, flask, uvicorn; print('Python runtime imports: OK')"
```

Expected result: `sys.executable` points inside
`<REPOSITORY_ROOT>\.venv\Scripts`, and the import check prints `OK`.

### Step 13A. Preinstall locked Node.js dependencies

The startup scripts can install Node.js packages, but preinstalling them makes
dependency failures easier to diagnose before multiple services are running.

Install the execution-subsystem lockfile exactly:

```powershell
Push-Location ragenius_execution_subsystem
npm ci
npm audit --audit-level=high
Pop-Location
```

Install the app-frontend lockfile exactly:

```powershell
Push-Location ragenius_app_skeleton\frontend
npm ci
npm audit --audit-level=high
Pop-Location
```

Use `npm ci` for clean verification because it installs exactly what each
committed `package-lock.json` specifies. Do not run `npm audit fix` during the
manual gate: that changes the dependency tree and means the test PC is no
longer testing the committed release candidate.

Expected result: both `npm ci` commands succeed and neither audit reports a
high or critical vulnerability. The execution dependency tree must resolve
`prisma@6.19.3`, `@prisma/client@6.19.3`, and the package override
`deepmerge-ts@8.0.2`. Verify it without changing the lockfile:

```powershell
npm --prefix ragenius_execution_subsystem ls prisma @prisma/client deepmerge-ts --all
```

Record the exact audit output and mark the dependency gate `FAIL` if the audit
or dependency-tree command fails. Do not silently rewrite the lockfile on the
test PC.

### Step 14. Create ignored `.env` files

Run:

```powershell
Copy-Item ragenius_execution_subsystem\.env.example ragenius_execution_subsystem\.env
Copy-Item ragenius_builder\.env.example ragenius_builder\.env
Copy-Item ragenius_app_skeleton\.env.example ragenius_app_skeleton\.env
```

Confirm Git ignores them:

```powershell
git status --short
```

Expected result: the three `.env` files do not appear in Git status.

### Step 15. Verify canonical database URLs

The copied templates already target the root Compose service. Verify these
values in `ragenius_execution_subsystem/.env`:

```dotenv
DATABASE_URL="postgresql://ragenius:ragenius@localhost:5433/ragenius_execution?schema=public"
```

Verify these values in both `ragenius_app_skeleton/.env` and
`ragenius_builder/.env`:

```dotenv
RAG_VECTOR_STORE_BACKEND=pgvector
RAG_VECTOR_STORE_DSN=postgresql://ragenius:ragenius@localhost:5433/ragenius
RAG_PGVECTOR_BOOTSTRAP=true
```

The tracked password is only for an isolated local development database. If
`RAGENIUS_POSTGRES_PASSWORD` was set before the first Compose initialization,
percent-encode that password where necessary and update all three ignored
`.env` files consistently.

### Step 16. Preserve safe Agent defaults

In `ragenius_execution_subsystem/.env`, verify these values:

```dotenv
CODEX_CLI_ENABLED="false"
CODEX_APP_SERVER_INTERACTIVE_ENABLED="false"
OPENCLAW_GATEWAY_INTERACTIVE_ENABLED="false"
OPENCLAW_GATEWAY_CHAT_LEVEL_ENABLED="false"
CODEX_MCP_ELICITATION_ENABLED="false"
CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED="false"
CODEX_INTERACTIVE_USER_ACTION_ENABLED="false"
CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON="[]"
CODEX_MANAGED_AUTH_TARGETS_JSON="[]"
```

Do not add Codex, OpenClaw, Gmail, NotebookLM, browser, MCP, or other external
provider credentials during the safe-default smoke test.

### Step 17. Configure service-token placeholders safely

The example execution configuration leaves service authentication disabled.
For this safe-default startup test, retain:

```dotenv
RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED="false"
```

The Builder and app example tokens may remain local placeholders during this
specific smoke test because the execution subsystem is not enforcing service
authentication. Do not commit them. A production deployment should enable
service authentication and use distinct random credentials with scoped access.

### Step 17A. Validate Prisma and database preparation

After the execution `.env` file contains the correct `DATABASE_URL`, validate
the Prisma schema, generate the client, and apply execution migrations:

```powershell
Push-Location ragenius_execution_subsystem
npx prisma validate
npx prisma generate
npx prisma migrate deploy
Pop-Location
```

Expected results:

- Prisma reports the schema is valid.
- Client generation succeeds.
- Migration deployment reports success or that no pending migrations exist.

The execution startup script repeats dependency synchronization, Prisma client
generation, and migration deployment. Running these commands here is an
intentional preflight, not an additional runtime requirement.

### Dependency troubleshooting rules

Use these checks before deleting package directories or changing versions:

```powershell
Get-Command python, node, npm, git
python -m pip check
npm --prefix ragenius_execution_subsystem ls --depth=0
npm --prefix ragenius_app_skeleton\frontend ls --depth=0
```

If `npm ci` reports that the manifest and lockfile disagree, stop and record
the release blocker. Do not replace `npm ci` with `npm install` merely to make
the clean-PC gate pass.

If a Python package fails to build, record the complete package name, version,
Python version, and error. Confirm the package supports the selected Python
version before installing compilers or pinning a different dependency.

## Gate 5: Start the Three Subsystems

Open three PowerShell terminals. In each terminal, change to the repository
root. Activate `.venv` in the Builder and app terminals.

### Step 18. Start the execution subsystem

Terminal 1:

```powershell
Set-Location <REPOSITORY_ROOT>
powershell -ExecutionPolicy Bypass -File .\ragenius_execution_subsystem\start-ragenius-execution-subsystem.ps1
```

This script automatically:

- Verifies that the execution database endpoint is reachable.
- Runs `npm install` for the execution subsystem.
- Generates the Prisma client.
- Applies pending Prisma migrations.
- Starts the service on port `3001`.

Confirm the startup output includes equivalent values:

```text
Execution database endpoint is reachable at localhost:5433.
Interactive Agent transports: Codex=False OpenClaw=False OpenClawChatLevel=False
Codex interactive capabilities: McpElicitation=False AuthHandoff=False UserAction=False AuthHosts=0 ManagedAuthTargets=0
```

Failure conditions include an unexpected enabled capability, nonempty
authentication allowlist, migration failure, or unavailable port.

### Step 19. Start Builder

Terminal 2:

```powershell
Set-Location <REPOSITORY_ROOT>
.\.venv\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File .\ragenius_builder\start-ragenius-builder.ps1
```

The Builder script does not install Python dependencies. Step 13 must already
have completed. Confirm it reports that the RAG database endpoint is reachable
at `localhost:5433`. Expected endpoint: `http://127.0.0.1:8011`.

### Step 20. Start the app skeleton

Terminal 3:

```powershell
Set-Location <REPOSITORY_ROOT>
.\.venv\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File .\ragenius_app_skeleton\start-ragenius-app-skeleton.ps1
```

The app script installs frontend npm dependencies only when `node_modules` is
absent. Confirm it reports that the RAG database endpoint is reachable at
`localhost:5433`. It starts the backend on port `8000` and frontend on port
`5173`.

## Gate 6: Runtime Smoke Test

### Step 21. Verify endpoints

From a fourth PowerShell terminal, run:

```powershell
Invoke-RestMethod http://127.0.0.1:3001/healthz
Invoke-WebRequest http://127.0.0.1:8011 -UseBasicParsing
Invoke-RestMethod http://127.0.0.1:8000/apps
Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing
```

Expected results:

- Execution health returns `status` equal to `ok`.
- Builder returns HTTP `200`.
- App backend returns an application list.
- App frontend returns HTTP `200`.

### Step 22. Verify the browser UX

Open `http://127.0.0.1:5173`.

Confirm:

- The application shell loads without a JavaScript error.
- Existing seeded applications can be listed or selected.
- Session navigation, chat area, Artifact Library, and Execution Composer open.
- No browser, login, authentication handoff, MCP request, or external action
  starts automatically.
- Disabled Codex and OpenClaw providers are unavailable or fail with a
  controlled provider-disabled response.
- No request remains indefinitely in `running` or
  `waiting_for_interaction`.

A normal chat response may require an independently configured language model.
Lack of a generated answer is not a safe-default failure if the UI and local
APIs remain healthy and no unsafe provider action occurs.

### Step 23. Stop the services

Use `Ctrl+C` in each subsystem terminal. Confirm ports are released:

```powershell
Test-NetConnection 127.0.0.1 -Port 3001
Test-NetConnection 127.0.0.1 -Port 8011
Test-NetConnection 127.0.0.1 -Port 8000
Test-NetConnection 127.0.0.1 -Port 5173
```

After shutdown, `TcpTestSucceeded` should be `False` for each port. If a port
remains active, identify the owning process before terminating anything:

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 3001,8011,8000,5173 | Select-Object LocalPort,OwningProcess
```

Stop PostgreSQL without deleting its named volume:

```powershell
docker compose stop postgres
```

## Gate 7: Evidence and Release Decision

### Step 24. Record results

Save the following record outside the repository or in the release tracking
issue:

```text
Release candidate commit:
GitHub Actions run:
Test date and timezone:
Tester:
Test PC and Windows version:

Repository readable by non-maintainer: PASS/FAIL
Issue templates available: PASS/FAIL
Private vulnerability reporting available: PASS/FAIL
Fork and pull request creation: PASS/FAIL
Required CI checks enforced: PASS/FAIL
One approval enforced: PASS/FAIL
Conversation resolution enforced: PASS/FAIL

Clean clone and prerequisite installation: PASS/FAIL
Python dependency check: PASS/FAIL
Execution npm install and audit: PASS/FAIL
Frontend npm install and audit: PASS/FAIL
Docker database bootstrap: PASS/FAIL
Both PostgreSQL databases present: PASS/FAIL
pgvector extension and RAG schema present: PASS/FAIL
Execution subsystem startup: PASS/FAIL
Builder startup: PASS/FAIL
App backend and frontend startup: PASS/FAIL
Safe Agent defaults observed: PASS/FAIL
Browser UX smoke: PASS/FAIL

Unexpected external action observed: YES/NO
Open blocker:
Notes:
```

Any `FAIL`, unexpected external action, exposed credential, or unresolved
security alert blocks the release.

### Step 25. Create the first tag only after every gate passes

Create the release tag from the maintainer PC, not the non-maintainer test
account. First synchronize and verify the exact release commit:

```powershell
git switch main
git pull --ff-only
git status --short
git log -1 --oneline
```

Choose the release version deliberately. For example, if `v0.1.0` is approved:

```powershell
git tag -a v0.1.0 -m "RAGenius v0.1.0"
git push origin v0.1.0
```

Do not run the tag commands merely because they appear in this guide. Confirm
the version, evidence record, current commit, CI status, and release decision
first.

## Completion Criteria

The manual gate is complete only when:

- A genuine non-maintainer can use the public contribution and private
  vulnerability-reporting paths.
- Protected `main` behavior is confirmed from a fork-based pull request.
- A clean Windows PC can install prerequisites and start all three active
  subsystems using only tracked documentation and newly created ignored
  configuration.
- Optional Agent providers and interactive external capabilities remain
  disabled during the safe-default smoke test.
- No credentials are committed or pasted into public issues, pull requests,
  logs, screenshots, or release notes.
- The release candidate commit passes all required GitHub Actions checks.
