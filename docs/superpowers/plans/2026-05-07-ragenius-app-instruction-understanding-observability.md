# RAGenius App Instruction Understanding Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add app-side admin endpoints and UI surfaces for compiled instruction-understanding detail, explicit recompile/review actions, and shared backend payload assembly without changing ordinary page-load behavior.

**Architecture:** Extend the existing app admin backend with one detail endpoint and two explicit mutation endpoints, backed by shared understanding-detail helpers layered on top of the existing persistence/review service. Reuse the existing `Instructions` and `Runtime` admin tabs in the React app, keeping the turn-level inspector unchanged and introducing only the minimum frontend state/actions needed to inspect and control app-level understanding.

**Tech Stack:** Python 3, FastAPI, SQLite persistence via existing repos, React 18, Vite, unittest, Vitest + React Testing Library for the new frontend component tests.

---

## File Structure

### Backend routes and services
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py`
  - add shared detail-payload helper and explicit force action helpers
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
  - add detail/recompile/review endpoints and reuse shared payload assembly

### Backend tests
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`
  - add route coverage for detail and force action endpoints
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`
  - add direct helper coverage for detail assembly and force actions

### Frontend components
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\InstructionsPanel.jsx`
  - show status, detail payload, actions, summary, and findings
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimePanel.jsx`
  - show compact understanding status and detail load action
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx`
  - only if small shared styles/helpers are needed for new panels

### Frontend test harness
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\package.json`
  - add test dependencies and scripts
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\vitest.config.js`
  - Vitest jsdom config
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\test\setup.js`
  - testing-library setup
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\InstructionsPanel.test.jsx`
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimePanel.test.jsx`

---

### Task 1: Add Shared Backend Helpers For Understanding Detail And Force Actions

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
def test_load_instruction_understanding_detail_returns_compiled_and_review_sections(self):
    repo = InstructionUnderstandingRepo(self.db_path)
    compiled = repo.save_compiled(
        app_id="app-1",
        instruction_source_hash="hash-1",
        instruction_source_version=1,
        instruction_uri="instructions/app-1/instructions.md",
        parser_contract_version=PARSER_CONTRACT_VERSION,
        binding_logic_version=BINDING_LOGIC_VERSION,
        resource_catalog_hash="resources-1",
        compiled_status="ready",
        compile_duration_ms=12,
        compile_errors=[],
        compiled_contract={"instruction_service_blocks": [{"block_id": "workflow:default"}]},
        metadata={"service_block_count": 1},
    )
    review = repo.save_review(
        app_id="app-1",
        instruction_source_hash="hash-1",
        parser_contract_version=PARSER_CONTRACT_VERSION,
        review_model="planner-model",
        review_prompt_version=REVIEW_PROMPT_VERSION,
        review_status="reviewed_ok",
        review_confidence=0.9,
        review_findings={"default_workflow_assessment": {"status": "ok"}},
        review_summary_md="# Review\n\nLooks good.",
        review_recommendations={"next_steps": []},
    )

    detail = load_instruction_understanding_detail(
        app_id="app-1",
        instructions={"content": "# Hello", "uri": "instructions/app-1/instructions.md", "version": 1},
        documents=[],
        repo=repo,
    )

    self.assertEqual(detail["compiled_status"], "ready")
    self.assertEqual(detail["review_status"], "reviewed_ok")
    self.assertEqual(detail["compiled_record_meta"]["instruction_uri"], compiled["instruction_uri"])
    self.assertEqual(detail["review_record_meta"]["review_model"], review["review_model"])
    self.assertEqual(detail["review_summary_md"], "# Review\n\nLooks good.")

def test_force_review_instruction_understanding_raises_when_no_reviewer(self):
    repo = InstructionUnderstandingRepo(self.db_path)
    repo.save_compiled(
        app_id="app-1",
        instruction_source_hash="hash-1",
        instruction_source_version=1,
        instruction_uri="instructions/app-1/instructions.md",
        parser_contract_version=PARSER_CONTRACT_VERSION,
        binding_logic_version=BINDING_LOGIC_VERSION,
        resource_catalog_hash="resources-1",
        compiled_status="ready",
        compile_duration_ms=12,
        compile_errors=[],
        compiled_contract={"instruction_service_blocks": []},
        metadata={},
    )

    with self.assertRaisesRegex(RuntimeError, "No instruction understanding reviewer available"):
        force_review_instruction_understanding(
            app_id="app-1",
            repo=repo,
            reviewer=None,
        )
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: FAIL with missing `load_instruction_understanding_detail` / `force_review_instruction_understanding`.

- [ ] **Step 3: Add shared detail and force-action helpers**

```python
def load_instruction_understanding_detail(
    *,
    app_id: str,
    instructions: Dict[str, Any],
    documents: list[dict[str, Any]],
    repo: InstructionUnderstandingRepo,
    parser_contract_version: str = PARSER_CONTRACT_VERSION,
    binding_logic_version: str = BINDING_LOGIC_VERSION,
) -> dict[str, Any]:
    instruction_source_hash = compute_instruction_source_hash(str(instructions.get("content") or ""))
    resource_catalog_hash = compute_resource_catalog_hash(documents)
    compiled = repo.get_active_compiled(app_id)
    review = repo.get_active_review(app_id)
    cache = evaluate_instruction_understanding_cache(
        compiled,
        instruction_source_hash=instruction_source_hash,
        parser_contract_version=parser_contract_version,
        binding_logic_version=binding_logic_version,
        resource_catalog_hash=resource_catalog_hash,
    )
    return {
        "app_id": app_id,
        "compiled_status": compiled.get("compiled_status") if isinstance(compiled, dict) else None,
        "review_status": review.get("review_status") if isinstance(review, dict) else "not_reviewed",
        "cache_status": cache["cache_status"],
        "stale_reasons": cache["stale_reasons"],
        "instruction_source_hash": instruction_source_hash,
        "parser_contract_version": parser_contract_version,
        "binding_logic_version": binding_logic_version,
        "resource_catalog_hash": resource_catalog_hash,
        "compiled_record_meta": {
            "compiled_at": compiled.get("compiled_at") if isinstance(compiled, dict) else None,
            "compile_duration_ms": compiled.get("compile_duration_ms") if isinstance(compiled, dict) else None,
            "instruction_source_version": compiled.get("instruction_source_version") if isinstance(compiled, dict) else None,
            "instruction_uri": compiled.get("instruction_uri") if isinstance(compiled, dict) else None,
            "metadata": compiled.get("metadata", {}) if isinstance(compiled, dict) else {},
        },
        "review_record_meta": {
            "reviewed_at": review.get("reviewed_at") if isinstance(review, dict) else None,
            "review_model": review.get("review_model") if isinstance(review, dict) else None,
            "review_prompt_version": review.get("review_prompt_version") if isinstance(review, dict) else None,
            "review_confidence": review.get("review_confidence") if isinstance(review, dict) else None,
        },
        "review_summary_md": review.get("review_summary_md") if isinstance(review, dict) else "",
        "review_findings": review.get("review_findings", {}) if isinstance(review, dict) else {},
        "review_recommendations": review.get("review_recommendations", {}) if isinstance(review, dict) else {},
    }


def force_review_instruction_understanding(
    *,
    app_id: str,
    repo: InstructionUnderstandingRepo,
    reviewer: Optional[Callable[[dict[str, Any]], dict[str, Any]]],
    review_model: str | None = None,
    review_prompt_version: str = REVIEW_PROMPT_VERSION,
) -> dict[str, Any]:
    compiled = repo.get_active_compiled(app_id)
    if not isinstance(compiled, dict):
        raise LookupError("No compiled instruction understanding available")
    if reviewer is None:
        raise RuntimeError("No instruction understanding reviewer available")
    return review_instruction_understanding(
        app_id=app_id,
        compiled_record=compiled,
        repo=repo,
        reviewer=reviewer,
        review_model=review_model,
        review_prompt_version=review_prompt_version,
    )
```

- [ ] **Step 4: Add explicit force-recompile helper**

```python
def force_recompile_instruction_understanding(
    *,
    app_id: str,
    instructions: Dict[str, Any],
    documents: list[dict[str, Any]],
    repo: InstructionUnderstandingRepo,
    snapshot_root: Path,
    reviewer: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    review_model: str | None = None,
    review_prompt_version: str = REVIEW_PROMPT_VERSION,
) -> dict[str, Any]:
    record = compile_instruction_understanding(
        app_id=app_id,
        instruction_text=str(instructions.get("content") or ""),
        instruction_uri=str(instructions.get("uri") or "") or None,
        instruction_source_version=instructions.get("version"),
        documents=documents,
        repo=repo,
        snapshot_root=snapshot_root,
    )
    if reviewer is not None:
        review_instruction_understanding(
            app_id=app_id,
            compiled_record=record,
            repo=repo,
            reviewer=reviewer,
            review_model=review_model,
            review_prompt_version=review_prompt_version,
        )
    return record
```

- [ ] **Step 5: Run the service tests to verify they pass**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: PASS for new detail/helper tests.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/backend/app/instruction_understanding_service.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "feat: add instruction understanding detail helpers"
```

---

### Task 2: Add Admin Detail And Force Action Endpoints

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`

- [ ] **Step 1: Write the failing route tests**

```python
def test_instruction_understanding_detail_endpoint_returns_review_payload(self):
    db_path, _ = _create_builder_db(str(self.tmp_root))

    with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
        response = self.client.get("/apps/app-1/instruction-understanding", headers={"x-role": "admin"})

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertEqual(payload["app_id"], "app-1")
    self.assertIn("compiled_record_meta", payload)
    self.assertIn("review_record_meta", payload)
    self.assertIn("review_summary_md", payload)
    self.assertIn("review_findings", payload)

def test_instruction_understanding_review_endpoint_returns_409_without_reviewer(self):
    db_path, _ = _create_builder_db(str(self.tmp_root))

    with mock.patch.dict(os.environ, {"RAGENIUS_BUILDER_DB": db_path}, clear=False):
        response = self.client.post("/apps/app-1/instruction-understanding/review", headers={"x-role": "admin"})

    self.assertEqual(response.status_code, 409)
    self.assertIn("No instruction understanding reviewer available", response.text)
```

- [ ] **Step 2: Run the route tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration -v
```

Expected: FAIL with missing routes.

- [ ] **Step 3: Add the new endpoints and shared payload usage**

```python
@app.get("/apps/{app_id}/instruction-understanding")
async def get_instruction_understanding_detail(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    context = _load_builder_context(app_id)
    return load_instruction_understanding_detail(
        app_id=app_id,
        instructions=context["instructions"],
        documents=context["documents"],
        repo=instruction_understanding_repo,
    )


@app.post("/apps/{app_id}/instruction-understanding/recompile")
async def recompile_instruction_understanding(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    context = _load_builder_context(app_id)
    reviewer = build_instruction_understanding_reviewer(
        {
            "config_json": context["config_json"],
            "adapter_json": context["adapter_json"],
            "template_registry": {
                "builder_app": context["app"],
                "builder_instructions": str(context["instructions"].get("content") or ""),
                "builder_documents": context["documents"],
            },
        }
    )
    force_recompile_instruction_understanding(
        app_id=app_id,
        instructions=context["instructions"],
        documents=context["documents"],
        repo=instruction_understanding_repo,
        snapshot_root=get_builder_store().db_path.parent / "instruction_understanding",
        reviewer=reviewer,
    )
    return load_instruction_understanding_detail(
        app_id=app_id,
        instructions=context["instructions"],
        documents=context["documents"],
        repo=instruction_understanding_repo,
    )


@app.post("/apps/{app_id}/instruction-understanding/review")
async def rerun_instruction_understanding_review(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    context = _load_builder_context(app_id)
    reviewer = build_instruction_understanding_reviewer(
        {
            "config_json": context["config_json"],
            "adapter_json": context["adapter_json"],
            "template_registry": {
                "builder_app": context["app"],
                "builder_instructions": str(context["instructions"].get("content") or ""),
                "builder_documents": context["documents"],
            },
        }
    )
    try:
        force_review_instruction_understanding(
            app_id=app_id,
            repo=instruction_understanding_repo,
            reviewer=reviewer,
        )
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return load_instruction_understanding_detail(
        app_id=app_id,
        instructions=context["instructions"],
        documents=context["documents"],
        repo=instruction_understanding_repo,
    )
```

- [ ] **Step 4: Enrich existing instructions/runtime endpoints with preview payloads**

```python
detail = load_instruction_understanding_detail(
    app_id=app_id,
    instructions=instructions,
    documents=context["documents"],
    repo=instruction_understanding_repo,
)
preview = {
    "compiled_status": detail["compiled_status"],
    "review_status": detail["review_status"],
    "cache_status": detail["cache_status"],
    "stale_reasons": detail["stale_reasons"],
    "review_confidence": detail["review_record_meta"].get("review_confidence"),
}
```

Add `instruction_understanding_preview=preview` to both `GET /apps/{app_id}/instructions` and `GET /apps/{app_id}/runtime`.

- [ ] **Step 5: Run the route tests to verify they pass**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration -v
```

Expected: PASS for the new detail/review/recompile route tests.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/backend/app/main.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "feat: add app instruction understanding admin endpoints"
```

---

### Task 3: Add Frontend Test Harness For Admin Panels

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\package.json`
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\vitest.config.js`
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\test\setup.js`

- [ ] **Step 1: Add the failing test script entry**

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  }
}
```

- [ ] **Step 2: Run the frontend test command to verify it fails**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm test
```

Expected: FAIL because `vitest` is not installed yet.

- [ ] **Step 3: Add the frontend test dependencies and config**

```json
{
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.6.1",
    "@vitejs/plugin-react": "^4.3.4",
    "jsdom": "^25.0.1",
    "vite": "^5.4.11",
    "vitest": "^2.1.5"
  }
}
```

```javascript
// vitest.config.js
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
  },
});
```

```javascript
// src/test/setup.js
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Install dependencies and run the test command again**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm install; npm test
```

Expected: PASS with zero or no-op tests before component tests are added.

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/frontend/package.json ragenius_app_skeleton/frontend/vitest.config.js ragenius_app_skeleton/frontend/src/test/setup.js
git commit -m "test: add frontend test harness for admin panels"
```

---

### Task 4: Extend InstructionsPanel With Understanding Detail And Force Actions

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\InstructionsPanel.jsx`
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\InstructionsPanel.test.jsx`

- [ ] **Step 1: Write the failing component tests**

```jsx
it("renders review summary and findings after loading understanding detail", async () => {
  const fetchJson = vi.fn()
    .mockResolvedValueOnce({
      instructions: { version: "v1", checksum: "abc", content: "# Hello" },
      instruction_understanding_status: { compiled_status: "ready", review_status: "reviewed_ok", cache_status: "hot" },
      instruction_understanding_preview: { review_confidence: 0.9 },
    })
    .mockResolvedValueOnce({
      compiled_status: "ready",
      review_status: "reviewed_ok",
      cache_status: "hot",
      stale_reasons: [],
      review_summary_md: "# Review\n\nLooks good.",
      review_findings: { warnings: ["none"], classification_findings: ["ok"] },
      review_record_meta: { review_confidence: 0.9 },
      compiled_record_meta: { compiled_at: "2026-05-07T00:00:00Z" },
    });

  render(<InstructionsPanel baseUrl="http://app" builderBaseUrl="http://builder" builderAvailable={false} appId="app-1" styles={styles} fetchJson={fetchJson} />);
  await userEvent.click(screen.getByRole("button", { name: /load instructions/i }));
  await userEvent.click(screen.getByRole("button", { name: /load understanding/i }));

  expect(await screen.findByText(/looks good/i)).toBeInTheDocument();
  expect(screen.getByText(/classification_findings/i)).toBeInTheDocument();
});

it("shows empty review state when no review exists", async () => {
  const fetchJson = vi.fn()
    .mockResolvedValueOnce({
      instructions: { version: "v1", checksum: "abc", content: "# Hello" },
      instruction_understanding_status: { compiled_status: "ready", review_status: "not_reviewed", cache_status: "hot" },
      instruction_understanding_preview: {},
    })
    .mockResolvedValueOnce({
      compiled_status: "ready",
      review_status: "not_reviewed",
      cache_status: "hot",
      stale_reasons: [],
      review_summary_md: "",
      review_findings: {},
      review_record_meta: {},
      compiled_record_meta: {},
    });

  render(<InstructionsPanel baseUrl="http://app" builderBaseUrl="http://builder" builderAvailable={false} appId="app-1" styles={styles} fetchJson={fetchJson} />);
  await userEvent.click(screen.getByRole("button", { name: /load instructions/i }));
  await userEvent.click(screen.getByRole("button", { name: /load understanding/i }));

  expect(await screen.findByText(/no review available/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the component tests to verify they fail**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm test -- InstructionsPanel.test.jsx
```

Expected: FAIL because the component does not yet render understanding detail or action buttons.

- [ ] **Step 3: Add local state and actions for understanding detail**

```jsx
const [understanding, setUnderstanding] = useState(null);
const [understandingLoading, setUnderstandingLoading] = useState(false);
const [understandingError, setUnderstandingError] = useState("");

const loadUnderstanding = async () => {
  if (!appId) return;
  setUnderstandingLoading(true);
  setUnderstandingError("");
  try {
    const data = await fetchJson(`${baseUrl}/apps/${appId}/instruction-understanding`, {
      headers: { "x-role": "admin" },
    });
    setUnderstanding(data);
  } catch (e) {
    setUnderstandingError(String(e.message || e));
  } finally {
    setUnderstandingLoading(false);
  }
};
```

- [ ] **Step 4: Render status, summary, findings, and control row**

```jsx
<div style={{ ...styles.row, marginTop: 14 }}>
  <button style={styles.secondaryButton} onClick={loadUnderstanding} disabled={!appId || understandingLoading}>
    {understandingLoading ? "Loading..." : "Load Understanding"}
  </button>
  <button style={styles.secondaryButton} onClick={refreshUnderstanding} disabled={!appId || understandingLoading}>
    Refresh Understanding
  </button>
  <button style={styles.secondaryButton} onClick={runReview} disabled={!appId || understandingLoading}>
    Run Review
  </button>
</div>
{understanding && (
  <div style={{ marginTop: 16 }}>
    <div style={styles.row}>
      <span style={styles.pill}>Compiled: {understanding.compiled_status || "n/a"}</span>
      <span style={styles.pill}>Review: {understanding.review_status || "n/a"}</span>
      <span style={styles.pill}>Cache: {understanding.cache_status || "n/a"}</span>
    </div>
    <div style={{ marginTop: 16 }}>
      <div style={styles.label}>Review Summary</div>
      <div style={styles.code}>{understanding.review_summary_md || "No review available"}</div>
    </div>
    <div style={{ marginTop: 16 }}>
      <div style={styles.label}>Structured Findings</div>
      <div style={styles.code}>{JSON.stringify(understanding.review_findings || {}, null, 2)}</div>
    </div>
  </div>
)}
```

- [ ] **Step 5: Run the component tests to verify they pass**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm test -- InstructionsPanel.test.jsx
```

Expected: PASS for summary, findings, and empty-state rendering.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/frontend/src/components/InstructionsPanel.jsx ragenius_app_skeleton/frontend/src/components/InstructionsPanel.test.jsx
git commit -m "feat: show instruction understanding detail in instructions panel"
```

---

### Task 5: Extend RuntimePanel With Compact Understanding Status

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimePanel.jsx`
- Create: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimePanel.test.jsx`

- [ ] **Step 1: Write the failing RuntimePanel tests**

```jsx
it("renders compact instruction understanding status from runtime payload", async () => {
  const fetchJson = vi.fn().mockResolvedValue({
    provider: "openai",
    domain: "bible",
    config_summary: { goal_count: 2 },
    adapter_summary: { guardrail_count: 1 },
    models: {},
    instruction_understanding_status: {
      compiled_status: "ready",
      review_status: "reviewed_with_warnings",
      cache_status: "hot",
      stale_reasons: [],
    },
    instruction_understanding_preview: {
      review_confidence: 0.7,
    },
  });

  render(<RuntimePanel baseUrl="http://app" builderBaseUrl="http://builder" builderAvailable={false} appId="app-1" styles={styles} fetchJson={fetchJson} />);
  await userEvent.click(screen.getByRole("button", { name: /load runtime summary/i }));

  expect(await screen.findByText(/compiled: ready/i)).toBeInTheDocument();
  expect(screen.getByText(/review: reviewed_with_warnings/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the RuntimePanel tests to verify they fail**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm test -- RuntimePanel.test.jsx
```

Expected: FAIL because the compact status is not rendered yet.

- [ ] **Step 3: Render compact status and detail hint in RuntimePanel**

```jsx
{payload?.instruction_understanding_status && (
  <div style={{ marginTop: 16 }}>
    <div style={styles.label}>Instruction Understanding</div>
    <div style={styles.row}>
      <span style={styles.pill}>Compiled: {payload.instruction_understanding_status.compiled_status || "n/a"}</span>
      <span style={styles.pill}>Review: {payload.instruction_understanding_status.review_status || "n/a"}</span>
      <span style={styles.pill}>Cache: {payload.instruction_understanding_status.cache_status || "n/a"}</span>
    </div>
    {payload.instruction_understanding_preview?.review_confidence != null && (
      <div style={styles.compactNote}>
        Review confidence: {payload.instruction_understanding_preview.review_confidence}
      </div>
    )}
  </div>
)}
```

- [ ] **Step 4: Run the RuntimePanel tests to verify they pass**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm test -- RuntimePanel.test.jsx
```

Expected: PASS for compact status rendering.

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/frontend/src/components/RuntimePanel.jsx ragenius_app_skeleton/frontend/src/components/RuntimePanel.test.jsx
git commit -m "feat: add compact understanding status to runtime panel"
```

---

### Task 6: Run End-To-End Verification

**Files:**
- Verify only

- [ ] **Step 1: Run backend route and service suites**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service ragenius_app_skeleton.tests.test_builder_chat_integration -v
```

Expected: PASS for understanding-detail and force-action coverage.

- [ ] **Step 2: Run frontend component suites**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm test -- InstructionsPanel.test.jsx RuntimePanel.test.jsx
```

Expected: PASS for panel status, summary, findings, and action-state coverage.

- [ ] **Step 3: Run the full backend discovery suite**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest discover -s ragenius_app_skeleton/tests -p 'test_*.py' -v
```

Expected: PASS with all backend tests green and no hangs.

- [ ] **Step 4: Build the frontend**

Run:
```powershell
Set-Location 'C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend'; npm run build
```

Expected: PASS with a Vite production build.

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add app-side instruction understanding observability"
```

---

## Self-Review

### Spec coverage
- Detail endpoint: covered in Task 2
- Force recompile/review endpoints: covered in Tasks 1 and 2
- Existing panel extension instead of new tab: covered in Tasks 4 and 5
- Shared backend status/detail assembly: covered in Task 1 and Task 2
- Explicit frontend test harness and panel tests: covered in Tasks 3, 4, and 5
- Ordinary page-load behavior remains read-only: enforced by endpoint design in Task 2 and panel button-driven behavior in Tasks 4 and 5

### Placeholder scan
- No `TODO`, `TBD`, or deferred “write tests later” steps remain
- Each code-modifying task includes concrete code snippets and exact commands

### Type consistency
- Helper names are consistent across tasks:
  - `load_instruction_understanding_detail`
  - `force_recompile_instruction_understanding`
  - `force_review_instruction_understanding`
- Response payload fields match the approved spec:
  - `compiled_record_meta`
  - `review_record_meta`
  - `review_summary_md`
  - `review_findings`
  - `review_recommendations`

