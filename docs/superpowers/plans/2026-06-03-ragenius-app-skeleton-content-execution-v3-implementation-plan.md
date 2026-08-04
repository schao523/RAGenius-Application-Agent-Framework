# RAGenius App Skeleton Content/Execution v3 Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add additive `@exec` routing, dual-lane session state, approved-content binding, and execution-intent submission to `ragenius_app_skeleton` without changing existing normal non-prefixed turn behavior.

**Architecture:** Keep one user-visible chat session and preserve the current compiled instruction/planner path for all non-`@exec` turns. Add a narrow pre-router that detects `@exec` turns, parses them into deterministic execution-intent requests, binds them to approved content or explicit targets, and updates a separate execution lane inside session runtime state. Use app-side services for `ApprovedContent`, `ExecutionIntent`, and execution submission so the app remains the policy boundary before `ragenius_execution_subsystem`.

**Tech Stack:** FastAPI, Pydantic, SQLite-backed session state in `chat_repos.py`, existing LangGraph workflow state, HTTP integration with `ragenius_execution_subsystem`, existing builder-compiled instruction/runtime models.

---

## File Structure

**Modify**
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
  - Add the lightweight `@exec` pre-router at the chat entry boundary.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_repos.py`
  - Persist dual-lane runtime state, approved-content records, execution-intent records, and execution refs.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
  - Keep normal chat path unchanged; expose enough structured return data for lane-safe persistence and audit summaries.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\graph_state.py`
  - Add explicit fields for dual-lane session state and approval snapshots without breaking current state shape.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
  - Add turn-routing and execution-lane models used by the app boundary.

**Create**
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\exec_router.py`
  - Parse `@exec` turns, normalize structured commands, and return deterministic routing outcomes.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_intent_service.py`
  - Build `ExecutionIntent` from approved content, selected skill, and command arguments.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\approved_content_service.py`
  - Create, version, hash, and resolve approved content snapshots from normal chat flow.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_subsystem_client.py`
  - Wrap calls to `ragenius_execution_subsystem` and normalize submit/status results.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_exec_router.py`
  - Unit coverage for prefix detection, command parsing, and safety failures.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_approved_content_service.py`
  - Coverage for snapshot creation, revision hashing, and approved-content lookup.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_execution_intent_service.py`
  - Coverage for deterministic mapping from approved content + command arguments to runtime-ready payloads.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_chat_exec_routing.py`
  - Endpoint-level regression coverage for normal turns and `@exec` turns.
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_session_repo_dual_lane.py`
  - Persistence coverage for content lane and execution lane state.

**Reference**
- `D:\GitHub\Codex-RAGenius-System\docs\2026-06-03-ragenius-content-execution-split-contract-v3.md`
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\schemas\execution-request.schema.ts`
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\executions.routes.ts`

---

### Task 1: Freeze Normal-Turn Compatibility With Regression Tests

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_chat_exec_routing.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
- Reference: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`

- [ ] **Step 1: Add a minimal FastAPI chat test harness around the existing `/sessions/{session_id}/chat` route**

```python
from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)
```

- [ ] **Step 2: Write a failing regression test proving a normal non-prefixed turn still goes through the current planner/chat pipeline**

```python
def test_normal_turn_without_exec_prefix_uses_existing_chat_pipeline(monkeypatch):
    calls = []

    def fake_run_chat_pipeline(**kwargs):
        calls.append(kwargs["user_query"])
        return {
            "answer": {"content": "normal-path"},
            "planner_output": {},
            "workflow_progress": {},
            "session_execution_state": {},
        }

    monkeypatch.setattr("backend.app.main.run_chat_pipeline", fake_run_chat_pipeline)

    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "Revise the introduction to be friendlier.",
        },
    )

    assert response.status_code == 200
    assert calls == ["Revise the introduction to be friendlier."]
```

- [ ] **Step 3: Write a failing regression test proving upload-analysis and workflow-advance style normal turns are still unaffected**

```python
def test_non_exec_turn_keeps_existing_runtime_fields(monkeypatch):
    def fake_run_chat_pipeline(**kwargs):
        return {
            "answer": {"content": "ok"},
            "planner_output": {"intentType": "qa"},
            "workflow_progress": {"workflow_id": "wf-1", "step_id": "step-1"},
            "session_execution_state": {"execution_status": "guiding"},
        }

    monkeypatch.setattr("backend.app.main.run_chat_pipeline", fake_run_chat_pipeline)

    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "Continue.",
        },
    )

    payload = response.json()
    assert payload["answer"]["content"] == "ok"
    assert payload["workflow_progress"]["workflow_id"] == "wf-1"
    assert payload["session_execution_state"]["execution_status"] == "guiding"
```

- [ ] **Step 4: Run the new tests and confirm they fail for the missing `@exec` isolation behavior only after the next tasks add the new branch**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
```

Expected:
- The file imports cleanly.
- The normal-path tests pass before `@exec` work is wired in.
- Later-added `@exec` tests fail until implementation exists.

---

### Task 2: Introduce Dual-Lane Session and Routing Models

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\graph_state.py`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_session_repo_dual_lane.py`

- [ ] **Step 1: Add explicit app-boundary models for approved content, execution intent, and lane state**

```python
class ApprovedContentSnapshot(BaseModel):
    approved_content_id: str
    session_id: str
    source_message_id: str | None = None
    revision_id: str
    content_hash: str
    content_text: str
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    target_refs: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ExecutionIntentRecord(BaseModel):
    execution_intent_id: str
    session_id: str
    approved_content_id: str | None = None
    skill_id: str
    skill_version: str | None = None
    command_text: str
    mapped_input: dict[str, Any]
    execution_mode: Literal["sync", "async"] = "sync"
    created_at: str


class SessionLaneState(BaseModel):
    content_lane: dict[str, Any] = Field(default_factory=dict)
    execution_lane: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 2: Extend `GraphState` with additive lane-oriented fields instead of replacing existing keys**

```python
class GraphState(TypedDict, total=False):
    ...
    session_lane_state: Dict[str, Any]
    approved_content_snapshot: Dict[str, Any]
    execution_intent_record: Dict[str, Any]
    turn_routing_decision: Dict[str, Any]
```

- [ ] **Step 3: Add a persistence test that proves runtime state can store both legacy execution state and the new lane state together**

```python
def test_runtime_state_stores_dual_lane_without_losing_legacy_fields():
    runtime_state = {
        "workflow_progress": {"workflow_id": "wf-1"},
        "session_execution_state": {"execution_status": "guiding"},
        "session_lane_state": {
            "content_lane": {"latest_approved_content_id": "ac-1"},
            "execution_lane": {"latest_execution_intent_id": "ei-1"},
        },
    }
    assert runtime_state["workflow_progress"]["workflow_id"] == "wf-1"
    assert runtime_state["session_lane_state"]["content_lane"]["latest_approved_content_id"] == "ac-1"
```

- [ ] **Step 4: Run the targeted persistence/model tests**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_session_repo_dual_lane.py -q
```

Expected:
- Fails until repo normalization persists `session_lane_state`.

---

### Task 3: Add the `@exec` Pre-Router Without Disturbing Normal Turns

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\exec_router.py`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_exec_router.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`

- [ ] **Step 1: Define a small deterministic routing result model**

```python
class ExecRouteDecision(BaseModel):
    is_exec_turn: bool
    command: str | None = None
    subcommand: str | None = None
    raw_args: str | None = None
    error: str | None = None
```

- [ ] **Step 2: Implement parser rules for `@exec`, `@exec skill`, and `@exec status` without trying to do full natural-language planning here**

```python
def parse_exec_turn(user_query: str) -> ExecRouteDecision:
    text = str(user_query or "").strip()
    if not text.startswith("@exec"):
        return ExecRouteDecision(is_exec_turn=False)
    parts = text.split(maxsplit=3)
    if len(parts) == 1:
        return ExecRouteDecision(is_exec_turn=True, error="Missing exec command.")
    command = parts[1]
    if command == "skill" and len(parts) >= 3:
        return ExecRouteDecision(is_exec_turn=True, command="skill", subcommand=parts[2], raw_args=parts[3] if len(parts) >= 4 else "")
    if command == "status" and len(parts) >= 3:
        return ExecRouteDecision(is_exec_turn=True, command="status", raw_args=parts[2])
    return ExecRouteDecision(is_exec_turn=True, error="Unsupported exec command.")
```

- [ ] **Step 3: Write router tests that prove normal turns bypass the new branch and `@exec` turns are recognized early**

```python
def test_parse_exec_turn_non_prefixed_query_is_normal():
    decision = parse_exec_turn("Make the draft shorter.")
    assert decision.is_exec_turn is False


def test_parse_exec_turn_skill_command():
    decision = parse_exec_turn("@exec skill notebooklm_generate_video use approved content")
    assert decision.is_exec_turn is True
    assert decision.command == "skill"
    assert decision.subcommand == "notebooklm_generate_video"
```

- [ ] **Step 4: Wire the parser into `main.py` before `run_chat_pipeline`, but only branch on positive `@exec` detection**

```python
route = parse_exec_turn(request.user_query)
if not route.is_exec_turn:
    return _handle_normal_chat_turn(...)
return _handle_exec_turn(...)
```

- [ ] **Step 5: Run router and endpoint tests**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_exec_router.py ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py -q
```

Expected:
- Normal-turn tests still pass.
- `@exec` tests fail until the execution path is fully implemented.

---

### Task 4: Add Approved-Content Snapshot Creation and Lookup

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\approved_content_service.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_repos.py`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_approved_content_service.py`

- [ ] **Step 1: Add SQLite tables and repo methods for approved-content snapshots and execution intents**

```sql
CREATE TABLE IF NOT EXISTS approved_content (
    approved_content_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    source_message_id TEXT,
    content_hash TEXT NOT NULL,
    content_text TEXT NOT NULL,
    artifact_refs_json TEXT NOT NULL,
    target_refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_intents (
    execution_intent_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    approved_content_id TEXT,
    skill_id TEXT NOT NULL,
    skill_version TEXT,
    command_text TEXT NOT NULL,
    mapped_input_json TEXT NOT NULL,
    execution_mode TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

- [ ] **Step 2: Implement content hashing and snapshot creation from approved normal-path outputs**

```python
def content_hash_for(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_approved_snapshot(...):
    return ApprovedContentSnapshot(
        approved_content_id=f"ac_{uuid.uuid4().hex[:12]}",
        revision_id=f"rev_{uuid.uuid4().hex[:8]}",
        content_hash=content_hash_for(content_text),
        ...
    )
```

- [ ] **Step 3: Write tests for duplicate-content hashing, latest snapshot lookup, and missing-snapshot failure**

```python
def test_create_snapshot_produces_stable_hash():
    snapshot = create_approved_snapshot(session_id="s1", content_text="hello")
    assert len(snapshot.content_hash) == 64


def test_resolve_latest_snapshot_returns_latest_revision(repo):
    latest = repo.get_latest_approved_content("s1")
    assert latest["approved_content_id"] == "ac-2"
```

- [ ] **Step 4: Add app policy rule to fail `@exec skill ...` when the selected skill needs approved content and none exists**

```python
if requires_approved_content and snapshot is None:
    raise HTTPException(status_code=400, detail="No approved content is available for this session.")
```

- [ ] **Step 5: Run approved-content and repo tests**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_approved_content_service.py ragenius_app_skeleton/backend/tests/test_session_repo_dual_lane.py -q
```

Expected:
- Pass once snapshots and tables are wired correctly.

---

### Task 5: Build Deterministic ExecutionIntent and Execution-Subsystem Submission

**Files:**
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_intent_service.py`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_subsystem_client.py`
- Create: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_execution_intent_service.py`

- [ ] **Step 1: Implement deterministic input mapping from approved content + parsed command args to the execution subsystem request envelope**

```python
def build_execution_intent(*, snapshot, skill_id: str, route, overrides: dict[str, Any]) -> ExecutionIntentRecord:
    mapped_input = {
        "instructions": snapshot.content_text,
        **overrides,
    }
    return ExecutionIntentRecord(
        execution_intent_id=f"ei_{uuid.uuid4().hex[:12]}",
        session_id=snapshot.session_id,
        approved_content_id=snapshot.approved_content_id,
        skill_id=skill_id,
        command_text=route.raw_args or "",
        mapped_input=mapped_input,
        execution_mode="async" if mapped_input.get("waitForCompletion") is False else "sync",
        created_at=_utcnow(),
    )
```

- [ ] **Step 2: Wrap execution-subsystem requests in one client so `main.py` never constructs raw HTTP payloads inline**

```python
class ExecutionSubsystemClient:
    def submit_skill(self, *, session_id: str, app_id: str, user_id: str, skill_id: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "application_id": app_id,
            "user_id": user_id,
            "skill_id": skill_id,
            "input": input_payload,
        }
        ...
```

- [ ] **Step 3: Write intent-service tests proving notebook-title and approved-content text survive deterministic mapping**

```python
def test_build_execution_intent_keeps_approved_text_and_notebook_title():
    intent = build_execution_intent(
        snapshot=ApprovedContentSnapshot(..., content_text="Explain the tool in a friendly way"),
        skill_id="notebooklm_generate_video",
        route=route,
        overrides={"notebookTitle": "GPT Application Designer", "waitForCompletion": False},
    )
    assert intent.mapped_input["instructions"] == "Explain the tool in a friendly way"
    assert intent.mapped_input["notebookTitle"] == "GPT Application Designer"
```

- [ ] **Step 4: Normalize submit responses for sync success, async submission, and timeout-like recoverable cases**

```python
def normalize_execution_submit_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "completed":
        return {"state": "completed", "result": result}
    return {"state": "submitted", "result": result}
```

- [ ] **Step 5: Run intent and client tests**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_execution_intent_service.py -q
```

Expected:
- Pass once intent mapping and response normalization are deterministic.

---

### Task 6: Integrate the `@exec` Lane Into the Chat Endpoint

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_repos.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
- Modify: `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_chat_exec_routing.py`

- [ ] **Step 1: Add a dedicated `_handle_exec_turn(...)` path that never calls `run_chat_pipeline` for `@exec` turns**

```python
def _handle_exec_turn(...):
    route = parse_exec_turn(request.user_query)
    if route.command == "status":
        return _handle_exec_status(...)
    if route.command == "skill":
        return _handle_exec_skill(...)
    raise HTTPException(status_code=400, detail=route.error or "Unsupported exec command.")
```

- [ ] **Step 2: Update session runtime state so content and execution lanes are both persisted under one session**

```python
runtime_state["session_lane_state"] = {
    "content_lane": {
        "latest_approved_content_id": approved_content_id,
        "latest_revision_id": revision_id,
    },
    "execution_lane": {
        "latest_execution_intent_id": execution_intent_id,
        "latest_execution_id": execution_id,
        "latest_status": submit_state,
    },
}
```

- [ ] **Step 3: Add endpoint tests for successful `@exec skill ...` submission and `@exec status ...` lookup**

```python
def test_exec_skill_turn_submits_execution_intent(monkeypatch):
    monkeypatch.setattr("backend.app.main.parse_exec_turn", lambda _: ExecRouteDecision(is_exec_turn=True, command="skill", subcommand="notebooklm_generate_video", raw_args="use approved content"))
    ...
    response = client.post("/sessions/session-1/chat", json={...})
    assert response.status_code == 200
    assert response.json()["execution_lane"]["latest_status"] in {"submitted", "completed"}


def test_exec_status_turn_does_not_invoke_normal_chat_pipeline(monkeypatch):
    ...
```

- [ ] **Step 4: Add negative-path tests for missing approved content, unsupported command, and explicit execution errors**

```python
def test_exec_skill_without_approved_content_returns_400():
    response = client.post("/sessions/session-1/chat", json={... "@exec skill notebooklm_generate_video"})
    assert response.status_code == 400
```

- [ ] **Step 5: Run the full app-skeleton backend test slice**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_exec_router.py ragenius_app_skeleton/backend/tests/test_approved_content_service.py ragenius_app_skeleton/backend/tests/test_execution_intent_service.py ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py ragenius_app_skeleton/backend/tests/test_session_repo_dual_lane.py -q
```

Expected:
- All tests pass.
- Normal non-`@exec` turns still use the existing planner/chat path.

---

### Task 7: Add Contract-Facing Documentation and Operator Verification

**Files:**
- Modify: `D:\GitHub\Codex-RAGenius-System\docs\2026-06-03-ragenius-content-execution-split-contract-v3.md`
- Create: `D:\GitHub\Codex-RAGenius-System\docs\superpowers\plans\verification-notes-ragenius-app-skeleton-exec-routing.md`

- [ ] **Step 1: Document the implemented command forms and backward-compatibility guarantees**

```md
Supported explicit execution overrides:
- `@exec skill <skill_id> ...`
- `@exec status <execution_id>`

Compatibility guarantee:
- Non-`@exec` turns continue through the existing compiled instruction/planner path unchanged.
```

- [ ] **Step 2: Capture manual verification scenarios for operators**

```md
1. Normal content-revision turn in an existing workflow session.
2. Approval snapshot creation from a reviewed content revision.
3. `@exec skill notebooklm_generate_video ...` using approved content.
4. `@exec status <execution_id>` after submission.
5. Content revision after execution submission does not mutate the prior execution record.
```

- [ ] **Step 3: Run final verification commands**

Run:

```powershell
python -m pytest ragenius_app_skeleton/backend/tests -q
```

Expected:
- New app-skeleton execution-lane tests pass.
- Existing normal-turn tests remain green.

---

## Self-Review

### Spec coverage
- Dual-lane session model: covered in Tasks 2 and 6.
- Routing policy with additive `@exec`: covered in Tasks 3 and 6.
- Backward compatibility for ordinary turns: covered in Tasks 1, 3, and 6.
- `ApprovedContent -> ExecutionIntent -> StructuredExecutionRequest`: covered in Tasks 4 and 5.
- Execution-lane persistence and status lookup: covered in Tasks 4, 5, and 6.

### Placeholder scan
- No `TODO`/`TBD` placeholders remain.
- Each implementation area names concrete files, commands, and expected outcomes.

### Type consistency
- Uses `ApprovedContentSnapshot`, `ExecutionIntentRecord`, and `ExecRouteDecision` consistently across tasks.
- Keeps the existing `workflow_progress` and `session_execution_state` fields additive rather than replaced.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-03-ragenius-app-skeleton-content-execution-v3-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
