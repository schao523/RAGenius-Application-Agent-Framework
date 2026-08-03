# RAGenius Execution Subsystem

`ragenius_execution_subsystem` is the controlled execution backend of the RAGenius system.

It accepts structured execution requests from `ragenius_app`, validates them, loads registered skills, executes internal workflow steps through the unified `ToolEngine`, enforces permissions, redacts sensitive log data, and returns normalized execution results.

## What This Runtime Does

- Validates structured `execute_skill` requests
- Executes one sample skill: `video_director_skill`
- Executes Builder-managed published skills through Builder fallback
- Executes a real HTTP-backed `research_paper_search_tool`
- Executes Phase 1 Builder-normalized safe contracts for file inspection, retrieval, metadata search, and artifact persistence
- Executes Phase 3 review-required contracts for approved adapters and discovered MCP-backed tools
- Resolves tools through an in-memory registry
- Supports `local`, `rag_adapter`, `api`, `mcp`, and `adapter` tool providers
- Enforces permission decisions before every tool call
- Supports `dry_run` and `pending_confirmation`
- Supports confirmation resume by persisted execution id
- Persists execution records, stored requests, and summary logs through the execution store seam
- Supports execution lookup and execution log lookup APIs
- Returns a standardized result envelope
- Exposes MVP REST routes for executions, skills, tools, and MCP discovery
- Provides a Prisma schema aligned to the documented persistence contract

## What This MVP Does Not Do Yet

- It does not perform LLM-first reasoning or planning.
- It does not generate final conversational answers.
- It does not perform RAG ingestion or mutation.
- It does not provide broad real tool coverage beyond the current research provider path.
- It does not talk to a real MCP server transport yet; Phase 3 MCP execution still uses a controlled mock provider seam behind discovered tool ids.
- It does not yet persist detailed workflow-step and tool-call history to the database.
- It does not implement queued background workers yet.

## Local Setup

### Prerequisites

- Node.js 20+
- npm
- PostgreSQL if you want to validate DB connectivity beyond schema validation

### Install

```bash
npm install
```

### Environment

Copy `.env.example` to `.env` and set values as needed.

Use a dedicated execution database. Do **not** point `DATABASE_URL` at the shared `ragenius` database used by `rag_subsystem` / `ragenius_app`.

Required variables:

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/ragenius_execution?schema=public"
NODE_ENV="development"
PORT="3000"
LOG_LEVEL="info"
BUILDER_BASE_URL=""
FILESYSTEM_ALLOWED_ROOTS=""
FILESYSTEM_MUTATION_ROOTS=""
FILESYSTEM_MAX_READ_BYTES="65536"
FILESYSTEM_MAX_WRITE_BYTES="65536"
FILESYSTEM_MAX_PATCH_BYTES="32768"
ARTIFACT_STORAGE_ROOT="storage/artifacts"
ADAPTERS_JSON="[]"
```

### Phase 1 Safe Core Tools

The execution subsystem now supports these Builder-normalized safe tools:

- `read_file`
- `list_files`
- `retrieve_documents`
- `search_metadata`
- `save_artifact`
- `load_artifact`

Recommended local development values:

```env
FILESYSTEM_ALLOWED_ROOTS="D:/GitHub/Codex-RAGenius-System/docs,D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/instructions"
FILESYSTEM_MAX_READ_BYTES="65536"
ARTIFACT_STORAGE_ROOT="storage/artifacts"
```

These tools are intended for safe Builder-executed admin/content workflows. They are not a general local automation shell.

### Phase 2 Mutation Tools

The execution subsystem now also supports bounded mutation tools:

- `write_file`
- `patch_file`

These tools are intended for reviewed Builder-managed content/admin workflows only. Mutation skills should be published from Builder as `review_required` contracts and are expected to trigger runtime confirmation before execution.

Recommended local development values:

```env
FILESYSTEM_MUTATION_ROOTS="D:/GitHub/Codex-RAGenius-System/docs"
FILESYSTEM_MAX_WRITE_BYTES="65536"
FILESYSTEM_MAX_PATCH_BYTES="32768"
```

Phase 2 mutation rules:

- target file must already exist
- target path must be inside configured mutation roots
- mutation execution is confirmation-gated by policy
- arbitrary shell/Python/file-creation behavior is still out of scope

### Phase 3 Approved Adapters and MCP Tools

Phase 3 adds two new execution shapes:

- approved adapter-backed tools such as:
  - `content_transform_adapter`
  - `site_build_adapter`
- discovered MCP-backed tools such as:
  - `mcp.cms.search_pages`
  - `mcp.cms.create_page`

Phase 3 rules:

- Builder should publish these contracts as `review_required`
- adapter execution is allowlisted through `ADAPTERS_JSON`
- MCP tools must be discovered through `POST /v1/tools/discover/mcp` before execution
- write-capable MCP tools are confirmation-gated by policy
- arbitrary shell execution is still out of scope

Example local development value:

```env
ADAPTERS_JSON='[{"id":"content_transform_adapter","command":"transform","enabled":true},{"id":"site_build_adapter","command":"build","enabled":true}]'
```

### Phase 3.5 NotebookLM Adapter

NotebookLM support uses a local Python bridge around `notebooklm-py`.

Phase 1 currently covers:

- `adapter.notebooklm.list_notebooks`
- `adapter.notebooklm.list_sources`
- `adapter.notebooklm.ask`

Phase 2/3 scaffolding now also covers:

- `adapter.notebooklm.add_source_text`
- `adapter.notebooklm.add_source_url`
- `adapter.notebooklm.add_source_file`
- `adapter.notebooklm.generate_report`
- `adapter.notebooklm.generate_slide_deck`
- `adapter.notebooklm.generate_video`

Recommended runtime config:

```env
NOTEBOOKLM_ENABLED="true"
NOTEBOOKLM_PYTHON_COMMAND="python"
NOTEBOOKLM_BRIDGE_SCRIPT="scripts/notebooklm_bridge.py"
# Set only when Google redirects this account to the renamed Gemini Notebook host.
NOTEBOOKLM_BASE_URL="https://notebook.google.com"
NOTEBOOKLM_AUTH_MODE="env_json"
NOTEBOOKLM_ALLOWED_OPERATIONS="list_notebooks,list_sources,ask,add_source_text,add_source_url,add_source_file,generate_report,generate_slide_deck,generate_video"
NOTEBOOKLM_GENERATION_WAIT_FOR_COMPLETION="true"
NOTEBOOKLM_GENERATION_PERSIST_ARTIFACTS="true"
```

Auth expectations:

- install `notebooklm-py` in the Python environment used by `NOTEBOOKLM_PYTHON_COMMAND`
- provide NotebookLM auth through one of the `notebooklm-py` supported storage/env flows
- the current bridge uses `NotebookLMClient.from_storage()`, so `NOTEBOOKLM_AUTH_JSON`, `NOTEBOOKLM_PROFILE`, or a configured storage path must resolve correctly in that Python environment
- `scripts/notebooklm_with_env.ps1` applies a narrow compatibility shim for `NOTEBOOKLM_BASE_URL=https://notebook.google.com`; other hosts retain native `notebooklm-py` validation

Phase 3.5 rules:

- NotebookLM read operations are `review_required` but not confirmation-gated
- NotebookLM source-import and generation operations are confirmation-gated write paths
- the current bridge is a local adapter seam, not an MCP provider
- live end-to-end execution requires a Python environment where `import notebooklm` succeeds

### Phase 3.1 Real Gmail MCP Support

The first real MCP transport target is Gmail over remote HTTP:

- transport: `http`
- endpoint: `https://gmailmcp.googleapis.com/mcp/v1`
- auth: shared OAuth2 bearer token

Recommended runtime config:

```env
GMAIL_MCP_ACCESS_TOKEN="your-shared-oauth-access-token"
MCP_SERVERS_JSON='[
  {
    "id":"gmail",
    "transport":"http",
    "baseUrl":"https://gmailmcp.googleapis.com/mcp/v1",
    "authTokenEnv":"GMAIL_MCP_ACCESS_TOKEN",
    "allowedToolNames":["search_messages","create_draft","send_draft","send_message"],
    "enabled":true
  }
]'
```

Phase 3.1 rules:

- Gmail remains `review_required` at the Builder contract layer
- tools must still be discovered through `POST /v1/tools/discover/mcp`
- only allowlisted Gmail tools are registered into the runtime registry
- the first slice starts with read-only discovery/execution
- later Gmail write slices are added explicitly through allowlisting and confirmation-gated skills

### Phase 3.2 Gmail Draft Creation

The first Gmail write-capable slice adds:

- `mcp.gmail.create_draft`

Phase 3.2 rules:

- Gmail draft creation remains `review_required` in Builder
- runtime permission scope is `external_api.write`
- execution is expected to become `pending_confirmation` before the draft is created
- confirmed execution resumes through the persisted execution id and completes the Gmail draft creation
- send-message behavior is still out of scope

### Gmail Drafts With Artifact Attachments

The first attachment-capable Gmail slice adds:

- `mcp.gmail.create_draft_with_attachments`

Rules for this slice:

- attachment-capable drafts remain `review_required` in Builder
- runtime permission scopes are:
  - `external_api.write`
  - `artifact.read`
- execution is expected to become `pending_confirmation` before the draft is created
- attachment source mode is `artifact_only`
- attachments must come from app-scoped artifacts, not arbitrary local file paths
- the current default policy allows only:
  - artifact type `google_drive_export`
  - MIME types:
    - `application/pdf`
    - `text/plain`
    - `text/markdown`

This slice is meant to pair with the Drive export/read flow. The expected progression is:

1. discover a Drive file
2. materialize it into an app-scoped artifact
3. create a Gmail draft with that artifact attached
4. send that draft later through the existing `mcp.gmail.send_draft` path after a separate confirmation

### Phase 3.3 Gmail Draft Sending

The first Gmail outbound-send slice adds:

- `mcp.gmail.send_draft`

Phase 3.3 rules:

- Gmail send-draft remains `review_required` in Builder
- runtime permission scope is `external_api.write`
- execution is expected to become `pending_confirmation` before outbound delivery
- confirmed execution resumes through the persisted execution id and completes the Gmail draft send
- direct `send_message` behavior is still out of scope

### Phase 3.4 Gmail Direct Send

The first Gmail direct-send slice adds:

- `mcp.gmail.send_message`

Phase 3.4 rules:

- Gmail direct-send remains `review_required` in Builder
- runtime permission scope is `external_api.write`
- execution is expected to become `pending_confirmation` before outbound delivery
- confirmed execution resumes through the persisted execution id and completes the Gmail direct send
- direct-send input is intentionally limited to `to`, `subject`, and `body`
- `cc`, `bcc`, attachments, and richer envelope features remain out of scope

Verification flow:

1. configure `GMAIL_MCP_ACCESS_TOKEN`
2. start `ragenius_execution_subsystem`
3. call `POST /v1/tools/discover/mcp` with `{"provider_id":"gmail"}`
4. verify `mcp.gmail.search_messages` appears in discovered tools
5. execute the sample `gmail_message_search` skill or an equivalent Builder-managed review-required Gmail read contract

### Google Docs MCP Read-Only Slice

The first Google Docs MCP slice is intentionally read-only and targets one capability:

- `mcp.gdocs.search_documents`

Recommended runtime config:

```env
GOOGLE_DOCS_MCP_ACCESS_TOKEN="your-shared-oauth-access-token"
MCP_SERVERS_JSON='[
  {
    "id":"gdocs",
    "transport":"http",
    "baseUrl":"https://google-docs-mcp.example.com/mcp/v1",
    "authTokenEnv":"GOOGLE_DOCS_MCP_ACCESS_TOKEN",
    "allowedToolNames":["search_documents"],
    "enabled":true
  }
]'
```

Docs MCP rules for this slice:

- Google Docs contracts remain `review_required` in Builder
- only the allowlisted `search_documents` tool is registered into the runtime registry
- runtime permission scope is `external_api.read`
- no document content read, mutation, or Drive/attachment workflow is included yet

Verification flow:

1. configure `GOOGLE_DOCS_MCP_ACCESS_TOKEN`
2. start `ragenius_execution_subsystem`
3. call `POST /v1/tools/discover/mcp` with `{"provider_id":"gdocs"}`
4. verify `mcp.gdocs.search_documents` appears in discovered tools
5. execute the sample `google_docs_search` skill or an equivalent Builder-managed review-required Docs search contract

### Google Drive MCP Read-Only Slice

The first Google Drive MCP slice is intentionally read-only and targets one capability:

- `mcp.gdrive.search_files`

Recommended runtime config:

```env
GOOGLE_DRIVE_MCP_ACCESS_TOKEN="your-shared-oauth-access-token"
MCP_SERVERS_JSON='[
  {
    "id":"gdrive",
    "transport":"http",
    "baseUrl":"https://drivemcp.googleapis.com/mcp/v1",
    "authTokenEnv":"GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
    "allowedToolNames":["search_files"],
    "enabled":true
  }
]'
```

Drive MCP rules for this slice:

- Google Drive contracts remain `review_required` in Builder
- only the allowlisted `search_files` tool is registered into the runtime registry
- runtime permission scope is `external_api.read`
- no file download/export, mutation, or Gmail attachment workflow is included yet
- this slice is groundwork for later attachment-capable workflows, not attachment support itself

Verification flow:

1. configure `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`
2. start `ragenius_execution_subsystem`
3. call `POST /v1/tools/discover/mcp` with `{"provider_id":"gdrive"}`
4. verify `mcp.gdrive.search_files` appears in discovered tools
5. execute the sample `google_drive_search` skill or an equivalent Builder-managed review-required Drive search contract

### Google Drive Export/Read Slice

The next Google Drive MCP slice adds one controlled file materialization capability:

- `mcp.gdrive.download_file_content`

Recommended runtime config:

```env
GOOGLE_DRIVE_MCP_ACCESS_TOKEN="your-shared-oauth-access-token"
MCP_SERVERS_JSON='[
  {
    "id":"gdrive",
    "transport":"http",
    "baseUrl":"https://drivemcp.googleapis.com/mcp/v1",
    "authTokenEnv":"GOOGLE_DRIVE_MCP_ACCESS_TOKEN",
    "allowedToolNames":["search_files","download_file_content"],
    "enabled":true
  }
]'
```

Drive export/read rules for this slice:

- Google Drive export/read contracts remain `review_required` in Builder
- `download_file_content` is treated as read-only with `external_api.read`
- exported content is saved into app-scoped artifact storage through `save_artifact`
- the final skill result returns artifact metadata plus Drive file identity
- no arbitrary local download targets are introduced
- this slice is a prerequisite for later attachment-capable Gmail workflows, not attachment support itself

Verification flow:

1. configure `GOOGLE_DRIVE_MCP_ACCESS_TOKEN`
2. start `ragenius_execution_subsystem`
3. call `POST /v1/tools/discover/mcp` with `{"provider_id":"gdrive"}`
4. verify `mcp.gdrive.download_file_content` appears in discovered tools
5. execute the sample `google_drive_download_file` skill or an equivalent Builder-managed review-required export/read contract

### Local PostgreSQL Layout

Recommended local setup:

- same PostgreSQL server instance
- same host and port
- different database names

Example:

```text
RAG / app database:
postgresql://ragenius:ragenius@localhost:5433/ragenius

Execution subsystem database:
postgresql://postgres:postgres@localhost:5433/ragenius_execution?schema=public
```

This keeps Prisma migrations for `ragenius_execution_subsystem` isolated from the RAG/vector data owned by `rag_subsystem`.

### Exact Local Setup Commands

PowerShell:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
Copy-Item .env.example .env
```

Create the dedicated execution database on the same PostgreSQL instance:

```powershell
$env:PGPASSWORD = "postgres"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -p 5433 -d postgres -c "CREATE DATABASE ragenius_execution;"
```

If the database already exists, PostgreSQL will report that and you can continue.

Then verify or set `.env`:

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/ragenius_execution?schema=public"
NODE_ENV="development"
PORT="3000"
LOG_LEVEL="info"
BUILDER_BASE_URL="http://127.0.0.1:8011"
```

Generate the Prisma client and validate the schema:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm install
npx prisma generate
npx prisma validate
```

If you are applying schema changes into the dedicated execution database:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma migrate dev --name execution_store_contract
```

Then start the execution subsystem:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue
$env:BUILDER_BASE_URL = "http://127.0.0.1:8011"
$env:PORT = "3001"
python --version | Out-Null
npm run dev
```

If `BUILDER_BASE_URL` is configured, the execution subsystem can fall back to builder-managed published skills when a requested skill is not found in the local in-memory sample registry. This is intended for the builder-first skill-management MVP.

### Run

```bash
npm run dev
```

### Verify

```bash
npm run lint
npm run typecheck
npm test
npx prisma generate
npx prisma validate
```

## API Routes

### Implemented

- `GET /healthz`
- `GET /readyz`
- `POST /v1/executions`
- `GET /v1/executions/:execution_id`
- `GET /v1/executions/:execution_id/logs`
- `POST /v1/executions/:execution_id/confirm`
- `GET /v1/skills`
- `GET /v1/skills/:skill_id`
- `GET /v1/tools`
- `POST /v1/tools/discover/mcp`

## Example Request

```json
{
  "request_type": "execute_skill",
  "app_id": "app_001",
  "session_id": "sess_001",
  "skill_id": "video_director_skill",
  "input": {
    "prompt": "Explain RAG simply",
    "duration": 30
  }
}
```

## Example Completed Response

```json
{
  "execution_id": "execution_7f3e6e0c4a2b",
  "status": "completed",
  "result_type": "video",
  "result": {
    "title": "Video: Explain RAG simply",
    "summary": "Generated 30 second explainer video."
  },
  "files": [
    {
      "file_id": "file_mock_video_001",
      "kind": "video",
      "mime_type": "video/mp4"
    }
  ],
  "errors": [],
  "logs_summary": "Skill completed in 3 steps with 2 tool calls."
}
```

## Example Pending Confirmation Response

```json
{
  "execution_id": "execution_7f3e6e0c4a2b",
  "status": "pending_confirmation",
  "result_type": "json",
  "result": {
    "required_confirmation": true,
    "tool_id": "mock_video_generation_tool",
    "permission_scope": "external_api.write"
  },
  "files": [],
  "errors": [],
  "logs_summary": "Execution paused because confirmation is required."
}
```

## Key Boundaries

- `ragenius_app` plans; this subsystem executes.
- `ragenius_builder` owns skill definitions, published versions, and app-skill bindings.
- Skills are the primary execution unit.
- All tool calls go through `ToolEngine`.
- MCP is treated as an untrusted provider layer.
- RAG is read-only through `rag_retrieval_tool`.
- Side-effecting tools require explicit policy.
- Logs must redact credentials and secrets.

## Supporting Docs

- `docs/architecture.md`
- `docs/api-contract.md`
- `docs/security.md`
- `docs/workflow-execution-map.yaml`
