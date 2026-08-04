# No-Phase-Fallback Resource Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop broad `phase:*` bindings from auto-loading instruction `.md` files, so Bible Tutor and Church Ministry load only explicitly owned instruction docs while keeping `???????` stable.

**Architecture:** Treat `phase:*` bindings as orchestration metadata, not instruction-document fallback. The compiler remains responsible for explicit resource ownership in the active snapshot; the planner becomes responsible for loading only explicit step/module docs, using selected block text plus vector retrieval when a step intentionally owns no `.md` files, and persisting the same canonical path that drove content generation.

**Tech Stack:** Python, FastAPI backend, planner graph node, snapshot compiler, unittest/pytest integration tests.

---

## File map

- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
  - Owns active-scope resolution, phase-binding activation, instruction/template resource load planning, and turn execution persistence.
- Modify: `ragenius_app_skeleton/backend/app/chat_service.py`
  - Owns how planner `resource_requests` become selected resources in persisted retrieval summaries.
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
  - Planner/persistence regressions for Bible Tutor, Church Ministry, and protected non-regression slices.
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - End-to-end session payload regressions for GUI-facing workflow status and selected resource filenames.
- Modify: `ragenius_app_skeleton/tests/test_llm_runtime_compat.py`
  - Cross-app non-regression assertions if planner semantics need explicit protection for non-phase bindings.
- Reference only: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
  - Snapshot contract is already the source of truth for explicit `resource_refs`; no new compile behavior should be added unless a test proves a missing explicit ownership defect.

## Design rules to enforce

1. Explicit instruction docs only:
   - Load instruction `.md` files only from explicit `resource_refs` / `bundled_resource_refs` on the active step or direct resources on the active executable block.
2. No broad `phase:*` fallback for instruction docs:
   - `phase:*` bindings may stay in session state for orchestration/debugging, but they must not auto-expand into `instruction_source` or `output_template` resource requests.
3. No-doc steps remain valid:
   - If the active step intentionally owns no `.md` files, planner must rely on selected block text plus vector retrieval, not broad module docs.
4. Starter-turn module entry must resolve before loading docs:
   - If a starter route enters a module-owned procedure, planner must synthesize the first step before resource preparation.
5. One active path per turn:
   - The active path used for content generation, resource loading, persisted session state, and GUI payload must be the same canonical workflow/module/step path.

## Verification bar

Do not call the issue fixed unless all four pass:

1. compile contract test passes
2. planner/runtime persistence test passes
3. GUI payload test passes
4. cross-app non-regression suite passes

---

### Task 1: Lock the current live failure shapes in tests

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Write failing planner tests for Bible Tutor starter-turn narrowing**

Add a regression near the existing Bible Tutor planner cases asserting that a starter turn entering `??????` does not emit the whole module pack when the module immediately resolves to the first executable step.

```python
def test_bible_tutor_starter_turn_enters_first_step_before_loading_instruction_docs(self):
    state = _planner_state(
        user_message="????????",
        runtime_model={
            "primary_service_mode": "intent_routed_interaction_logic",
            "routing_rules": [
                {
                    "rule_id": "route_to_bible_study",
                    "target_logic_block_id": "mode_bible_study",
                    "trigger_keywords": ["??", "??"],
                    "priority": 1,
                }
            ],
            "instruction_service_blocks": [
                {"block_id": "support_module:??????", "title": "??????", "block_type": "support_module"}
            ],
            "instruction_procedures": [
                {
                    "procedure_id": "procedure:support_module_??????",
                    "service_block_id": "support_module:??????",
                    "title": "??????",
                }
            ],
            "procedure_steps": [
                {
                    "procedure_id": "procedure:support_module_??????",
                    "step_id": "step:observation",
                    "title": "???? (Observation)",
                    "order": 1,
                    "resource_refs": ["observation_guide.md"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "phase:??????",
                    "title": "??????",
                    "resource_refs": [
                        "observation_guide.md",
                        "identify_relationships_guide.md",
                    ],
                }
            ],
        },
    )

    out = run(state)

    request_filenames = [item.get("filename") for item in out["turn_execution_plan"]["resource_requests"]]
    assert request_filenames == ["observation_guide.md"]
    assert out["session_execution_state"]["active_step_scope_id"] == "step:observation"
```

- [ ] **Step 2: Write failing planner tests for Church Ministry no-doc clarification and narrow core step**

Add two regressions asserting that broad knowledge/instruction phases do not auto-load docs when a step intentionally owns none, and that core step 2 loads only explicit step docs.

```python
def test_church_ministry_clarification_step_does_not_fallback_to_phase_docs(self):
    state = _planner_state(
        user_message="????????????????",
        runtime_model={
            "primary_service_mode": "single_default_workflow",
            "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
            "instruction_service_blocks": [
                {"block_id": "primary_workflow:interaction_logic_execution_flow", "title": "Interaction Logic & Execution Flow", "block_type": "primary_workflow"},
            ],
            "instruction_procedures": [
                {"procedure_id": "primary_workflow:interaction_logic_execution_flow", "service_block_id": "primary_workflow:interaction_logic_execution_flow", "title": "Interaction Logic & Execution Flow"},
            ],
            "procedure_steps": [
                {"procedure_id": "primary_workflow:interaction_logic_execution_flow", "step_id": "step:interaction_logic_execution_flow:1", "title": "Clarification", "order": 1, "resource_refs": []},
                {"procedure_id": "primary_workflow:interaction_logic_execution_flow", "step_id": "step:interaction_logic_execution_flow:2", "title": "????(Workflow Execution)", "order": 2, "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"]},
            ],
            "phase_resource_bindings": [
                {"binding_id": "phase:1_knowledge_modules_????", "resource_refs": ["template_library.md", "prompt_design_rules.md"]},
                {"binding_id": "phase:2_instruction_modules_????", "resource_refs": ["dynamic_prompt_optimizer.md"]},
            ],
        },
    )

    out = run(state)

    instruction_requests = [
        item for item in out["turn_execution_plan"]["resource_requests"]
        if item.get("resource_role") == "instruction_source"
    ]
    assert instruction_requests == []
    assert out["session_execution_state"]["active_step_scope_id"] == "step:interaction_logic_execution_flow:1"


def test_church_ministry_core_step_loads_only_explicit_step_docs(self):
    state = _planner_state(
        user_message="?????,????? prompt",
        session_state={"active_step_scope_id": "step:interaction_logic_execution_flow:1"},
        runtime_model={...same as above...},
    )

    out = run(state)

    request_filenames = [
        item.get("filename")
        for item in out["turn_execution_plan"]["resource_requests"]
        if item.get("resource_role") == "instruction_source"
    ]
    assert request_filenames == ["template_library.md", "dynamic_prompt_optimizer.md"]
```

- [ ] **Step 3: Write failing builder integration tests for persisted selected resources**

Add or update end-to-end tests so the API payload reflects the same narrow resource set.

```python
def test_bible_tutor_session_messages_starter_turn_uses_only_first_step_doc(self):
    payload = _run_bible_tutor_starter_flow_via_api(...)
    first_assistant = _assistant_messages(payload)[0]
    assert first_assistant["retrievalSummary"]["selected_resource_filenames"] == ["observation_guide.md"]


def test_church_ministry_session_messages_clarification_turn_uses_no_instruction_docs(self):
    payload = _run_church_ministry_flow_via_api(...)
    first_assistant = _assistant_messages(payload)[0]
    assert first_assistant["retrievalSummary"]["selected_resource_filenames"] == []


def test_church_ministry_session_messages_core_turn_uses_only_template_and_dpo(self):
    payload = _run_church_ministry_flow_via_api(...)
    last_assistant = _assistant_messages(payload)[-1]
    assert last_assistant["retrievalSummary"]["selected_resource_filenames"] == [
        "template_library.md",
        "dynamic_prompt_optimizer.md",
    ]
```

- [ ] **Step 4: Run the targeted tests to confirm failure**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "bible_tutor_starter_turn_enters_first_step_before_loading_instruction_docs or church_ministry_clarification_step_does_not_fallback_to_phase_docs or church_ministry_core_step_loads_only_explicit_step_docs" -v
python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "starter_turn_uses_only_first_step_doc or clarification_turn_uses_no_instruction_docs or core_turn_uses_only_template_and_dpo" -v
```

Expected:
- planner tests fail because broad `phase:*` resources still appear
- builder integration tests fail because persisted `selected_resource_filenames` still show the broad file sets

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "test: lock no-phase-fallback resource loading regressions"
```

### Task 2: Make `phase:*` bindings metadata-only for instruction-doc loading

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Add a helper that decides whether a binding may contribute instruction docs**

Add a small predicate near the resource-planning helpers.

```python
def _binding_can_supply_instruction_docs(binding_id: str | None) -> bool:
    if not binding_id:
        return False
    normalized = str(binding_id).strip().lower()
    if normalized.startswith("phase:"):
        return False
    return True
```

- [ ] **Step 2: Filter phase-origin binding requests out of instruction/template resource requests**

In `_build_resource_requests(...)`, keep non-phase binding requests, but exclude `phase:*` requests when they would load instruction docs or templates.

```python
binding_requests: list[dict[str, Any]] = []
for request in execution_context.get("binding_resource_requests", []) or []:
    role = str(request.get("resource_role") or "").strip().lower()
    binding_id = request.get("binding_id")
    if role in {"instruction_source", "output_template"} and not _binding_can_supply_instruction_docs(binding_id):
        continue
    binding_requests.append(request)
```

- [ ] **Step 3: Keep `active_binding_ids` in session state**

Do not remove `phase:*` from `active_binding_ids`. They still matter for orchestration/debugging.

```python
session_state_update["active_binding_ids"] = binding_activation.get("active_binding_ids", [])
# Keep as-is; only resource expansion changes.
```

- [ ] **Step 4: Run the targeted planner tests**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "church_ministry_clarification_step_does_not_fallback_to_phase_docs or church_ministry_core_step_loads_only_explicit_step_docs" -v
```

Expected:
- clarification test passes with zero instruction docs
- core-step test still may fail until starter-turn first-step synthesis is fixed in Task 3

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "fix: stop phase bindings from auto-loading instruction docs"
```

### Task 3: Resolve module-owned first step before resource preparation

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Write a focused failing test for starter-turn first-step synthesis**

If Task 1 coverage was broad, add a narrower unit around execution-context selection.

```python
def test_module_entry_prefers_first_step_scope_for_resource_preparation(self):
    out = run(_planner_state(...Bible Tutor starter runtime...))
    assert out["selected_instruction_block"]["block_id"] == "step:observation"
    assert [item.get("filename") for item in out["instruction_resource_load_plan"]] == ["observation_guide.md"]
```

- [ ] **Step 2: Update selected-block resolution to prefer concrete first step on module entry**

In the execution-context assembly path, when the active service block is a module-owned procedure and no concrete step has been selected yet, synthesize the first step before `instruction_resource_load_plan` is built.

```python
if selected_module and not selected_block:
    module_block_id = str(selected_module.get("block_id") or "")
    module_procedure = _procedure_for_service_block(state, module_block_id)
    first_step = _first_step_for_procedure(state, module_procedure)
    if first_step:
        selected_block = _instruction_block_from_step(first_step, selected_module)
```

- [ ] **Step 3: Ensure the persisted active path matches the synthesized step path**

When the first step is synthesized for the turn, persist the same step scope into `session_execution_state`.

```python
if selected_block and selected_block.get("block_type") == "step":
    session_state_update["active_step_scope_id"] = selected_block.get("block_id")
    session_state_update["primary_scope_id"] = selected_module.get("block_id") if selected_module else session_state_update.get("primary_scope_id")
```

- [ ] **Step 4: Run the Bible Tutor planner test**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "bible_tutor_starter_turn_enters_first_step_before_loading_instruction_docs or module_entry_prefers_first_step_scope_for_resource_preparation" -v
```

Expected:
- both tests pass

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "fix: synthesize first module step before resource loading"
```

### Task 4: Treat no-doc steps as block-text plus vector-retrieval only

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Modify: `ragenius_app_skeleton/backend/app/chat_service.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Write the failing persistence test for no-doc clarification turns**

```python
def test_no_doc_step_sets_use_instruction_block_only_and_persists_empty_selected_resources(self):
    out = run(_planner_state(...Church clarification runtime...))
    assert out["turn_execution_plan"]["resource_requests"] == []
    assert out["use_instruction_block_only"] is True
```

- [ ] **Step 2: Keep `instruction_resource_load_plan` empty when a concrete step owns no docs**

In the execution-context builder, preserve selected block text but do not fall back to broad instruction docs.

```python
if selected_block and selected_block.get("block_type") == "step" and not instruction_resource_load_plan:
    execution_context["use_instruction_block_only"] = True
    execution_context["instruction_resource_load_plan"] = []
```

- [ ] **Step 3: Ensure selected-resource summaries stay empty for no-doc steps**

In `chat_service.py`, keep selected-resource summarization faithful to planner `resource_requests`; do not infer selected resources from `active_binding_ids`.

```python
selected_resource_summary = _summarize_selected_resources(...)
# No extra expansion from active_binding_ids here.
```

If any branch currently expands by `active_binding_ids`, delete that expansion and rely only on the requests returned by planner.

- [ ] **Step 4: Run the targeted integration tests**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "clarification_turn_uses_no_instruction_docs or core_turn_uses_only_template_and_dpo or starter_turn_uses_only_first_step_doc" -v
```

Expected:
- selected resource filenames match explicit planner loads exactly

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/backend/app/chat_service.py ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "fix: treat no-doc steps as block-text and retrieval only"
```

### Task 5: Protect non-phase binding behavior and cross-app stability

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Modify: `ragenius_app_skeleton/tests/test_llm_runtime_compat.py`

- [ ] **Step 1: Add a regression proving non-phase bindings still work**

Reuse an existing app pattern that relies on `binding:*` ids and assert those resource requests still survive.

```python
def test_non_phase_binding_requests_still_load_output_rules(self):
    out = run(_planner_state(...existing binding:ministry-output-rules fixture...))
    request_filenames = [item.get("filename") for item in out["turn_execution_plan"]["resource_requests"]]
    assert "ministry_output_rules.md" in request_filenames
    assert "binding:ministry-output-rules" in out["session_execution_state"]["active_binding_ids"]
```

- [ ] **Step 2: Add protected non-regression for `???????`**

```python
def test_parenting_route_visibility_remains_stable_after_no_phase_fallback_change(self):
    payload = _run_parenting_route_flow_via_api(...)
    assert payload["workflow_status"]["workflow_title"]
    assert payload["workflow_status"]["active_step_scope_id"]
```

- [ ] **Step 3: Run compatibility/non-regression tests**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -k "non_phase_binding_requests_still_load_output_rules" -v
python -m pytest ragenius_app_skeleton/tests/test_llm_runtime_compat.py -v
python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "parenting_route_visibility_remains_stable_after_no_phase_fallback_change" -v
```

Expected:
- non-phase bindings still produce resources when explicitly requested
- `???????` remains stable

- [ ] **Step 4: Commit**

```bash
git add ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_llm_runtime_compat.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "test: protect non-phase bindings and parenting non-regression"
```

### Task 6: Run the practical-standard verification suite

**Files:**
- No code changes

- [ ] **Step 1: Run compile contract tests**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_instruction_understanding_service.py -v
```

Expected:
- all pass

- [ ] **Step 2: Run planner/runtime persistence tests**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_planner_node.py -v
```

Expected:
- all pass

- [ ] **Step 3: Run GUI payload tests**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_builder_chat_integration.py -k "starter_turn_uses_only_first_step_doc or clarification_turn_uses_no_instruction_docs or core_turn_uses_only_template_and_dpo or session_messages_workflow_status_shows_parenting_route_when_role_target_should_bind_workflow" -v
```

Expected:
- all pass

- [ ] **Step 4: Run cross-app non-regression suite**

Run:
```bash
python -m pytest ragenius_app_skeleton/tests/test_llm_runtime_compat.py -v
```

Expected:
- all pass

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/backend/app/chat_service.py ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_builder_chat_integration.py ragenius_app_skeleton/tests/test_llm_runtime_compat.py
# Commit only if all verification gates are green.
git commit -m "fix: enforce explicit instruction-doc loading without phase fallback"
```

## Self-review

- Spec coverage:
  - explicit-doc-only loading: Tasks 2 and 4
  - no broad `phase:*` fallback: Task 2
  - no-doc clarification/core behavior: Tasks 1 and 4
  - Bible Tutor starter-turn first-step narrowing: Task 3
  - persistence path consistency: Tasks 3 and 4
  - protect `???????`: Task 5
- Placeholder scan:
  - no TBD/TODO placeholders remain
  - every task includes exact files, commands, and concrete assertions/code skeletons
- Type consistency:
  - uses existing runtime names already observed in live payloads: `primary_scope_id`, `active_step_scope_id`, `resource_requests`, `instruction_resource_load_plan`, `active_binding_ids`
