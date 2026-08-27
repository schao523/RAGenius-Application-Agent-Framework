# RAGenius Application Agent Framework

RAGenius is a multi-application RAG and governed Agent-execution framework. It
separates end-user chat, administrative publishing, retrieval, and external
execution into explicit subsystem boundaries.

## Architecture

| Component | Responsibility |
| --- | --- |
| `rag_subsystem/` | Protected ingestion, retrieval, embeddings, and vector-store integration |
| `ragenius_app_skeleton/` | Active Builder-backed end-user chat, artifacts, and execution UX |
| `ragenius_builder/` | Administrative control plane for apps, instructions, documents, and approved Agent Skills |
| `ragenius_execution_subsystem/` | Policy-controlled tools, skills, Codex/OpenClaw providers, artifacts, and interactive execution |
| `ragenius_app/` | Legacy/reference scaffold; it is not part of the integrated runtime |

Every data and execution flow must remain scoped by `app_id`; session artifacts
are additionally session-scoped. Retrieval logic belongs only in
`rag_subsystem`.

## Current Platform Support

The integrated developer startup path is tested on Windows with PowerShell,
Python 3.10+, Node.js 20+, npm, PostgreSQL, and optional WSL for OpenClaw.
Individual Python and Node test suites may run elsewhere, but Linux and macOS
are not yet supported as complete three-subsystem runtime environments.

Codex CLI, OpenClaw, NotebookLM, Gmail, browser control, and other external
providers are optional local integrations. They are not bundled and may have
their own licenses, accounts, usage charges, or security requirements.

## Quick Start

1. Install Python 3.10+, Node.js 20+, npm, PostgreSQL, and Git.
2. Create and activate a virtual environment.
3. Install the Python dependencies.
4. Copy each tracked environment template to its ignored `.env` file.
5. Start the execution subsystem, Builder, and app skeleton in separate
   PowerShell terminals.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install -r ragenius_app_skeleton\backend\requirements.txt
python -m pip install -r ragenius_builder\requirements.txt

Copy-Item ragenius_execution_subsystem\.env.example ragenius_execution_subsystem\.env
Copy-Item ragenius_builder\.env.example ragenius_builder\.env
Copy-Item ragenius_app_skeleton\.env.example ragenius_app_skeleton\.env
```

Generate separate random values for the app execution credential, Builder
execution credential, and Builder administrator credential. Never commit the
resulting `.env` files. The service credentials and scopes are described in
[`ragenius_execution_subsystem/docs/service-authentication-guide.md`](ragenius_execution_subsystem/docs/service-authentication-guide.md).

Start each subsystem:

```powershell
powershell -ExecutionPolicy Bypass -File .\ragenius_execution_subsystem\start-ragenius-execution-subsystem.ps1
powershell -ExecutionPolicy Bypass -File .\ragenius_builder\start-ragenius-builder.ps1
powershell -ExecutionPolicy Bypass -File .\ragenius_app_skeleton\start-ragenius-app-skeleton.ps1
```

The default local endpoints are Builder `http://127.0.0.1:8011`, app backend
`http://127.0.0.1:8000`, app frontend `http://127.0.0.1:5173`, and execution
subsystem `http://127.0.0.1:3001`.

## Safe Defaults

External writes, managed authentication handoff, generic user action, and
provider-specific interactive capabilities are disabled unless an administrator
explicitly configures them. Do not enable broad allowlists for convenience.
The controlled Gmail opt-in and rollback procedure is documented in
[`ragenius_execution_subsystem/docs/codex-gmail-mcp-live-test-plan.md`](ragenius_execution_subsystem/docs/codex-gmail-mcp-live-test-plan.md).

## Tests

```powershell
python -m pytest tests\test_rag_subsystem.py
python -m pytest --basetemp=tmp_sqlite_tests\app-backend ragenius_app_skeleton\backend\tests
$builderTests = Get-ChildItem ragenius_builder\flask_scaffold\tests -File -Filter "test_*.py" | ForEach-Object FullName
python -m pytest --basetemp=tmp_sqlite_tests\builder @builderTests

Push-Location ragenius_app_skeleton\frontend
npm ci
npm test
npm run build
Pop-Location

Push-Location ragenius_execution_subsystem
npm ci
npx prisma generate
npm test
npm run typecheck
npm run lint
Pop-Location
```

Live provider tests are excluded from the default automated gate and require
explicit credentials, local providers, and authorization.

## Contributing And Security

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing subsystem contracts.
Report vulnerabilities privately using [`SECURITY.md`](SECURITY.md); do not put
credentials or sensitive provider output in a public issue.

RAGenius is licensed under the [MIT License](LICENSE).
