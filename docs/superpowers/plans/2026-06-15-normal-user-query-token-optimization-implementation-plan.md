# Normal User Query Token Optimization Implementation Plan

> **For agentic workers:** Execute task-by-task with test-first checkpoints. Do not enable compact mode by default until every parity and reduction gate in this plan passes.

**Goal:** Reduce aggregate DeepSeek input tokens by at least 40% for eligible normal text queries without changing planner routing, retrieval scope, evidence behavior, answer quality, citations, session persistence, upload analysis, exec turns, or other RAGenius subsystems.

**Architecture:** Calculate one optimization-eligibility decision at the normal-chat boundary, retain full `GraphState`, and build prompt-compatible compact projections only for eligible LLM calls. Diagnostic mode measures the exact full outbound payload and compact candidate while sending full context; compact mode sends the compact candidate after ordered budget stages. All changes remain inside `ragenius_app_skeleton`.

**Tech Stack:** Python, FastAPI, existing LangGraph-style workflow, Pydantic/jsonschema validators, pytest, current OpenAI-compatible DeepSeek client.

**Normative documents:**

- `docs/normal-user-query-token-optimization-contract.md`
- `docs/normal-user-query-token-optimization-design.md`

---

## File Map

Create:

- `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
  - Eligibility, modes, prompt-compatible projections, compaction stages, token estimation, evidence policy, real deterministic summaries, and diagnostics.
- `ragenius_app_skeleton/tests/test_llm_context_optimization.py`
  - Pure helper and projection tests.
- `ragenius_app_skeleton/tests/test_llm_context_optimization_integration.py`
  - Node/pipeline eligibility, diagnostic, compact, fallback, and persistence tests.
- `ragenius_app_skeleton/tests/test_llm_context_optimization_parity.py`
  - Full-versus-compact representative parity and token-reduction fixtures.

Modify:

- `ragenius_app_skeleton/backend/app/main.py`
  - Set optimization eligibility only in `_handle_normal_chat_turn(...)`; explicitly disable it for upload analysis.
- `ragenius_app_skeleton/backend/app/chat_service.py`
  - Propagate eligibility, initialize/aggregate diagnostics, and preserve existing response fields.
- `ragenius_app_skeleton/workflows/graph_state.py`
  - Add optional internal optimization state keys.
- `ragenius_app_skeleton/workflows/nodes/planner.py`
  - Use eligible planner/hybrid projections under existing prompt keys.
- `ragenius_app_skeleton/workflows/nodes/evidence_analysis.py`
  - Honor `auto|deterministic|llm_required` and compact only eligible calls.
- `ragenius_app_skeleton/workflows/nodes/answer.py`
  - Preserve every answer-critical logical key while compacting eligible values.
- `ragenius_app_skeleton/workflows/nodes/persist_run.py`
  - Refresh a real deterministic summary with the current completed turn before runtime-state persistence.
- `ragenius_app_skeleton/.env.example`
  - Document flags and safe defaults.

Never modify for this feature:

- `rag_subsystem/`
- `ragenius_builder/`
- `ragenius_app/`
- root compatibility shims
- function schemas
- frontend workflow-status contracts
- instruction-understanding compile/review/revision paths

---

### Task 1: Establish a Runnable Baseline

**Files:** No source changes.

- [ ] Confirm the selected Python environment contains runtime dependencies.

Run:

```powershell
.\.venv\Scripts\python.exe -c "import pydantic, jsonschema, fastapi; print('runtime dependencies available')"
```

Expected: prints `runtime dependencies available`.

- [ ] If dependencies are absent, install the existing backend requirements without changing requirement files.

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r ragenius_app_skeleton\backend\requirements.txt
```

Expected: installation completes successfully.

- [ ] Run the current focused baseline.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_runtime.py ragenius_app_skeleton\tests\test_planner_node.py ragenius_app_skeleton\tests\test_evidence_analysis.py ragenius_app_skeleton\tests\test_answer_node.py ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py ragenius_app_skeleton\tests\test_persist_run_node.py -q
```

Expected: all focused tests pass before implementation. Record any pre-existing failures before continuing.

- [ ] Capture baseline payload fixtures without real DeepSeek calls.

Add no code yet. Identify reusable state builders in the six focused test files for simple QA, workflow follow-up, Church Ministry, `與孩子一起成長`, missing evidence, out-of-scope, and upload analysis.

---

### Task 2: Add Eligibility, Modes, and Internal State Contracts

**Files:**

- Create: `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
- Create: `ragenius_app_skeleton/tests/test_llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/workflows/graph_state.py`
- Modify: `ragenius_app_skeleton/.env.example`

- [ ] Write failing eligibility and mode tests.

Tests must assert:

```python
def test_text_query_without_upload_events_is_eligible(): ...
def test_session_upload_is_not_eligible(): ...
def test_pending_upload_analysis_is_not_eligible(): ...
def test_upload_event_ids_make_turn_ineligible(): ...
def test_default_mode_is_off(): ...
def test_evidence_mode_defaults_to_auto(): ...
```

Required expectations:

```python
assert normal_query_optimization_eligible({
    "turn_input_type": "text_query",
    "pending_upload_analysis": False,
    "session_upload_event_ids": [],
}) is True

assert normal_query_optimization_eligible({
    "turn_input_type": "session_upload",
    "pending_upload_analysis": True,
    "session_upload_event_ids": ["upload-1"],
}) is False
```

- [ ] Run the new test file and confirm failure because the module is absent.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py -q
```

- [ ] Implement immutable policy types and helpers.

Required public interface:

```python
@dataclass(frozen=True)
class ContextOptimizationResult:
    context: dict[str, Any]
    diagnostics: dict[str, Any]
    budget_exceeded: bool = False
    skip_llm: bool = False
    skip_reason: str | None = None


def normal_query_optimization_eligible(state: Mapping[str, Any]) -> bool: ...
def context_optimization_mode() -> Literal["off", "diagnostic", "compact"]: ...
def evidence_analysis_mode() -> Literal["auto", "deterministic", "llm_required"]: ...
```

Eligibility must require `text_query`, no pending upload analysis, and no upload event ids.

- [ ] Add optional internal fields to `GraphState` and `GraphStateModel`:

```python
_context_optimization_eligible: bool
_context_optimization_mode: str
_context_optimization_diagnostics: Dict[str, Any]
_turn_token_accounting: Dict[str, Any]
```

- [ ] Document safe defaults in `.env.example`:

```text
RAGENIUS_LLM_CONTEXT_OPTIMIZATION=0
RAGENIUS_LLM_CONTEXT_OPTIMIZATION_MODE=off
RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE=auto
```

- [ ] Run tests and commit.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py -q
git add ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\workflows\graph_state.py ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\.env.example
git commit -m "feat: add normal query optimization eligibility"
```

---

### Task 3: Add Exact Payload Estimation and Turn Accounting

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_llm_context_optimization.py`

- [ ] Write failing estimator tests that compare against the same message construction used by `llm_runtime._build_messages`.

Required diagnostics:

```python
{
    "actual_full_tokens": int,
    "compact_candidate_tokens": int,
    "actual_outbound_tokens": int,
    "estimated_tokens_saved": int,
    "estimated_saving_percent": float,
    "estimator_name": "chars_per_token",
    "estimator_version": "v1",
    "budget_limit_tokens": int,
    "budget_exceeded": bool,
}
```

- [ ] Test diagnostic and compact outbound selection.

```python
diagnostic = optimize_task_context(
    task="planner",
    prompt="prompt",
    tools=[],
    full_context={"large": "x" * 1000},
    compact_context={"small": "x" * 100},
    eligible=True,
    mode="diagnostic",
)
assert diagnostic.context == {"large": "x" * 1000}
assert diagnostic.diagnostics["actual_outbound_tokens"] == diagnostic.diagnostics["actual_full_tokens"]

compact = optimize_task_context(
    task="planner",
    prompt="prompt",
    tools=[],
    full_context={"large": "x" * 1000},
    compact_context={"small": "x" * 100},
    eligible=True,
    mode="compact",
)
assert compact.context == {"small": "x" * 100}
assert compact.diagnostics["actual_outbound_tokens"] == compact.diagnostics["compact_candidate_tokens"]
```

- [ ] Implement one canonical serializer shared by estimation logic.

The estimator must include system prompt, `Context JSON`, and tool schemas; exclude HTTP headers and secrets. Use compact JSON separators for outbound context only after a test proves DeepSeek parsing and current response extraction remain unchanged.

- [ ] Implement turn accounting:

```python
def add_task_token_accounting(accounting: dict, task: str, diagnostics: dict) -> dict:
    result = copy.deepcopy(accounting) if isinstance(accounting, dict) else {}
    result.setdefault("calls", []).append({"task": task, **diagnostics})
    result["call_count"] = len(result["calls"])
    result["turn_estimated_outbound_tokens"] = sum(
        int(call.get("actual_outbound_tokens") or 0) for call in result["calls"]
    )
    return result
```

- [ ] Run tests and commit.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py -q
git add ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\tests\test_llm_context_optimization.py
git commit -m "feat: add exact llm payload accounting"
```

---

### Task 4: Add Lossless Projection Primitives and Ordered Compaction

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_llm_context_optimization.py`

- [ ] Write failing tests for semantic truncation, history windows, evidence ranking, citation preservation, and ordered stages.

Tests must prove:

- last 4 planner turns means 8 messages
- last 6 answer turns means 12 messages
- evidence is ranked by score before applying limits
- `doc_id`, title/filename, location, version, score, and retrieval domain survive projection
- active instruction section and complete safety rules survive semantic shortening
- no helper mutates its input
- an over-budget candidate applies all permitted stages before fail-open

- [ ] Implement pure primitives:

```python
def bounded_chat_history(history: Any, *, max_turns: int) -> list[dict]: ...
def compact_evidence_items(items: Any, *, limit: int, snippet_limit: int) -> list[dict]: ...
def semantic_section_compact(text: str, *, active_markers: list[str], max_chars: int) -> str: ...
def project_mapping(source: Any, allowed_keys: Collection[str]) -> dict: ...
def apply_ordered_compaction(task: str, context: dict, budget: int) -> tuple[dict, list[str]]: ...
```

`semantic_section_compact` must split Markdown by heading boundaries and retain complete sections containing active markers or safety/constraint headings. It must not slice an authoritative section mid-rule.

- [ ] Run tests and commit.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py -q
git add ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\tests\test_llm_context_optimization.py
git commit -m "feat: add lossless llm context compaction"
```

---

### Task 5: Build Prompt-Compatible Planner Projections

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] Write failing tests asserting compact planner context retains these exact keys:

```python
{
    "user_query",
    "turn_input_type",
    "session_upload_event_ids",
    "chat_history",
    "session_uploads",
    "app_id",
    "collection_id",
    "config_json",
    "adapter_json",
    "template_registry",
}
```

For eligible text turns, `session_uploads` may contain only metadata for active upload ids explicitly referenced by persisted state; it must not contain content. For ineligible upload turns, optimization must return the original full context unchanged.

- [ ] Implement `build_planner_context(state)` with prompt-compatible compact values:

- `config_json`: goals, step skeletons, planning-relevant style/safety/retrieval rules
- `adapter_json`: intent overrides, step skeleton mapping, retrieval defaults/mapping rules, planner guardrails
- `template_registry`: intent categories, compact executable candidates, routing rules, active binding identities
- `chat_history`: real summary plus last 4 turns

- [ ] Add hybrid candidate projection preserving every role/workflow/module/follow-up/procedure/step id used by planner harmonization.

- [ ] Extend existing Church Ministry, `與孩子一起成長`, follow-up module, and upload planner tests to capture outbound LLM context and verify required ids remain available.

- [ ] Run planner tests and commit.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_planner_node.py -q
git add ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_planner_node.py
git commit -m "feat: add prompt compatible planner projections"
```

---

### Task 6: Build Lossless Answer Projection

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_answer_node.py`

- [ ] Write failing tests that start from the rich state in `test_answer_node.py` and assert compact context retains every logical key currently asserted there.

Required keys:

```python
{
    "user_query",
    "chat_history",
    "planner_output",
    "evidence_analysis",
    "prepared_inputs",
    "instruction_evidence",
    "selected_instruction_block",
    "selected_instruction_block_text",
    "instruction_resource_load_plan",
    "instruction_resource_context",
    "template_resource_load_plan",
    "template_resource_context",
    "global_instruction_context",
    "knowledge_evidence",
    "template_evidence",
    "session_upload_evidence",
    "adapter_json",
    "config_json",
    "template_registry",
    "turn_execution_plan",
    "turn_action_plan",
    "session_execution_state",
    "presentation_policy",
    "visible_outputs",
    "execution_artifacts",
}
```

- [ ] Add field-specific tests:

- citation identities are lossless
- active step/module ids remain present
- prepared input resource requests remain present
- load plans retain filename, load strategy, binding id, dependency group id, and artifact role
- global safety rules and guardrails remain complete
- authoritative instruction text retains the complete active section
- hidden outputs are retained only when referenced by assembly/validation/artifact state
- normal text follow-up includes active upload evidence only when `active_session_upload_ids` is populated

- [ ] Implement `build_answer_context(full_context)` under the same keys. Remove only exact duplicates and unrelated fields.

- [ ] Preserve the existing safe-answer pass by adding `missing_infoTypes` and `previous_answer` to the already-selected outbound context.

- [ ] Run answer tests and commit.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_answer_node.py -q
git add ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_answer_node.py
git commit -m "feat: add lossless answer context projection"
```

---

### Task 7: Implement Evidence Modes and Conflict-Aware Sufficiency

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_evidence_analysis.py`

- [ ] Write failing tests for all modes:

```python
def test_auto_skips_llm_only_when_sufficient_and_non_conflicting(): ...
def test_auto_calls_llm_for_semantically_ambiguous_info_type(): ...
def test_auto_calls_llm_when_evidence_conflicts(): ...
def test_deterministic_never_calls_llm(): ...
def test_llm_required_calls_llm_even_when_deterministic_sufficient(): ...
def test_llm_required_falls_back_when_model_unavailable(): ...
```

- [ ] Implement `deterministic_evidence_assessment(...)` returning structured reasons:

```python
{
    "sufficient": bool,
    "ambiguous": bool,
    "conflicting": bool,
    "reasons": list[str],
}
```

The assessment must require stable citation identity, honor minimum score when present, detect direct positive/negative conflict markers for the same requested info type, and classify broad labels without direct metadata grounding as ambiguous.

- [ ] Implement mode routing without changing the existing evidence output schema or LLM-error fallback.

- [ ] Run tests and commit.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_evidence_analysis.py -q
git add ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_evidence_analysis.py
git commit -m "feat: add evidence analysis optimization policy"
```

---

### Task 8: Add a Real Deterministic Conversation Summary

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_llm_context_optimization.py`
- Modify: `ragenius_app_skeleton/tests/test_persist_run_node.py`

- [ ] Write failing summary tests using more than 4 turns.

The summary must contain actual extracted values for:

- user decisions/preferences/constraints
- assistant conclusions and generated output references
- unresolved questions
- active workflow/module/step ids and titles
- filled clarification slots
- pending resource/artifact/output obligations
- recent citation ids
- covered message ids/count

- [ ] Test that the current user message and current `final_answer` are included even though neither is yet present in input `chat_history` when `persist_run.run()` begins.

- [ ] Implement:

```python
def build_or_refresh_chat_summary(
    *,
    existing_summary: Mapping[str, Any] | None,
    prior_history: list[dict],
    current_user_message: str,
    current_answer: Mapping[str, Any],
    session_execution_state: Mapping[str, Any],
) -> dict: ...
```

Use deterministic extraction and bounded text, not a new LLM call. Refresh before the planner would drop history older than 4 turns.

- [ ] Persist summary additively under `session_execution_state.chat_summary`; do not replace or flatten workflow state.

- [ ] Run persistence tests and commit.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_persist_run_node.py ragenius_app_skeleton\tests\test_chat_repo_persistence.py -q
git add ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\workflows\nodes\persist_run.py ragenius_app_skeleton\tests\test_llm_context_optimization.py ragenius_app_skeleton\tests\test_persist_run_node.py
git commit -m "feat: persist deterministic conversation summaries"
```

---

### Task 9: Integrate Diagnostic Mode Without Behavior Changes

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/app/chat_service.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/evidence_analysis.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/answer.py`
- Create: `ragenius_app_skeleton/tests/test_llm_context_optimization_integration.py`

- [ ] Write failing diagnostic-mode tests proving:

- normal text turn is eligible
- actual full context is sent
- compact candidate is measured
- actual outbound tokens equal full tokens
- task diagnostics aggregate to `turn_estimated_outbound_tokens`
- existing response diagnostic keys remain unchanged
- upload analysis is ineligible and sends byte-for-byte equivalent logical context
- out-of-scope direct answer behavior remains unchanged

- [ ] Set `_context_optimization_eligible` only in normal-chat state construction. Set it false explicitly in upload state construction.

- [ ] In each task node, build full and compact contexts only after checking eligibility. When ineligible or mode is `off`, call the current code path directly.

- [ ] In diagnostic mode, send full context and attach nested optional diagnostics under the existing selected-task diagnostics.

- [ ] Run integration and existing pipeline tests.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization_integration.py ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py ragenius_app_skeleton\tests\test_builder_chat_integration.py -q
```

Expected: all tests pass with no compact contexts sent.

- [ ] Commit.

```powershell
git add ragenius_app_skeleton\backend\app\main.py ragenius_app_skeleton\backend\app\chat_service.py ragenius_app_skeleton\workflows\nodes\planner.py ragenius_app_skeleton\workflows\nodes\evidence_analysis.py ragenius_app_skeleton\workflows\nodes\answer.py ragenius_app_skeleton\tests\test_llm_context_optimization_integration.py
git commit -m "feat: add diagnostic context optimization pipeline"
```

---

### Task 10: Build Representative Parity and Reduction Harness

**Files:**

- Create: `ragenius_app_skeleton/tests/test_llm_context_optimization_parity.py`
- Reuse fixtures from existing planner, answer, and pipeline tests.

- [ ] Implement a fake task-call recorder that serializes prompt, tools, and context exactly as the runtime estimator does.

- [ ] Implement full-versus-compact execution helpers with deterministic LLM responses based only on required context fields.

- [ ] Add fixtures for:

1. simple factual QA
2. multi-turn continuation beyond 4 turns
3. Church Ministry initial workflow
4. Church Ministry refinement follow-up
5. `與孩子一起成長`
6. missing-evidence safe-answer second call
7. out-of-scope direct answer
8. session-upload analysis bypass
9. normal text follow-up referencing an active upload

- [ ] For every eligible fixture, assert parity for:

```text
planner intent and normalized/contextual query
retrieval app_id filter
active workflow/module/step
resource request identities
evidence-analysis output shape
final answer schema
citation source ids
workflow_progress
session_execution_state canonical ids
```

- [ ] For ineligible upload fixture, assert no compact builder is used and contexts match full mode.

- [ ] Assert aggregate savings:

```python
assert compact_total_tokens < full_total_tokens
assert ((full_total_tokens - compact_total_tokens) / full_total_tokens) >= 0.40
```

Compute the 40% threshold over the representative eligible fixture set, and also report each fixture's savings so one regression cannot be hidden by another.

- [ ] Run parity tests. Do not proceed to compact integration until all pass.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_llm_context_optimization_parity.py -q
```

- [ ] Commit.

```powershell
git add ragenius_app_skeleton\tests\test_llm_context_optimization_parity.py
git commit -m "test: add llm context parity and savings harness"
```

---

### Task 11: Enable Compact Mode in Staged Task Order

**Files:**

- Modify: `ragenius_app_skeleton/workflows/nodes/evidence_analysis.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/answer.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Modify: relevant optimization integration/parity tests

- [ ] Enable evidence-analysis compaction first. Run evidence, parity, and upload-bypass tests.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_evidence_analysis.py ragenius_app_skeleton\tests\test_llm_context_optimization_integration.py ragenius_app_skeleton\tests\test_llm_context_optimization_parity.py -q
```

- [ ] Enable answer compaction second. Run answer, safe-answer, pipeline, parity, and upload-bypass tests.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_answer_node.py ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py ragenius_app_skeleton\tests\test_llm_context_optimization_integration.py ragenius_app_skeleton\tests\test_llm_context_optimization_parity.py -q
```

- [ ] Enable legacy planner compaction third. Run complete planner and parity suites.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests\test_planner_node.py ragenius_app_skeleton\tests\test_llm_context_optimization_parity.py -q
```

- [ ] Enable hybrid candidate compaction last. Run protected Church Ministry, `與孩子一起成長`, follow-up, module queue, and parity tests.

- [ ] After each stage, verify `actual_outbound_tokens`, parity, and upload bypass before committing that stage separately.

Suggested commits:

```text
feat: enable compact evidence context
feat: enable compact answer context
feat: enable compact legacy planner context
feat: enable compact hybrid planner context
```

---

### Task 12: Full Regression, Boundary Audit, and Default Decision

**Files:** No additional feature files unless failures require correction.

- [ ] Run all `ragenius_app_skeleton` tests.

```powershell
.\.venv\Scripts\python.exe -m pytest ragenius_app_skeleton\tests ragenius_app_skeleton\backend\tests -q
```

- [ ] Run repository tests that do not require unavailable external services.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] Audit changed paths.

```powershell
git diff --name-only
```

Expected: no feature changes under `rag_subsystem`, `ragenius_builder`, `ragenius_app`, frontend contracts, or function schemas.

- [ ] Audit prompt/context compatibility.

```powershell
rg -n "config_json|adapter_json|template_registry|prepared_inputs|instruction_evidence|resource_load_plan|selected_instruction_block_text" ragenius_app_skeleton\prompts ragenius_app_skeleton\backend\app\llm_context_optimization.py ragenius_app_skeleton\workflows\nodes
```

Expected: every prompt-referenced logical field required by an eligible task is represented in its compact projection.

- [ ] Verify safe default remains `off` or `diagnostic`. Do not set `compact` as default in this implementation unless maintainers separately approve it after reviewing parity and real-session diagnostics.

- [ ] Record final evidence in `docs/superpowers/plans/2026-07-15-normal-user-query-token-optimization-verification.md`.

The verification record must include commands and results, per-fixture full/compact token estimates, aggregate saving percentage, parity outcomes, upload/exec bypass outcomes, and known limitations.

---

## Completion Gate

Implementation is complete only when all statements are true:

- optimization runs only for eligible normal text queries
- upload analysis and exec turns remain on current behavior with compact mode globally enabled
- compact contexts preserve prompt-referenced logical keys
- existing planner, answer, evidence, pipeline, and persistence tests pass
- representative full/compact parity tests pass
- aggregate estimated input-token savings are at least 40%
- citations remain grounded and app-scoped retrieval filters remain enforced
- session summaries preserve real conversation continuity beyond 4 turns
- no changes were made to protected sibling subsystems
- compact mode remains non-default pending operational approval
