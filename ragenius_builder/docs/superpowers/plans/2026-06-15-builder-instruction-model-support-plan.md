# Builder Instruction Model Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only Builder support for inspecting the compiled instruction model produced by `ragenius_app_skeleton`, without changing existing Builder app CRUD, instruction editing, settings, uploads, search, skills, or runtime execution behavior.

**Architecture:** Add a narrow read-only adapter that loads compiled instruction model snapshots, a read-only Builder API endpoint, and a UI projection inside the existing instructions preview area. Existing instruction save/settings/upload/skill/search routes remain unchanged, and no Builder path compiles, executes, or mutates runtime instruction state.

**Tech Stack:** Python, Flask, Jinja templates, vanilla browser JavaScript, unittest, existing `DatabaseStore` instruction metadata.

---

## Read This First

- `AGENTS.md`
- `ragenius_builder/AGENTS.md`
- `ragenius_builder/docs/builder_gui_instruction_model_contract.md`
- `ragenius_builder/docs/builder_gui_instruction_model_design.md`
- `ragenius_builder/flask_scaffold/templates/config.html`
- `ragenius_builder/flask_scaffold/app.py`
- `ragenius_builder/flask_scaffold/storage.py`

## Safety Strategy

This feature must be additive and read-only.

Required safeguards:

- Do not change `DatabaseStore.get_instructions`.
- Do not change `DatabaseStore.update_instructions`.
- Do not change `DatabaseStore.get_settings`.
- Do not change `DatabaseStore.update_settings`.
- Do not change upload/document/search/skill routes.
- Do not add automatic compile behavior.
- Do not read or write end-user chat sessions.
- Do not parse Builder Markdown and present it as the runtime model.
- Do not mutate `ragenius_app_skeleton/backend/.state`.
- Do not make app-skeleton `.state` a permanent storage contract; use an adapter name and environment configuration.

Regression checks must prove these existing capabilities still work:

- GET `/apps/<app_id>/config?tab=instructions`
- POST `/apps/<app_id>/config?tab=instructions`
- GET `/apps/<app_id>/config?tab=settings`
- POST `/apps/<app_id>/config?tab=settings`
- GET `/api/apps/<app_id>/instructions`
- PATCH `/api/apps/<app_id>/instructions`
- GET `/api/apps/<app_id>/settings`
- PATCH `/api/apps/<app_id>/settings`
- GET `/skills`
- GET `/apps/<app_id>/docs`
- GET `/apps/<app_id>/search`

## File Structure

Create:

- `ragenius_builder/flask_scaffold/instruction_model_adapter.py`
  - Read-only adapter for compiled instruction model snapshots.
  - Computes display-safe status and freshness metadata.
  - Does not depend on Flask.

- `ragenius_builder/flask_scaffold/tests/test_instruction_model_support.py`
  - Adapter, API, UI marker, and regression tests.

Modify:

- `ragenius_builder/flask_scaffold/app.py`
  - Add one read-only route: `GET /api/apps/<app_id>/instruction-model`.
  - Pass no new mutable state into existing POST handlers.

- `ragenius_builder/flask_scaffold/templates/config.html`
  - Replace the plain `Preview` label with display mode tabs.
  - Preserve existing Markdown preview behavior.
  - Add a Runtime Model container that calls the read-only API.
  - Add Raw JSON display.

Optional if the inline script becomes too large:

- `ragenius_builder/flask_scaffold/static/instruction_model.js`
  - Runtime Model rendering logic.
  - Use only if static file serving is already configured and compatible with the current Flask scaffold.

Do not modify:

- `ragenius_app/`
- `rag_subsystem/`
- `ragenius_execution_subsystem/`
- `ragenius_app_skeleton/` runtime code

## Runtime Configuration

Use environment variables for the compatibility adapter:

```text
RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT=D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\.state\instruction_understanding_snapshots
RAGENIUS_INSTRUCTION_MODEL_SOURCE=filesystem
```

Default behavior if unset:

- API returns a successful JSON response with `status: "missing"` or `source_kind: "unconfigured"`.
- UI shows a missing/unconfigured state.
- Existing Builder page loads normally.

The plan intentionally avoids a hard-coded dependency on:

```text
ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots
```

That path may be used by local development through the environment variable, but must not become a hidden permanent Builder contract.

---

### Task 1: Add Failing Adapter Tests

**Objective:** Lock the read-only adapter contract before implementation.

**Files:**

- Create: `ragenius_builder/flask_scaffold/tests/test_instruction_model_support.py`
- Create later: `ragenius_builder/flask_scaffold/instruction_model_adapter.py`

- [ ] **Step 1: Create tests for missing, found, invalid, and stale snapshots**

Add tests with these cases:

```python
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from instruction_model_adapter import InstructionModelAdapter


class InstructionModelAdapterTests(unittest.TestCase):
    def test_returns_unconfigured_when_snapshot_root_missing(self):
        adapter = InstructionModelAdapter(snapshot_root=None)

        result = adapter.get_latest_instruction_model(
            app_id="app-1",
            current_instruction={"content": "# Hello", "version": "v1", "uri": "instructions/app-1/instructions.md"},
        )

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["source_kind"], "unconfigured")
        self.assertEqual(result["freshness"], "unknown")
        self.assertEqual(result["payload"], None)
        self.assertEqual(result["errors"], [])

    def test_loads_understanding_json_from_snapshot_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            content = "# Hello"
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            payload = {
                "compiled_status": "ready",
                "compiled_at": "2026-06-15T01:02:03Z",
                "instruction_source_hash": digest,
                "instruction_source_version": "v1",
                "instruction_uri": "instructions/app-1/instructions.md",
                "parser_contract_version": "instruction-parser-2026-05-18-v3",
                "binding_logic_version": "binding-logic-2026-05-07-v1",
                "compiled_contract": {
                    "instruction_runtime_model": {
                        "primary_service_mode": "guided_workflow",
                        "default_workflow_id": "workflow.main",
                        "instruction_service_blocks": [{"id": "workflow.main", "role": "primary"}],
                        "instruction_procedures": [{"id": "proc.main", "procedure_steps": [{"id": "step.one"}]}],
                        "instruction_resources": [{"id": "res.one", "role": "reference"}],
                        "global_policies": ["Use uploaded docs first."],
                    }
                },
                "semantic_compile": {"attached": True, "valid": True},
            }
            (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={"content": content, "version": "v1", "uri": "instructions/app-1/instructions.md"},
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["source_kind"], "filesystem_snapshot")
            self.assertEqual(result["freshness"], "current")
            self.assertEqual(result["payload"]["compiled_status"], "ready")
            self.assertEqual(result["summary"]["service_block_count"], 1)
            self.assertEqual(result["summary"]["procedure_count"], 1)
            self.assertEqual(result["summary"]["procedure_step_count"], 1)
            self.assertEqual(result["summary"]["resource_count"], 1)

    def test_marks_snapshot_stale_when_hash_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            payload = {
                "compiled_status": "ready",
                "instruction_source_hash": "old-hash",
                "instruction_source_version": "v1",
                "compiled_contract": {"instruction_runtime_model": {}},
            }
            (app_dir / "understanding.json").write_text(json.dumps(payload), encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={"content": "# Changed", "version": "v1", "uri": "instructions/app-1/instructions.md"},
            )

            self.assertEqual(result["freshness"], "stale")
            self.assertIn("hash", result["freshness_reason"])

    def test_invalid_json_returns_error_without_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "app-1"
            app_dir.mkdir()
            (app_dir / "understanding.json").write_text("{invalid-json", encoding="utf-8")
            adapter = InstructionModelAdapter(snapshot_root=root)

            result = adapter.get_latest_instruction_model(
                app_id="app-1",
                current_instruction={"content": "# Hello", "version": "v1", "uri": "instructions/app-1/instructions.md"},
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["payload"], None)
            self.assertTrue(result["errors"])
```

- [ ] **Step 2: Run tests and confirm they fail because the adapter does not exist**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_instruction_model_support
```

Expected:

```text
ModuleNotFoundError: No module named 'instruction_model_adapter'
```

---

### Task 2: Implement The Read-Only Adapter

**Objective:** Add a small pure-Python adapter that reads runtime-produced artifacts without mutating anything.

**Files:**

- Create: `ragenius_builder/flask_scaffold/instruction_model_adapter.py`
- Test: `ragenius_builder/flask_scaffold/tests/test_instruction_model_support.py`

- [ ] **Step 1: Implement `InstructionModelAdapter`**

Implementation rules:

- Use only file reads.
- Do not create directories.
- Do not write files.
- Do not import Flask.
- Return JSON-serializable dictionaries.
- Keep raw payload unchanged in `payload`.
- Put friendly counts in `summary`.

Core shape:

```python
class InstructionModelAdapter:
    def __init__(self, snapshot_root):
        self.snapshot_root = Path(snapshot_root).resolve() if snapshot_root else None

    def get_latest_instruction_model(self, app_id, current_instruction):
        return {
            "app_id": app_id,
            "source_kind": "unconfigured",
            "source_path": None,
            "loaded_at": datetime.datetime.utcnow().isoformat() + "Z",
            "compiled_at": None,
            "status": "missing",
            "freshness": "unknown",
            "freshness_reason": "snapshot root is not configured",
            "summary": {},
            "payload": None,
            "errors": [],
        }
```

Expected result shape:

```python
{
    "app_id": "app-1",
    "source_kind": "filesystem_snapshot",
    "source_path": "D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/app-1/understanding.json",
    "loaded_at": "2026-06-15T01:03:04Z",
    "compiled_at": "2026-06-15T01:02:03Z",
    "status": "ready",
    "freshness": "current",
    "freshness_reason": "compiled hash matches current instruction content",
    "summary": {
        "primary_service_mode": "guided_workflow",
        "default_workflow_id": "workflow.main",
        "service_block_count": 1,
        "procedure_count": 1,
        "procedure_step_count": 1,
        "resource_count": 1,
        "validation_error_count": 0,
        "validation_warning_count": 0,
        "semantic_attached": True,
        "semantic_valid": True,
    },
    "payload": {"compiled_status": "ready", "compiled_contract": {"instruction_runtime_model": {}}},
    "errors": [],
}
```

- [ ] **Step 2: Run adapter tests**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_instruction_model_support
```

Expected:

```text
OK
```

---

### Task 3: Add Read-Only API Route

**Objective:** Expose the adapter to the Builder GUI through a scoped, read-only endpoint.

**Files:**

- Modify: `ragenius_builder/flask_scaffold/app.py`
- Test: `ragenius_builder/flask_scaffold/tests/test_instruction_model_support.py`

- [ ] **Step 1: Add API tests**

Add tests that:

- Create a temporary `DatabaseStore`.
- Create one app with instructions.
- Configure a temporary snapshot root.
- Call `GET /api/apps/<app_id>/instruction-model`.
- Assert status code `200`.
- Assert the response includes `app_id`, `status`, `freshness`, `summary`, and `payload`.
- Assert a missing app returns `404`.
- Assert no POST route exists.

Representative assertions:

```python
self.assertEqual(response.status_code, 200)
body = response.get_json()
self.assertEqual(body["app_id"], created["id"])
self.assertEqual(body["status"], "ready")
self.assertIn("summary", body)
self.assertIn("payload", body)
```

- [ ] **Step 2: Run tests and confirm route is missing**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_instruction_model_support
```

Expected:

```text
AssertionError: 404 != 200
```

- [ ] **Step 3: Add route in `app.py`**

Route contract:

```text
GET /api/apps/<app_id>/instruction-model
```

Implementation requirements:

- Call `store.get_application(app_id)` first.
- Return `404` for unknown app.
- Call `store.get_instructions(app_id)`.
- Instantiate adapter from env/config.
- Return adapter result as JSON.
- Do not update instructions.
- Do not update settings.
- Do not call any compile function.

Pseudo-code:

```python
@app.route("/api/apps/<app_id>/instruction-model")
def api_get_instruction_model(app_id):
    if not store.get_application(app_id):
        return jsonify({"error": "not found"}), 404
    instructions = store.get_instructions(app_id) or {"content": "", "version": "", "uri": ""}
    snapshot_root = os.environ.get("RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT")
    adapter = InstructionModelAdapter(snapshot_root=snapshot_root)
    return jsonify(adapter.get_latest_instruction_model(app_id, instructions))
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_instruction_model_support
```

Expected:

```text
OK
```

---

### Task 4: Add UI Tests And Protect Existing Config Flows

**Objective:** Prove the UI enhancement is additive and does not break instructions/settings behavior.

**Files:**

- Modify: `ragenius_builder/flask_scaffold/tests/test_instruction_model_support.py`
- Modify later: `ragenius_builder/flask_scaffold/templates/config.html`

- [ ] **Step 1: Add GET UI marker test**

Assert that the instructions config page includes:

- Runtime Model mode.
- Markdown Preview mode.
- Raw JSON mode.
- Existing textarea `name="content"`.
- Existing submit button `Save Instructions`.

Representative assertions:

```python
response = client.get(f"/apps/{created['id']}/config?tab=instructions")
body = response.get_data(as_text=True)
self.assertEqual(response.status_code, 200)
self.assertIn("Runtime Model", body)
self.assertIn("Markdown Preview", body)
self.assertIn("Raw JSON", body)
self.assertIn('name="content"', body)
self.assertIn("Save Instructions", body)
```

- [ ] **Step 2: Add POST instructions regression test**

Assert that posting instructions still updates the file-backed instruction content.

Representative assertions:

```python
response = client.post(
    f"/apps/{created['id']}/config?tab=instructions",
    data={"content": "# Updated", "version": "v2", "uri": "instructions/app/instructions.md"},
)
self.assertEqual(response.status_code, 200)
updated = store.get_instructions(created["id"])
self.assertEqual(updated["content"], "# Updated")
self.assertEqual(updated["version"], "v2")
```

- [ ] **Step 3: Add POST settings regression test**

Assert that settings tab still saves existing settings payload.

Representative assertions:

```python
response = client.post(
    f"/apps/{created['id']}/config?tab=settings",
    data={"config_settings": '{"llm": {"provider": "test"}}', "config_schema": '{"type": "object", "properties": {"llm": {"type": "object"}}}'},
)
self.assertEqual(response.status_code, 200)
settings = store.get_settings(created["id"])
self.assertIn('"provider": "test"', settings["config_settings"])
```

- [ ] **Step 4: Run tests and confirm UI marker fails before template change**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_instruction_model_support
```

Expected:

```text
AssertionError: 'Runtime Model' not found
```

---

### Task 5: Enhance The Instructions Preview Pane

**Objective:** Add Runtime Model and Raw JSON display modes while preserving current Markdown preview and form submission.

**Files:**

- Modify: `ragenius_builder/flask_scaffold/templates/config.html`
- Test: `ragenius_builder/flask_scaffold/tests/test_instruction_model_support.py`

- [ ] **Step 1: Replace only the right-side preview pane**

Keep the existing form, inputs, textarea, validation block, and submit button unchanged.

Replace:

```html
<p class="text-sm font-semibold text-gray-800 mb-2">Preview</p>
<div class="prose max-w-none bg-gray-50 border border-gray-200 rounded p-3" id="markdown-preview">Loading preview...</div>
```

With a tabbed preview container that includes:

- `Runtime Model`
- `Markdown Preview`
- `Raw JSON`
- Existing `id="markdown-preview"` element retained for current JavaScript compatibility.
- A new `data-instruction-model-url="{{ url_for('api_get_instruction_model', app_id=app.id) }}"` hook.

- [ ] **Step 2: Add defensive client rendering**

Client behavior:

- Load `/api/apps/<app_id>/instruction-model` only on the instructions tab.
- If the API fails, show an unavailable message.
- If missing/unconfigured, show a clear missing state.
- If ready, render summary cards and section counts.
- Render Raw JSON from `payload`.
- Never submit data from Runtime Model or Raw JSON controls.

Minimum displayed fields:

- status
- freshness
- primary service mode
- default workflow ID
- service block count
- procedure count
- procedure step count
- resource count
- semantic attached/valid

- [ ] **Step 3: Run UI/regression tests**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_instruction_model_support
```

Expected:

```text
OK
```

---

### Task 6: Add Full Builder Regression Checks

**Objective:** Ensure unrelated Builder capabilities still route and render after the instruction model work.

**Files:**

- Modify: `ragenius_builder/flask_scaffold/tests/test_instruction_model_support.py`

- [ ] **Step 1: Add route smoke tests**

Add a test that creates one app and asserts these GET routes still return non-error responses:

```python
routes = [
    f"/apps/{app_id}/config?tab=instructions",
    f"/apps/{app_id}/config?tab=settings",
    f"/apps/{app_id}/docs",
    f"/apps/{app_id}/search",
    "/skills",
]
for route in routes:
    response = client.get(route)
    self.assertLess(response.status_code, 500, route)
```

- [ ] **Step 2: Add API regression checks**

Assert existing instruction/settings APIs remain unchanged:

```python
self.assertEqual(client.get(f"/api/apps/{app_id}/instructions").status_code, 200)
self.assertEqual(client.get(f"/api/apps/{app_id}/settings").status_code, 200)
self.assertEqual(
    client.patch(
        f"/api/apps/{app_id}/instructions",
        json={"content": "# API Updated", "version": "v3", "uri": "instructions/app/instructions.md"},
    ).status_code,
    200,
)
```

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_instruction_model_support
```

Expected:

```text
OK
```

- [ ] **Step 4: Run existing Builder test suite**

Run:

```powershell
python -m unittest ragenius_builder.flask_scaffold.tests.test_skill_management
```

Expected:

```text
OK
```

---

### Task 7: Manual Local Verification

**Objective:** Verify actual Builder UI behavior without relying only on tests.

**Files:**

- No code files changed in this task.

- [ ] **Step 1: Start Builder with no instruction model snapshot root**

Run Builder as currently documented for `ragenius_builder/flask_scaffold`.

Expected:

- Application configuration page loads.
- Instructions editor works.
- Runtime Model panel shows unconfigured/missing state.
- Markdown Preview still updates.
- Settings tab still loads.

- [ ] **Step 2: Start Builder with snapshot root configured**

Example:

```powershell
$env:RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT="D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\.state\instruction_understanding_snapshots"
```

Expected:

- For an app ID with a matching snapshot, Runtime Model shows status and summary.
- Raw JSON shows the exact payload.
- If the Builder instruction content differs from compiled hash/version, freshness is stale or unknown, not silently current.

- [ ] **Step 3: Exercise unrelated Builder pages**

Manually verify:

- Apps list/detail.
- App instructions save.
- App settings save.
- Documents page.
- Search page.
- Skills list/detail/test pages.
- Admin subsystem page.

Expected:

- No new errors.
- No unrelated UI changes.
- No compile/run mutation triggered from the instruction config page.

---

## Must-Have For MVP

- Read-only adapter.
- Read-only API.
- Runtime Model tab.
- Markdown Preview preserved.
- Raw JSON tab.
- Freshness/status display.
- Missing/unconfigured/error states.
- Tests proving existing instruction/settings routes still work.
- Existing skill-management tests still pass.

## Defer Until Later

- Compile button.
- Review button.
- Approval workflow.
- Runtime DB adapter.
- Historical compile timeline.
- Diff between current and previous compiled models.
- Cross-linking every friendly card to exact JSON pointer.
- Editing compiled model fields.
- Integrating `ragenius_app`.
- Any end-user chat workflow.

## Acceptance Criteria

The implementation is accepted only when:

- Builder admin can open Application Configuration and see `Runtime Model`, `Markdown Preview`, and `Raw JSON` modes.
- Runtime Model is derived from `understanding.json` or equivalent compiled payload only.
- Raw JSON preserves the original runtime-produced artifact.
- Missing/unconfigured/stale/error states are explicit.
- Saving instructions still writes file-backed markdown through existing `DatabaseStore` behavior.
- Saving settings still uses the existing settings route and schema behavior.
- Uploads/docs/search/skills pages still route without server errors.
- No code under `ragenius_app`, `rag_subsystem`, `ragenius_execution_subsystem`, or `ragenius_app_skeleton` is modified for the MVP.
- No automatic compile or runtime mutation occurs on page load.

## Recommended Commit Sequence

1. `test: add instruction model adapter contract tests`
2. `feat: add read-only instruction model adapter`
3. `feat: expose builder instruction model read API`
4. `feat: add instruction model preview modes`
5. `test: add builder regression coverage for instruction model support`

## Stop Conditions

Stop and ask before continuing if:

- The implementation requires modifying `ragenius_app_skeleton` runtime code.
- Builder and app-skeleton app IDs cannot be mapped for real data.
- Existing instruction save behavior must be changed to compute freshness.
- Existing settings or upload tests fail for unrelated reasons.
- The only way to get a model is to invoke runtime compile implicitly on page load.
