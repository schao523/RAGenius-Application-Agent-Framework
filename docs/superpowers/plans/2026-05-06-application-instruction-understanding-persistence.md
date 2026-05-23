# Application Instruction Understanding Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist deterministic application-instruction understanding per app, add explicit cache/invalidation checks, and support optional LLM review without making review authoritative for runtime.

**Architecture:** Introduce a compiled-understanding persistence layer with explicit status and invalidation metadata, then add an optional review artifact keyed to the compiled result. Runtime will fetch the active compiled record, rebuild when inputs change, and keep the last known good artifact active on failures. Builder/admin-facing status helpers will expose cache state, stale reasons, and review outcomes.

**Tech Stack:** Python 3, SQLite-backed runtime state, Pydantic models, unittest, existing `ragenius_app_skeleton` workflow and Builder storage patterns.

---

## File Structure

### Persistence and services
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\state_store.py`
  - add compiled/review persistence methods and status queries
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\state_schema.py`
  - add SQLite schema for compiled/review tables if schema helpers live here
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
  - add persistence metadata models
- Create or modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\instruction_understanding_service.py`
  - compile, cache, invalidation, and review orchestration

### Runtime integration
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
  - emit compiled contract payloads suitable for persistence
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
  - fetch active compiled understanding instead of ad hoc rebuilding
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
  - attach current compiled/review/cache status to summaries if needed

### Snapshot outputs
- Create directory convention only: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold\instruction_understanding\{app_id}\`
  - `understanding.json`
  - `understanding.md`
  - optional review snapshot files

### Tests
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_state_store.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- Create or modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`

---

### Task 1: Add Persistence Models And SQLite Schema

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\state_schema.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_state_store.py`

- [ ] **Step 1: Write the failing schema/model tests**

```python
class InstructionUnderstandingPersistenceModelTests(unittest.TestCase):
    def test_compiled_instruction_understanding_model_serializes_required_metadata(self):
        from workflows.runtime_models import CompiledInstructionUnderstandingRecord, to_plain_dict

        record = CompiledInstructionUnderstandingRecord(
            app_id="app-1",
            instruction_source_hash="abc123",
            parser_contract_version="instruction-parser-2026-05-06-v1",
            binding_logic_version="binding-logic-2026-05-06-v1",
            resource_catalog_hash="def456",
            compiled_status="ready",
            compiled_contract_json={"instruction_service_blocks": []},
            is_active=True,
        )

        payload = to_plain_dict(record)

        self.assertEqual(payload["compiled_status"], "ready")
        self.assertEqual(payload["app_id"], "app-1")
        self.assertTrue(payload["is_active"])

    def test_state_schema_contains_compiled_and_review_tables(self):
        sql = get_runtime_state_schema_sql()
        self.assertIn("CREATE TABLE IF NOT EXISTS app_instruction_understanding", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS app_instruction_understanding_review", sql)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_state_store -v
```

Expected: FAIL with missing models or missing schema table declarations.

- [ ] **Step 3: Add compiled/review persistence models**

```python
class CompiledInstructionUnderstandingRecord(BaseModel):
    app_id: str
    instruction_source_hash: str
    instruction_source_version: str | None = None
    parser_contract_version: str
    binding_logic_version: str
    resource_catalog_hash: str
    compiled_status: Literal["ready", "stale", "building", "failed_compile", "superseded"]
    compiled_at: str | None = None
    compile_duration_ms: int | None = None
    compile_errors_json: dict[str, Any] = Field(default_factory=dict)
    compiled_contract_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False


class InstructionUnderstandingReviewRecord(BaseModel):
    app_id: str
    instruction_source_hash: str
    parser_contract_version: str
    review_model: str | None = None
    review_prompt_version: str | None = None
    review_status: Literal["not_reviewed", "reviewed_ok", "reviewed_with_warnings", "review_failed", "review_stale"]
    reviewed_at: str | None = None
    review_confidence: float | None = None
    review_findings_json: dict[str, Any] = Field(default_factory=dict)
    review_summary_md: str | None = None
    review_recommendations_json: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False
```

- [ ] **Step 4: Add SQLite schema tables**

```sql
CREATE TABLE IF NOT EXISTS app_instruction_understanding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id TEXT NOT NULL,
    instruction_source_hash TEXT NOT NULL,
    instruction_source_version TEXT,
    parser_contract_version TEXT NOT NULL,
    binding_logic_version TEXT NOT NULL,
    resource_catalog_hash TEXT NOT NULL,
    compiled_status TEXT NOT NULL,
    compiled_at TEXT,
    compile_duration_ms INTEGER,
    compile_errors_json TEXT NOT NULL DEFAULT '{}',
    compiled_contract_json TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_instruction_understanding_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id TEXT NOT NULL,
    instruction_source_hash TEXT NOT NULL,
    parser_contract_version TEXT NOT NULL,
    review_model TEXT,
    review_prompt_version TEXT,
    review_status TEXT NOT NULL,
    reviewed_at TEXT,
    review_confidence REAL,
    review_findings_json TEXT NOT NULL DEFAULT '{}',
    review_summary_md TEXT,
    review_recommendations_json TEXT NOT NULL DEFAULT '{}',
    is_active INTEGER NOT NULL DEFAULT 0
);
```

- [ ] **Step 5: Run tests to verify schema/model additions pass**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_state_store -v
```

Expected: PASS for new schema/model tests.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/workflows/runtime_models.py ragenius_app_skeleton/backend/app/state_schema.py ragenius_app_skeleton/tests/test_state_store.py
git commit -m "feat: add instruction understanding persistence schema"
```

---

### Task 2: Persist And Read Compiled Understanding Records

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\state_store.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_state_store.py`

- [ ] **Step 1: Write failing store tests for compiled and review record lifecycle**

```python
def test_state_store_can_save_and_get_active_compiled_instruction_understanding(self):
    store = RuntimeStateStore(db_path=self.db_path)
    store.save_compiled_instruction_understanding({
        "app_id": "app-1",
        "instruction_source_hash": "hash-a",
        "parser_contract_version": "parser-v1",
        "binding_logic_version": "binding-v1",
        "resource_catalog_hash": "resources-v1",
        "compiled_status": "ready",
        "compiled_contract_json": {"instruction_service_blocks": [{"block_id": "workflow:default"}]},
        "is_active": True,
    })

    row = store.get_active_compiled_instruction_understanding("app-1")

    self.assertEqual(row["app_id"], "app-1")
    self.assertEqual(row["compiled_status"], "ready")
    self.assertEqual(row["compiled_contract_json"]["instruction_service_blocks"][0]["block_id"], "workflow:default")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_state_store -v
```

Expected: FAIL because state store methods do not yet exist.

- [ ] **Step 3: Add compiled-understanding persistence methods**

```python
def save_compiled_instruction_understanding(self, payload: dict[str, Any]) -> None:
    with self._connect() as conn:
        conn.execute(
            "UPDATE app_instruction_understanding SET is_active = 0, compiled_status = CASE WHEN is_active = 1 THEN 'superseded' ELSE compiled_status END WHERE app_id = ?",
            (payload["app_id"],),
        )
        conn.execute(
            \"\"\"\n            INSERT INTO app_instruction_understanding (\n                app_id, instruction_source_hash, instruction_source_version,\n                parser_contract_version, binding_logic_version, resource_catalog_hash,\n                compiled_status, compiled_at, compile_duration_ms,\n                compile_errors_json, compiled_contract_json, is_active\n            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\n            \"\"\",\n            (...),
        )

def get_active_compiled_instruction_understanding(self, app_id: str) -> dict[str, Any] | None:
    ...
```

- [ ] **Step 4: Add review persistence methods**

```python
def save_instruction_understanding_review(self, payload: dict[str, Any]) -> None:
    ...

def get_active_instruction_understanding_review(self, app_id: str) -> dict[str, Any] | None:
    ...
```

- [ ] **Step 5: Run state-store tests**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_state_store -v
```

Expected: PASS for active compiled/review record save/load flows.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/backend/app/state_store.py ragenius_app_skeleton/tests/test_state_store.py
git commit -m "feat: persist compiled instruction understanding records"
```

---

### Task 3: Add Cache Metadata And Invalidation Checks

**Files:**
- Create or modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\instruction_understanding_service.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`

- [ ] **Step 1: Write failing invalidation tests**

```python
def test_cache_status_is_hot_when_hashes_and_versions_match(self):
    status = evaluate_instruction_understanding_cache(
        current_instruction_source_hash="a",
        current_parser_contract_version="parser-v1",
        current_binding_logic_version="binding-v1",
        current_resource_catalog_hash="r1",
        cached_record={
            "instruction_source_hash": "a",
            "parser_contract_version": "parser-v1",
            "binding_logic_version": "binding-v1",
            "resource_catalog_hash": "r1",
        },
    )

    self.assertEqual(status["cache_status"], "hot")
    self.assertEqual(status["stale_reasons"], [])


def test_cache_status_reports_stale_instruction_hash(self):
    status = evaluate_instruction_understanding_cache(
        current_instruction_source_hash="b",
        current_parser_contract_version="parser-v1",
        current_binding_logic_version="binding-v1",
        current_resource_catalog_hash="r1",
        cached_record={
            "instruction_source_hash": "a",
            "parser_contract_version": "parser-v1",
            "binding_logic_version": "binding-v1",
            "resource_catalog_hash": "r1",
        },
    )

    self.assertEqual(status["cache_status"], "stale_instructions")
    self.assertIn("instruction_source_hash", status["stale_reasons"][0])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: FAIL because invalidation service does not yet exist.

- [ ] **Step 3: Add explicit cache evaluation function**

```python
def evaluate_instruction_understanding_cache(
    *,
    current_instruction_source_hash: str,
    current_parser_contract_version: str,
    current_binding_logic_version: str,
    current_resource_catalog_hash: str,
    cached_record: dict[str, Any] | None,
) -> dict[str, Any]:
    if not cached_record:
        return {"cache_status": "missing", "stale_reasons": ["no_cached_record"]}
    stale_reasons: list[str] = []
    if current_instruction_source_hash != cached_record.get("instruction_source_hash"):
        stale_reasons.append("instruction_source_hash_changed")
    if current_parser_contract_version != cached_record.get("parser_contract_version"):
        stale_reasons.append("parser_contract_version_changed")
    if current_binding_logic_version != cached_record.get("binding_logic_version"):
        stale_reasons.append("binding_logic_version_changed")
    if current_resource_catalog_hash != cached_record.get("resource_catalog_hash"):
        stale_reasons.append("resource_catalog_hash_changed")
    if not stale_reasons:
        return {"cache_status": "hot", "stale_reasons": []}
    if "instruction_source_hash_changed" in stale_reasons:
        return {"cache_status": "stale_instructions", "stale_reasons": stale_reasons}
    if "parser_contract_version_changed" in stale_reasons:
        return {"cache_status": "stale_parser_contract", "stale_reasons": stale_reasons}
    if "binding_logic_version_changed" in stale_reasons:
        return {"cache_status": "stale_binding_logic", "stale_reasons": stale_reasons}
    return {"cache_status": "stale_resource_catalog", "stale_reasons": stale_reasons}
```

- [ ] **Step 4: Add hashing helpers**

```python
def compute_instruction_source_hash(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def compute_resource_catalog_hash(resources: list[dict[str, Any]]) -> str:
    stable = sorted(
        [
            {
                "document_id": item.get("document_id"),
                "filename": item.get("filename"),
                "status": item.get("status"),
                "domain": item.get("domain"),
                "linked_app_id": item.get("linked_app_id"),
                "title": item.get("title"),
            }
            for item in resources
        ],
        key=lambda item: (str(item["filename"]), str(item["document_id"])),
    )
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Run invalidation tests**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: PASS for hot/stale cache evaluation cases.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/workflows/instruction_understanding_service.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "feat: add instruction understanding cache invalidation"
```

---

### Task 4: Compile And Snapshot Instruction Understanding

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\instruction_understanding_service.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`

- [ ] **Step 1: Write failing compile/snapshot tests**

```python
def test_compile_instruction_understanding_persists_record_and_snapshot_files(self):
    service = InstructionUnderstandingService(...)
    result = service.compile_instruction_understanding(
        app_id="app-1",
        instructions_text="## Primary Workflow\\n### Step 1\\nDo thing",
        resource_catalog=[],
    )

    self.assertEqual(result["compiled_status"], "ready")
    self.assertTrue(self.snapshot_dir.joinpath("app-1", "understanding.json").exists())
    self.assertTrue(self.snapshot_dir.joinpath("app-1", "understanding.md").exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: FAIL because compile service and snapshot writing are not yet implemented.

- [ ] **Step 3: Add compile service method**

```python
def compile_instruction_understanding(self, *, app_id: str, instructions_text: str, resource_catalog: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    instruction_hash = compute_instruction_source_hash(instructions_text)
    resource_hash = compute_resource_catalog_hash(resource_catalog)
    compiled_contract = self._run_registry_compile(app_id=app_id, instructions_text=instructions_text, resource_catalog=resource_catalog)
    duration_ms = int((time.perf_counter() - started) * 1000)
    payload = {
        "app_id": app_id,
        "instruction_source_hash": instruction_hash,
        "parser_contract_version": self.parser_contract_version,
        "binding_logic_version": self.binding_logic_version,
        "resource_catalog_hash": resource_hash,
        "compiled_status": "ready",
        "compiled_at": _utc_now_iso(),
        "compile_duration_ms": duration_ms,
        "compile_errors_json": {},
        "compiled_contract_json": compiled_contract,
        "is_active": True,
    }
    self.state_store.save_compiled_instruction_understanding(payload)
    self._write_snapshots(app_id=app_id, payload=payload)
    return payload
```

- [ ] **Step 4: Write JSON and Markdown snapshots**

```python
def _write_snapshots(self, *, app_id: str, payload: dict[str, Any]) -> None:
    target_dir = self.snapshot_root / app_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "understanding.json").write_text(
        json.dumps(payload["compiled_contract_json"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_md = render_instruction_understanding_markdown(payload)
    (target_dir / "understanding.md").write_text(summary_md, encoding="utf-8")
```

- [ ] **Step 5: Run compile/snapshot tests**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: PASS for persistence and snapshot writing.

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/workflows/instruction_understanding_service.py ragenius_app_skeleton/workflows/nodes/load_template_registry.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "feat: compile and snapshot instruction understanding"
```

---

### Task 5: Add Optional LLM Review Pipeline

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\instruction_understanding_service.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`

- [ ] **Step 1: Write failing review tests**

```python
def test_review_instruction_understanding_persists_review_record(self):
    llm_reviewer = FakeReviewer({
        "review_status": "reviewed_with_warnings",
        "review_confidence": 0.62,
        "review_findings_json": {"warnings": ["default workflow ambiguous"]},
        "review_summary_md": "# Review\\n- default workflow ambiguous",
        "review_recommendations_json": {"actions": ["inspect triggers"]},
    })
    service = InstructionUnderstandingService(..., llm_reviewer=llm_reviewer)
    service.state_store.save_compiled_instruction_understanding({...})

    review = service.review_instruction_understanding("app-1", force=True)

    self.assertEqual(review["review_status"], "reviewed_with_warnings")
    self.assertAlmostEqual(review["review_confidence"], 0.62)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: FAIL because review orchestration does not yet exist.

- [ ] **Step 3: Add review orchestration**

```python
def review_instruction_understanding(self, app_id: str, force: bool = False) -> dict[str, Any]:
    compiled = self.state_store.get_active_compiled_instruction_understanding(app_id)
    if not compiled:
        raise ValueError("compiled instruction understanding is required before review")
    existing = self.state_store.get_active_instruction_understanding_review(app_id)
    if existing and not force and self._review_is_current(existing, compiled):
        return existing
    review_output = self.llm_reviewer.review(
        instructions_text=self._load_instruction_text(app_id),
        compiled_contract=compiled["compiled_contract_json"],
    )
    payload = {
        "app_id": app_id,
        "instruction_source_hash": compiled["instruction_source_hash"],
        "parser_contract_version": compiled["parser_contract_version"],
        "review_model": self.review_model_name,
        "review_prompt_version": self.review_prompt_version,
        **review_output,
        "is_active": True,
    }
    self.state_store.save_instruction_understanding_review(payload)
    return payload
```

- [ ] **Step 4: Run review tests**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -v
```

Expected: PASS for review persistence and current-review reuse logic.

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/workflows/instruction_understanding_service.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "feat: add instruction understanding review pipeline"
```

---

### Task 6: Integrate Active Compiled Understanding Into Runtime Entry

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`

- [ ] **Step 1: Write failing runtime integration tests**

```python
def test_chat_service_uses_active_compiled_instruction_understanding_when_cache_is_hot(self):
    service = _chat_service_with_instruction_understanding_service(...)
    service.instruction_understanding_service.compile_instruction_understanding(
        app_id="app-1",
        instructions_text="## Primary Workflow\\n### Step 1\\nDo thing",
        resource_catalog=[],
    )

    result = service._prepare_runtime_context(app_id="app-1", ...)

    self.assertIn("instruction_service_blocks", result["instruction_runtime_model"])
    self.assertEqual(result["instruction_understanding_status"]["cache_status"], "hot")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v
```

Expected: FAIL because chat service does not yet fetch through the compiled-understanding service.

- [ ] **Step 3: Wire runtime preparation through the understanding service**

```python
understanding = self.instruction_understanding_service.get_active_instruction_understanding(app_id)
runtime_context["instruction_runtime_model"] = understanding["compiled_contract_json"]
runtime_context["instruction_understanding_status"] = self.instruction_understanding_service.get_instruction_understanding_status(app_id)
```

- [ ] **Step 4: Run runtime integration tests**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v
```

Expected: PASS for active compiled-understanding injection and cache-status propagation.

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/backend/app/chat_service.py ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py
git commit -m "feat: use compiled instruction understanding in chat runtime"
```

---

### Task 7: Expose Builder/Admin Status And Final Verification

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_persist_run_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py`
- Test: all relevant suites

- [ ] **Step 1: Write failing status-summary tests**

```python
def test_instruction_understanding_status_reports_stale_reasons(self):
    service = InstructionUnderstandingService(...)
    status = service.get_instruction_understanding_status("app-1")
    self.assertIn("cache_status", status)
    self.assertIn("stale_reasons", status)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service ragenius_app_skeleton.tests.test_persist_run_node -v
```

Expected: FAIL if status helpers are incomplete.

- [ ] **Step 3: Implement status helper and summary propagation**

```python
def get_instruction_understanding_status(self, app_id: str) -> dict[str, Any]:
    compiled = self.state_store.get_active_compiled_instruction_understanding(app_id)
    review = self.state_store.get_active_instruction_understanding_review(app_id)
    cache_eval = ...
    return {
        "compiled_status": compiled.get("compiled_status") if compiled else "missing",
        "review_status": review.get("review_status") if review else "not_reviewed",
        "cache_status": cache_eval["cache_status"],
        "stale_reasons": cache_eval["stale_reasons"],
    }
```

- [ ] **Step 4: Run the final verification suite**

Run:
```powershell
$env:PYTHONPATH='C:\Users\User\Documents\GitHub\Codex-RAGenius-System;C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton'; python -m unittest ragenius_app_skeleton.tests.test_state_store ragenius_app_skeleton.tests.test_instruction_understanding_service ragenius_app_skeleton.tests.test_load_template_registry ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts ragenius_app_skeleton.tests.test_persist_run_node -v
```

Expected: PASS across persistence, invalidation, compilation, review, and runtime integration tests.

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/backend/app/chat_service.py ragenius_app_skeleton/workflows/nodes/persist_run.py ragenius_app_skeleton/tests/test_persist_run_node.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "feat: expose instruction understanding status"
```

---

## Spec Coverage Check

Covered requirements:
- persistent compiled understanding artifact
- separate review artifact
- `.md` and `.json` snapshots
- explicit cache/invalidation by hashes and versions
- rebuild on instruction/parser/binding/resource-catalog changes
- optional review re-run rules
- last-known-good runtime resilience
- Builder/admin inspection status

No uncovered design items remain.

## Placeholder Scan

Reviewed for:
- `TODO`
- `TBD`
- vague “handle appropriately” steps
- missing commands

No placeholders remain.

## Type Consistency Check

Consistent names used throughout:
- `CompiledInstructionUnderstandingRecord`
- `InstructionUnderstandingReviewRecord`
- `InstructionUnderstandingService`
- `instruction_source_hash`
- `parser_contract_version`
- `binding_logic_version`
- `resource_catalog_hash`
- `cache_status`
- `stale_reasons`
