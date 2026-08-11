## RAGenius Builder

`ragenius_builder/flask_scaffold/` is the primary builder/admin application in this repository.

Use the Flask scaffold for builder work:

```bash
cd ragenius_builder/flask_scaffold
flask --app app.py run --reload
```

What is active:

- admin workflows
- apps CRUD
- instructions markdown editor
- schema-driven settings UI
- uploads and docs management
- search admin tooling
- read-only subsystem settings visibility

What is not active:

- the older FastAPI prototype that previously lived at `ragenius_builder/main.py`

That prototype has been quarantined under `ragenius_builder/archived_fastapi_prototype/` so it remains available for historical reference without presenting itself as a second supported runtime.

### Agent Skill governance

Builder is the administrative control plane for discovered Codex and OpenClaw Agent Skills. Configure only trusted local sources in the execution subsystem, then use Builder to discover, approve, bind, and synchronize skills. Execution stores the acknowledged projection, so Builder does not need to remain running while users list or invoke synchronized skills.

```powershell
$env:RAGENIUS_EXECUTION_BASE_URL = "http://127.0.0.1:3001"
$env:RAGENIUS_BUILDER_INSTANCE_ID = "builder-primary"
$env:RAGENIUS_BUILDER_EXECUTION_SERVICE_TOKEN = "replace-builder-token"
$env:RAGENIUS_BUILDER_ADMIN_TOKEN = "replace-browser-and-api-admin-token"
# Optional for large OpenClaw inventories.
$env:RAGENIUS_BUILDER_EXECUTION_TIMEOUT_SECONDS = "120"
```

`RAGENIUS_BUILDER_INSTANCE_ID` must equal execution's `AGENT_SKILL_TRUSTED_BUILDER_INSTANCE_ID`. `RAGENIUS_BUILDER_EXECUTION_SERVICE_TOKEN` is the outbound service credential and must match a dedicated execution credential with `agent_skills:admin`; do not reuse the app token. `RAGENIUS_BUILDER_ADMIN_TOKEN` is a separate inbound credential required by publication preview, publish, and legacy synchronize routes. API clients send it as `Authorization: Bearer <token>`. The browser review page uses HTTP Basic authentication with any username and this token as the password; its publication form also requires the page-issued CSRF token. API and legacy synchronize routes do not accept ambient Basic credentials. Publication fails closed when the inbound token is absent. Runtime paths and provider metadata remain protected and are not exposed through public inventory APIs.
