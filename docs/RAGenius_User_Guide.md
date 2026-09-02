# RAGenius User Guide

This guide helps evaluators and early contributors install RAGenius, run the official public demo, evaluate the main product capabilities, and understand the optional advanced agent integrations.

The recommended first-run path is the Windows Docker demo package. The source-checkout runner is available for contributors who want to inspect or modify the code.

## 1. What RAGenius is

RAGenius is a multi-application RAG and governed agent-execution framework. It separates end-user chat, application administration, retrieval, and external execution into explicit subsystem boundaries.

| Component | Responsibility |
| --- | --- |
| `ragenius_app_skeleton/` | End-user Application Runner: chat, sessions, citations, artifacts, and runtime UX |
| `ragenius_builder/` | Builder/admin control plane: applications, instructions, settings, documents, ingestion, search, and approved agent skills |
| `rag_subsystem/` | Protected ingestion, retrieval, embeddings, vector-store operations, and app-scoped RAG contracts |
| `ragenius_execution_subsystem/` | Policy-controlled tools, skills, Codex/OpenClaw provider interfaces, artifacts, and interactive execution |
| `shared/` | Shared modules used by multiple subsystems |
| `ragenius_app/` | Legacy/reference scaffold; not the active integrated runtime |

RAGenius is designed around application isolation. Every application has its own `app_id`, instructions, settings, documents, retrieval scope, and runtime behavior. Retrieval logic belongs in `rag_subsystem`; Builder owns admin workflows; Application Runner owns end-user workflows.

## 2. Recommended path

Use the Docker demo package for normal evaluation.

| Path | Recommended for | Notes |
| --- | --- | --- |
| Docker demo package | First-time users, evaluators, Windows x64, Windows ARM64 | Official public demo path. Uses GHCR images, immutable seed data, and Docker volumes. |
| Source-checkout runner | Contributors and maintainers | Runs from the repository checkout. Best on Windows x64. Requires Python, Node.js, npm, Docker, and dependency setup. |
| Native Windows ARM64 source-checkout | Not recommended for normal evaluation | Local embedding setup depends on Python packages such as PyTorch, which may not provide the required Windows ARM64 wheel. Use Docker on ARM64 Windows. |

The Docker demo uses `linux/amd64` RAGenius images. On Windows x64 this runs natively. On Windows ARM64, Docker Desktop runs the same images through emulation.

## 3. System requirements

For the Docker demo package:

- Windows 10 or Windows 11.
- Docker Desktop installed and running.
- Internet access.
- Browser such as Microsoft Edge or Chrome.
- Enough disk space for Docker images, PostgreSQL data, demo runtime data, and embedding models.
- At least one supported LLM API key for model-backed responses. The official demo settings use DeepSeek by default.

For local document ingestion with the realistic local embedding backend, run the included embedding setup script. The public Docker images include the embedding runtime dependencies, but they do not bundle the large embedding model files.

## 4. Docker demo package quick start

Download the demo zip from GitHub before running the commands below.

Recommended release path:

1. Open the RAGenius GitHub repository: `https://github.com/schao523/RAGenius-Application-Agent-Framework`.
2. Select **Releases** in the right sidebar, or open the repository's **Releases** page.
3. Open the latest release.
4. Under **Assets**, download the Windows demo package, for example:

   ```text
   RAGenius-Demo-<version>-Windows.zip
   ```

Development/latest-main artifact path:

1. Open the RAGenius GitHub repository: `https://github.com/schao523/RAGenius-Application-Agent-Framework`.
2. Select **Actions**.
3. Open the **GHCR Demo Package** workflow.
4. Open the latest successful run for the branch or tag you want to test.
5. In the run summary, find **Artifacts**.
6. Download:

   ```text
   RAGenius-Demo-main-Windows.zip
   ```

Use the Actions artifact when you want the latest package from `main`. Use the release asset when you want the stable published release package.

Open PowerShell in the folder where the zip was downloaded:

```powershell
Expand-Archive .\RAGenius-Demo-main-Windows.zip -DestinationPath .\RAGenius-Demo-Test -Force
cd .\RAGenius-Demo-Test\RAGenius-Demo
Copy-Item .env.template .env
notepad .env
```

Set at least one real LLM API key. For the default demo applications, use:

```env
DEEPSEEK_API_KEY=your-real-api-key
```

Then install, download embedding models, and start the demo:

```powershell
.\Install.ps1
.\Setup-Embeddings.ps1
.\Start.ps1
```

Open:

| UI/API | URL |
| --- | --- |
| Application Runner | `http://127.0.0.1:5173` |
| Builder | `http://127.0.0.1:8011` |
| Backend API app list | `http://127.0.0.1:8000/apps` |

## 5. What the Docker package contains

The Docker package contains:

- `compose.demo.yml`
- `Install.ps1`
- `Setup-Embeddings.ps1`
- `Start.ps1`
- `Stop.ps1`
- `Reset.ps1`
- `.env.template`
- immutable `demo-data/`
- Docker support files needed by the package
- RAG subsystem SQL initialization files

The package uses public GHCR images:

- `ghcr.io/schao523/ragenius-builder`
- `ghcr.io/schao523/ragenius-app-backend`
- `ghcr.io/schao523/ragenius-app-frontend`
- `ghcr.io/schao523/ragenius-execution-subsystem`

It also uses `pgvector/pgvector:pg16` for PostgreSQL with pgvector.

## 6. Runtime data model

The demo package separates immutable seed data from writable runtime state.

| Location | Role |
| --- | --- |
| `demo-data/` | Immutable public seed data included in the package. Do not edit this as runtime state. |
| Docker volume `ragenius_demo_runtime` | Writable Builder and Application Runner runtime state. |
| Docker volume `ragenius_demo_postgres` | Writable PostgreSQL/pgvector data. |
| `models/` | Downloaded embedding model files mounted read-only into Builder and app backend. |

`demo-data/` includes Builder metadata, file-backed instructions, source documents, and instruction-understanding snapshots for the official public demo applications.

When the demo starts, seed data is copied into writable runtime storage. Runtime paths are regenerated for the target machine/container. This matters because exported runtime records may contain absolute paths from the original development machine; the installer rewrites them for the new runtime location.

Use:

```powershell
.\Stop.ps1
```

to stop containers while keeping volumes.

Use:

```powershell
.\Reset.ps1
```

to delete demo volumes and recreate runtime state from `demo-data/`.

## 7. First validation checklist

After `.\Start.ps1`, verify the demo is working:

1. Open Builder at `http://127.0.0.1:8011`.
2. Confirm Builder shows the three official demo applications.
3. Open Application Runner at `http://127.0.0.1:5173`.
4. Confirm Application Runner shows the same three applications.
5. Open one application.
6. Confirm there is no warning saying:

   ```text
   This application has no compiled instruction-understanding model loaded.
   ```

7. In Builder, confirm the demo documents are visible.
8. Ingest documents for one application.
9. Start a chat in Application Runner.
10. Ask a question that should use the seeded documents.
11. Confirm the answer uses the selected application's behavior and, after ingestion, can cite retrieved material.

You can also check the backend API directly:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/apps" | ConvertTo-Json -Depth 5
```

Expected result: three applications.

## 8. Official public demo applications

The public demo seed currently includes three Builder-backed applications.

| Application | Documents | Demonstrates |
| --- | ---: | --- |
| 教會事工指令設計師  Church Ministry Prompt Designer | 9 | Prompt design workflow for church ministry content and structured prompt generation |
| Bible Tutor 酷聖經教師  4.0 | 13 | Guided Bible-study workflow, RAG, instruction-understanding behavior, and app-scoped resources |
| 酷 GPT 應用設計助理 Pro  GPT Application Design Assistant | 15 | GPT application design workflow using Builder-authored instructions and project-authored resources |

### Church Ministry Prompt Designer

Purpose: help users design high-quality structured prompts for ministry, teaching, discipleship, devotion, and church content workflows.

Suggested prompts:

```text
我想透過【主題或經文】幫助人更深認識神的真理，請幫我建立一個能支持這目的的最佳化提示（prompt）。
```

```text
請協助我生成一個能鼓勵與牧養【對象】、帶來屬靈更新與安慰的提示（prompt）。
```

What to evaluate:

- The application uses its own instruction model and starter workflow.
- The answer stays within the ministry prompt-design purpose.
- After ingestion, retrieval can use the seeded prompt-design resources.

### Bible Tutor 酷聖經教師 4.0

Purpose: guide users through Scripture study and theological reflection using structured Bible-study workflows.

Suggested prompts:

```text
我想查考一段經文
```

```text
我遇到一段難解的經文，想請你陪我一起探討它的意思。
```

What to evaluate:

- The application uses the Bible Tutor instruction-understanding snapshot.
- The conversation follows a guided study pattern rather than a generic chatbot pattern.
- After ingestion, retrieval can cite the seeded Bible-study documents.
- The Bible Tutor app does not leak behavior or resources from the other demo apps.

### GPT Application Design Assistant

Purpose: help users design GPT-style applications, including use-case clarification, system instructions, resources, interaction logic, and testing.

Suggested prompts:

```text
我想設計一個 GPT，請幫我先釐清「受眾」與「應用情境」，並協助定義合適的角色與目標。
```

```text
啟動「測試與優化支持模組」：請幫我按照 GPT 應用場景和 System Instructions，設計一份測試卡和評估標準。
```

What to evaluate:

- The application behaves like an application-design assistant.
- It uses its own Builder-authored instruction model.
- After ingestion, it can retrieve from the seeded design resources.

## 9. Evaluating core RAGenius capabilities

Use this sequence for a structured evaluation.

### Multi-application isolation

1. Open Application Runner.
2. Select one demo app.
3. Ask a question specific to that app.
4. Switch to another demo app.
5. Ask a similar question.

Expected behavior: each app uses its own name, purpose, starter questions, instruction model, documents, and retrieval scope.

### Builder administration

Open Builder and review:

- application list;
- application instructions;
- application settings;
- document inventory;
- document ingestion status;
- search/admin tools.

Expected behavior: Builder exposes admin workflows. End-user chat remains in Application Runner.

### Instruction-understanding snapshots

The public demo includes compiled instruction-understanding snapshots. These snapshots allow Application Runner to load the intended app behavior without asking the evaluator to recompile instructions first.

Expected behavior: Application Runner should not show a missing compiled instruction model warning for the seeded demo apps.

### Document ingestion and retrieval

Before ingestion, documents are present but not indexed into pgvector. In Builder, ingest documents for the app you want to test.

Expected behavior:

- documents move through ingestion status;
- chunks are created;
- retrieval can use the ingested content;
- retrieval remains scoped to the selected `app_id`.

### LLM-backed chat

The demo requires internet and an API key for model-backed responses.

Expected behavior:

- without a real API key, the system can start but cannot produce normal model-backed answers;
- with `DEEPSEEK_API_KEY` configured, the official demo applications can call the configured DeepSeek models.

### Execution subsystem

The Docker demo includes the execution subsystem service. The default public demo configuration keeps advanced external agent integrations disabled or restricted.

Use this API/status path for basic connectivity checks:

```powershell
docker compose -f compose.demo.yml --env-file .env ps
```

Expected behavior: the execution container is running and reachable by Builder/Application Runner.

## 10. Embeddings and ingestion setup

The Docker demo defaults to local embeddings:

```env
RAG_EMBEDDING_BACKEND=local
RAG_EMBEDDING_MODEL_PATH_BGE_LARGE_ZH=/models/bge-large-zh
RAG_EMBEDDING_MODEL_PATH_E5_LARGE=/models/e5-large
```

Run this once after extracting the Docker demo package:

```powershell
.\Setup-Embeddings.ps1
```

The script downloads:

- `BAAI/bge-large-zh-v1.5` to `models/bge-large-zh`
- `intfloat/e5-large-v2` to `models/e5-large`

After the models are downloaded, they can be reused by later demo starts from the same extracted package folder.

If ingestion fails with:

```text
Ingestion produced zero chunks. Check embedding runtime/model availability.
```

then check that:

- `.\Setup-Embeddings.ps1` completed successfully;
- `models\bge-large-zh` exists;
- `models\e5-large` exists;
- `RAG_EMBEDDING_BACKEND=local` remains set in `.env`;
- Builder and app backend were restarted after the model files were installed.

## 11. Common Docker demo commands

From the extracted package folder:

```powershell
cd C:\Temp\RAGenius-Demo-Test\RAGenius-Demo
```

Install/pull images:

```powershell
.\Install.ps1
```

Download embedding models:

```powershell
.\Setup-Embeddings.ps1
```

Start:

```powershell
.\Start.ps1
```

Stop while keeping data:

```powershell
.\Stop.ps1
```

Reset demo data and volumes:

```powershell
.\Reset.ps1
```

Check container status:

```powershell
docker compose -f compose.demo.yml --env-file .env ps
```

Check backend app list:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/apps" | ConvertTo-Json -Depth 5
```

Check backend logs:

```powershell
docker compose -f compose.demo.yml --env-file .env logs --tail=120 app-backend
```

Check Builder logs:

```powershell
docker compose -f compose.demo.yml --env-file .env logs --tail=120 builder
```

Check execution subsystem logs:

```powershell
docker compose -f compose.demo.yml --env-file .env logs --tail=120 execution
```

## 12. Docker troubleshooting

### Docker Desktop is not running

Symptom:

```text
failed to connect to the docker API
```

Fix:

1. Start Docker Desktop.
2. Wait until Docker reports that it is running.
3. Retry:

   ```powershell
   .\Install.ps1
   ```

### GHCR pull is denied

Symptom:

```text
error from registry: denied
```

Cause: the GHCR package may not be public, or the image/tag does not exist.

Fix:

1. Confirm the GitHub Actions image workflow completed successfully.
2. Confirm the four GHCR packages exist.
3. In GitHub Packages, make each package public if GitHub created it as private.
4. Retry:

   ```powershell
   .\Install.ps1
   ```

### Windows ARM64 manifest error

Symptom:

```text
no matching manifest for linux/arm64/v8
```

The current public RAGenius images are `linux/amd64`. The package should contain:

```env
RAGENIUS_DOCKER_PLATFORM=linux/amd64
```

Check:

```powershell
Select-String -Path .\.env.template -Pattern "RAGENIUS_DOCKER_PLATFORM"
Select-String -Path .\compose.demo.yml -Pattern "platform"
```

If those lines are missing, download a newer demo package.

Temporary workaround for an old package:

```powershell
$env:DOCKER_DEFAULT_PLATFORM = "linux/amd64"
.\Install.ps1
```

### Port conflict

Default host ports:

| Service | Port |
| --- | --- |
| Application Runner frontend | `5173` |
| Application Runner backend | `8000` |
| Builder | `8011` |
| Execution subsystem | `3001` |
| PostgreSQL | `55433` |

Check a port:

```powershell
netstat -ano | findstr ":55433"
```

If a port is already allocated, stop the conflicting service or edit `.env` to use a different port before starting the demo.

### Application Runner opens but applications do not load

Check backend API:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/apps" | ConvertTo-Json -Depth 5
```

Check containers:

```powershell
docker compose -f compose.demo.yml --env-file .env ps
```

Check backend logs:

```powershell
docker compose -f compose.demo.yml --env-file .env logs --tail=120 app-backend
```

Interpretation:

- If `/apps` returns three apps, hard refresh the browser with `Ctrl+F5`.
- If `/apps` fails, inspect `app-backend` logs.
- If the backend container is not running, restart the demo.
- If the runtime volume is stale, run `.\Reset.ps1`.

### Missing compiled instruction model warning

Symptom:

```text
This application has no compiled instruction-understanding model loaded.
```

Fix:

1. Confirm the package is current.
2. Reset the writable demo volumes:

   ```powershell
   .\Reset.ps1
   .\Start.ps1
   ```

3. If the warning remains, check app backend logs:

   ```powershell
   docker compose -f compose.demo.yml --env-file .env logs --tail=120 app-backend
   ```

### Documents appear ready but are not ingested

In the public demo, documents may be present in Builder but still need ingestion into the current pgvector database.

Use Builder to ingest the documents for the selected app. If ingestion fails with zero chunks, run `.\Setup-Embeddings.ps1`, restart the demo, and retry ingestion.

### Stale Docker volumes

If behavior does not match the current package, reset volumes:

```powershell
.\Reset.ps1
.\Start.ps1
```

This deletes writable demo state and recreates it from immutable `demo-data/`.

## 13. Source-checkout runner for contributors

Use the source-checkout runner if you want to inspect, modify, or contribute to the RAGenius code.

For normal evaluation, use the Docker demo package.

### Prerequisites

- Windows PowerShell.
- Git.
- Python 3.11 or newer.
- Node.js 20 or newer.
- npm.
- Docker Desktop.
- Internet access.
- At least one supported LLM API key.

Native Windows ARM64 source-checkout local embeddings are not recommended because required packages such as PyTorch may not be available for the active ARM64 Python environment. Use the Docker demo package on ARM64 Windows.

### Clone or update the repository

Use one of the following paths depending on whether the PC already has a local clone.

#### New PC or no existing clone

Open PowerShell in the folder where you keep GitHub repositories, then clone the repository:

```powershell
cd C:\Users\schao\GitHub
git clone https://github.com/schao523/RAGenius-Application-Agent-Framework.git
cd RAGenius-Application-Agent-Framework
```

Verify that the source-checkout runner files are present:

```powershell
Test-Path .env.template
Test-Path .\demo-data\apps.json
Test-Path .\scripts\Start-Demo.ps1
Test-Path .\scripts\Setup-Embeddings.ps1
```

Each command should print `True`.

#### Existing clone that may not be up to date

Open PowerShell in the existing repository folder:

```powershell
cd C:\Users\schao\GitHub\RAGenius-Application-Agent-Framework
git branch --show-current
git status --short
```

If the current branch is not `main`, switch to `main`:

```powershell
git switch main
```

If `git status --short` shows no local changes, update the local `main` branch:

```powershell
git fetch origin
git pull --ff-only origin main
```

If `git status --short` shows local changes, do not overwrite them. For local work that should be kept but can be temporarily moved aside, stash it first:

```powershell
git stash push -u -m "local work before updating RAGenius"
git fetch origin
git pull --ff-only origin main
git stash pop
```

If the local changes are important source changes, commit them on a separate branch before updating `main`:

```powershell
git switch -c my-local-work
git add .
git commit -m "Save local work before updating RAGenius"
git switch main
git fetch origin
git pull --ff-only origin main
```

Verify the runner exists:

```powershell
Test-Path .env.template
Test-Path .\demo-data\apps.json
Test-Path .\scripts\Start-Demo.ps1
Test-Path .\scripts\Setup-Embeddings.ps1
```

Each command should print `True`.

### Run the source-checkout demo

From the repository root:

```powershell
Copy-Item .env.template .env
notepad .env
```

Set:

```env
DEEPSEEK_API_KEY=your-real-api-key
```

Install Python dependencies into the active Python environment:

```powershell
python -c "import sys; print(sys.executable)"
.\scripts\Install-PythonDependencies.ps1
```

Install embedding dependencies and models:

```powershell
.\scripts\Setup-Embeddings.ps1
```

This step only needs to be run again when dependencies are missing, the Python environment changes, or the embedding model files are deleted.

Prepare the seeded runtime once before full startup if you want to validate the seed install separately:

```powershell
.\scripts\Start-Demo.ps1 -PrepareOnly -ForceInstall
```

Start the demo:

```powershell
.\scripts\Start-Demo.ps1
```

Open:

| UI/API | URL |
| --- | --- |
| Application Runner | `http://127.0.0.1:5173` |
| Builder | `http://127.0.0.1:8011` |
| Backend API app list | `http://127.0.0.1:8000/apps` |

Validate the backend app list:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/apps" | ConvertTo-Json -Depth 5
```

Expected result: three applications.

Stop:

```powershell
.\scripts\Stop-Demo.ps1
```

Reset:

```powershell
.\scripts\Reset-Demo.ps1
```

For more detail, see `docs/source-checkout-demo-runner-guide.md`.

## 14. Advanced: Codex and OpenClaw agent integrations

The Docker demo includes the RAGenius execution subsystem and the configuration surface for Codex/OpenClaw agent integrations. The default public Docker image does not bundle Codex CLI, OpenClaw CLI, WSL, an OpenClaw gateway, or authenticated host sessions.

Treat these integrations as advanced, opt-in setup.

| Capability | Default Docker demo status |
| --- | --- |
| Execution subsystem service | Included |
| Agent execution API/schema | Included |
| Async agent execution flag | Enabled by default |
| Codex CLI agent mode | Code exists, disabled by default, runtime not bundled |
| Codex interactive app-server mode | Code/config exists, disabled by default, runtime not bundled |
| OpenClaw CLI mode | Code exists, disabled by default, runtime not bundled |
| OpenClaw gateway interactive mode | Code/config exists, disabled by default, requires external gateway and token |

Default public-demo settings:

```env
AGENT_ASYNC_EXECUTION_ENABLED=true
CODEX_CLI_ENABLED=false
CODEX_APP_SERVER_INTERACTIVE_ENABLED=false
CODEX_MCP_ELICITATION_ENABLED=false
CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED=false
CODEX_INTERACTIVE_USER_ACTION_ENABLED=false
OPENCLAW_GATEWAY_INTERACTIVE_ENABLED=false
OPENCLAW_GATEWAY_CHAT_LEVEL_ENABLED=false
```

### Codex CLI mode requirements

To use Codex CLI mode, the execution subsystem environment must provide:

- `codex` executable;
- authenticated Codex account/session;
- a writable run workspace;
- appropriate sandbox and permission policy;
- any required plugin/skill/tool access.

Representative settings:

```env
CODEX_CLI_ENABLED=true
CODEX_CLI_COMMAND=codex
CODEX_RUN_ROOT=/runtime/execution/codex-runs
CODEX_CLI_SANDBOX_MODE=workspace-write
```

In the stock Docker package, enabling these variables alone is not sufficient unless the execution container can actually run `codex` and access the required authentication state.

### Codex interactive mode requirements

Codex interactive mode requires a reachable Codex app-server/runtime and deliberate permission configuration.

Representative settings:

```env
CODEX_APP_SERVER_INTERACTIVE_ENABLED=true
CODEX_MCP_ELICITATION_ENABLED=true
CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED=true
CODEX_INTERACTIVE_USER_ACTION_ENABLED=true
CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON=[]
CODEX_MANAGED_AUTH_TARGETS_JSON=[]
```

Enable one capability at a time and validate with a read-only test before allowing write-capable operations.

### OpenClaw CLI mode requirements

OpenClaw CLI mode requires:

- OpenClaw installed and runnable;
- a configured OpenClaw agent;
- a workspace available to the execution subsystem;
- compatible WSL/workspace assumptions if using the existing local OpenClaw path.

Representative settings:

```env
OPENCLAW_CLI_ENABLED=true
OPENCLAW_CLI_COMMAND=openclaw
OPENCLAW_AGENT_ID=main
OPENCLAW_WORKSPACE_ROOT=/home/openclaw/.openclaw/workspace
OPENCLAW_WSL_DISTRO=OpenClawGateway
```

The stock Docker image does not include WSL or OpenClaw CLI.

### OpenClaw gateway interactive mode requirements

OpenClaw gateway mode requires:

- running OpenClaw gateway;
- gateway URL reachable from the execution subsystem container;
- approval credential/token;
- supported gateway version.

If the gateway runs on the Windows host and the execution subsystem runs in Docker, set the gateway URL in `.env` to use `host.docker.internal`. From inside a Docker container, `127.0.0.1` means the container itself, not the Windows host. `host.docker.internal` is Docker Desktop's built-in hostname for reaching services running on the Windows host.

Example `.env` settings:

```env
OPENCLAW_GATEWAY_INTERACTIVE_ENABLED=true
OPENCLAW_GATEWAY_CHAT_LEVEL_ENABLED=true
OPENCLAW_GATEWAY_URL=ws://host.docker.internal:18789
OPENCLAW_GATEWAY_APPROVAL_CREDENTIAL_ENV=OPENCLAW_GATEWAY_APPROVAL_TOKEN
OPENCLAW_GATEWAY_APPROVAL_TOKEN=your-token-here
OPENCLAW_GATEWAY_SUPPORTED_VERSIONS=2026.6.8
```

### Advanced integration safety rules

- First confirm the base Docker demo works.
- Enable only one integration at a time.
- Start with read-only tests.
- Do not enable broad host access for untrusted demos.
- Keep credentials in ignored `.env` files only.
- Do not commit API keys, gateway tokens, auth state, generated logs, or private provider output.

## 15. Contributor onboarding

Contributors should start by reading:

- `README.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `docs/source-checkout-demo-runner-guide.md`
- `docs/open-source-release-manual-gate-checklist.md`

Core contribution boundaries:

- Do not duplicate retrieval logic outside `rag_subsystem`.
- Do not put admin workflows into `ragenius_app_skeleton`.
- Do not put end-user chat flows into `ragenius_builder`.
- Do not add new integrated runtime behavior to the legacy `ragenius_app`.
- Always preserve `app_id` isolation.
- Treat external lookups as read-only unless an explicit write workflow is implemented and authorized.

Useful test commands:

Run the demo packaging and seed lifecycle tests when changing the Docker demo package, `demo-data/`, seed export/install scripts, or demo start/stop/reset scripts. These tests check that the package includes the expected files, seed data can be installed into a writable runtime, document statuses are initialized correctly, instruction snapshots are copied, and lifecycle scripts keep their expected contract.

```powershell
python -m pytest tests\test_ghcr_demo_package.py tests\test_demo_seed_exporter.py tests\test_demo_seed_installer.py tests\test_demo_lifecycle_scripts.py -q
```

Run the RAG subsystem tests when changing ingestion, chunking, retrieval, embeddings, vector-store behavior, or app-scoped retrieval contracts. These tests protect the rule that retrieval logic stays in `rag_subsystem` and remains isolated by `app_id`.

```powershell
python -m pytest tests\test_rag_subsystem.py
```

Run the execution subsystem tests when changing governed tool execution, agent requests, confirmation policy, artifact handling, Codex/OpenClaw provider interfaces, Prisma schema usage, or interactive execution behavior. `npm ci` installs the exact Node dependencies, `npm test` runs the subsystem test suite, `npm run typecheck` validates TypeScript types, and `npm run lint` checks code style/static rules.

```powershell
Push-Location ragenius_execution_subsystem
npm ci
npm test
npm run typecheck
npm run lint
Pop-Location
```

Build the Docker demo package locally:

```powershell
.\scripts\Build-DemoPackage.ps1 -Version local-test
```

The generated zip is written under `dist/` unless another output path is supplied.

## 16. Reporting issues

When reporting a bug, include:

- Windows version and CPU architecture: x64 or ARM64;
- Docker Desktop version;
- whether you used Docker demo package or source-checkout runner;
- exact command that failed;
- relevant logs;
- whether `.env` was created from `.env.template`;
- whether `.\Setup-Embeddings.ps1` completed;
- whether `Invoke-RestMethod "http://127.0.0.1:8000/apps"` returns three applications.

Useful diagnostic commands:

```powershell
docker compose -f compose.demo.yml --env-file .env ps
docker compose -f compose.demo.yml --env-file .env logs --tail=120 app-backend
docker compose -f compose.demo.yml --env-file .env logs --tail=120 builder
docker compose -f compose.demo.yml --env-file .env logs --tail=120 execution
Invoke-RestMethod "http://127.0.0.1:8000/apps" | ConvertTo-Json -Depth 5
```

For security issues, follow `SECURITY.md`. Do not post credentials, private documents, auth tokens, or sensitive provider output in public issues.

## 17. Feature support summary

| Feature | Default Docker demo | Requires setup | Advanced/custom |
| --- | --- | --- | --- |
| Builder opens | Yes | No | No |
| Application Runner opens | Yes | No | No |
| Three public demo apps load | Yes | No | No |
| Instruction-understanding snapshots load | Yes | No | No |
| LLM-backed responses | No | API key and internet | No |
| Document ingestion | No | Embedding model download | No |
| Retrieval/citations | No | Successful ingestion | No |
| pgvector vector store | Yes | Docker Desktop | No |
| Execution subsystem service | Yes | No | No |
| Codex CLI agent execution | No | Codex runtime/auth | Often custom image or host integration |
| Codex interactive execution | No | Codex app-server/runtime | Yes |
| OpenClaw CLI execution | No | OpenClaw runtime/workspace | Yes |
| OpenClaw gateway interaction | No | Gateway URL/token | Yes |
