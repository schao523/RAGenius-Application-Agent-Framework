# Snapshot-First Compiler and Planner Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix recurring broad `.md` loading and persisted-path drift for Bible Tutor and Church Ministry by hardening the active snapshot contract first, then tightening planner resource precedence and persistence, while protecting `與孩子一起成長` as a non-regression baseline.

**Architecture:** The work is split into two layers. First, strengthen `compiled_contract.hybrid_instruction_runtime_model` so executable steps and follow-up modules own their narrow resources and compatibility runtime cannot broaden those scopes. Second, narrow planner behavior so it follows the canonical snapshot contract, persists one coherent execution path, and exposes the same path to the GUI. `與孩子一起成長` is protected through compile, planner, and GUI non-regression tests.

**Tech Stack:** Python 3, pytest/unittest hybrid test suite, FastAPI backend, SQLite-backed session state, runtime snapshot JSON projections.

---

## File Structure

- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
  - Snapshot compiler and projection logic.
  - Owns hybrid runtime step resources, executable follow-up projection, and compatibility-runtime derivation rules.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py`
  - Planner resource precedence, active execution-path selection, and persisted session-state validation.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py`
  - GUI payload projection if planner/runtime state surfaces need a small adapter adjustment.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
  - Compile-contract tests for Bible Tutor, Church Ministry, and `與孩子一起成長` non-regression.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`
  - Planner persistence/resource-precedence regressions.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - GUI payload and end-to-end builder-facing runtime-state regressions.
- `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/docs/superpowers/specs/2026-05-21-snapshot-first-compiler-planner-hardening-design.md`
  - Approved design reference. Do not change unless implementation reveals a real contradiction.

### Task 1: Lock Compile-Contract Failures First

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Reference: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/docs/superpowers/specs/2026-05-21-snapshot-first-compiler-planner-hardening-design.md`

- [ ] **Step 1: Add a failing Bible Tutor compile-contract test for step-owned resource refs**

```python
def test_compile_instruction_understanding_bible_tutor_hybrid_steps_own_step_specific_resources(self) -> None:
    understanding = self.service.compile_instruction_understanding(
        app_name="Bible Tutor",
        instructions_markdown=BIBLE_TUTOR_INSTRUCTIONS,
    )

    hybrid = understanding["compiled_contract"]["hybrid_instruction_runtime_model"]
    steps = {step["step_id"]: step for step in hybrid.get("procedure_steps", [])}

    assert steps["step:observation"]["resource_refs"] == ["observation_guide.md"]
    assert steps["step:identify_relationships"]["resource_refs"] == ["identify_relationships_guide.md"]
```

- [ ] **Step 2: Add a failing Church Ministry compile-contract test for clarification/core/optimization scope**

```python
def test_compile_instruction_understanding_church_ministry_projects_narrow_step_and_optimization_resources(self) -> None:
    understanding = self.service.compile_instruction_understanding(
        app_name="Church Ministry Prompt Designer",
        instructions_markdown=CHURCH_MINISTRY_PROMPT_DESIGNER_INSTRUCTIONS,
    )

    hybrid = understanding["compiled_contract"]["hybrid_instruction_runtime_model"]
    steps = {step["step_id"]: step for step in hybrid.get("procedure_steps", [])}
    blocks = {block["block_id"]: block for block in hybrid.get("instruction_service_blocks", [])}

    assert steps["step:clarification"]["resource_refs"]
    assert steps["step:core_workflow_execution"]["resource_refs"]
    assert "followup_module:optimization_module" in blocks
    assert blocks["followup_module:optimization_module"]["resource_refs"] == [
        "Optimization Strategy Library.md",
        "dynamic_prompt_optimizer.md",
    ]
```

- [ ] **Step 3: Add a failing compatibility-projection test that broad module scope does not override narrow step scope**

```python
def test_compile_instruction_understanding_compatibility_runtime_does_not_broaden_hybrid_step_scope(self) -> None:
    understanding = self.service.compile_instruction_understanding(
        app_name="Bible Tutor",
        instructions_markdown=BIBLE_TUTOR_INSTRUCTIONS,
    )

    hybrid = understanding["compiled_contract"]["hybrid_instruction_runtime_model"]
    nested = understanding["compiled_contract"]["instruction_runtime_model"]
    hybrid_steps = {step["step_id"]: step for step in hybrid.get("procedure_steps", [])}
    nested_steps = {step["step_id"]: step for step in nested.get("procedure_steps", [])}

    assert nested_steps["step:observation"]["resource_refs"] == hybrid_steps["step:observation"]["resource_refs"]
```

- [ ] **Step 4: Add a protected non-regression compile test for `與孩子一起成長`**

```python
def test_compile_instruction_understanding_parenting_app_preserves_runtime_bindable_parenting_paths(self) -> None:
    understanding = self.service.compile_instruction_understanding(
        app_name="與孩子一起成長",
        instructions_markdown=PARENTING_APP_INSTRUCTIONS,
    )

    hybrid = understanding["compiled_contract"]["hybrid_instruction_runtime_model"]
    rule_ids = {rule["rule_id"] for rule in hybrid.get("routing_rules", [])}

    assert "route_emotion_to_mentor" in rule_ids
    assert "route_behavior_to_consultant" in rule_ids
```

- [ ] **Step 5: Run the compile-contract tests and verify they fail for the intended reasons**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py -k "hybrid_steps_own_step_specific_resources or projects_narrow_step_and_optimization_resources or compatibility_runtime_does_not_broaden_hybrid_step_scope or preserves_runtime_bindable_parenting_paths" -v
```

Expected:
- Bible Tutor test fails because `resource_refs` are empty or too broad.
- Church Ministry test fails because clarification/core refs or executable optimization block are missing.
- Compatibility test fails if nested runtime still broadens active step ownership.
- Parenting non-regression test should already pass or expose an unexpected shared compile regression.

- [ ] **Step 6: Commit the red tests**

```bash
git add C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "test: lock snapshot contract regressions for bible tutor and church ministry"
```

### Task 2: Harden Active Snapshot Generation

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Identify or add one helper that maps executable steps to owned resource refs**

```python
def _step_resource_refs_for_runtime_scope(
    *,
    app_name: str,
    step_id: str,
    step_title: str,
    existing_refs: list[str] | None,
) -> list[str]:
    if existing_refs:
        return existing_refs
    # Fill in deterministic step refs from authored step metadata or known compile artifacts.
    ...
```

- [ ] **Step 2: Apply that helper when building hybrid `procedure_steps` for Bible Tutor**

```python
resource_refs = _step_resource_refs_for_runtime_scope(
    app_name=app_name,
    step_id=step_id,
    step_title=step_title,
    existing_refs=resource_refs,
)
hybrid_step["resource_refs"] = resource_refs
```

- [ ] **Step 3: Apply the same helper for Church Ministry clarification/core steps**

```python
if canonical_workflow_id == "wf:interaction_logic_execution_flow":
    hybrid_step["resource_refs"] = _step_resource_refs_for_runtime_scope(
        app_name=app_name,
        step_id=hybrid_step["step_id"],
        step_title=hybrid_step.get("title", ""),
        existing_refs=hybrid_step.get("resource_refs"),
    )
```

- [ ] **Step 4: Project Church Ministry Optimization Module into executable hybrid service blocks**

```python
optimization_block = {
    "block_id": "followup_module:optimization_module",
    "block_type": "followup_module",
    "title": "Optimization Module",
    "resource_refs": [
        "Optimization Strategy Library.md",
        "dynamic_prompt_optimizer.md",
    ],
}
instruction_service_blocks = _upsert_service_block(
    instruction_service_blocks,
    optimization_block,
)
```

- [ ] **Step 5: Make compatibility runtime copy narrow step refs from hybrid runtime instead of regenerating broad module scope**

```python
for hybrid_step in hybrid_runtime_model.get("procedure_steps", []):
    nested_step = nested_steps_by_id.get(hybrid_step["step_id"])
    if nested_step is not None:
        nested_step["resource_refs"] = list(hybrid_step.get("resource_refs", []))
        nested_step["bundled_resource_refs"] = list(hybrid_step.get("bundled_resource_refs", []))
```

- [ ] **Step 6: Ensure broad phase/module bindings are marked as fallback-only in the projected runtime metadata**

```python
binding["scope_strength"] = "fallback"
binding["may_broaden_active_step_scope"] = False
```

- [ ] **Step 7: Run the compile-contract tests and verify they pass**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py -k "hybrid_steps_own_step_specific_resources or projects_narrow_step_and_optimization_resources or compatibility_runtime_does_not_broaden_hybrid_step_scope or preserves_runtime_bindable_parenting_paths" -v
```

Expected:
- All four targeted tests pass.

- [ ] **Step 8: Run the full compile suite to catch shared regressions**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py -v
```

Expected:
- Entire file passes.

- [ ] **Step 9: Commit the compile-contract implementation**

```bash
git add C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/instruction_understanding_service.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "feat: harden active snapshot resource and followup contracts"
```

### Task 3: Lock Planner Persistence and Resource-Precedence Regressions

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`
- Reference: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

- [ ] **Step 1: Add a failing planner test for Bible Tutor step-owned resources beating module-phase bindings**

```python
def test_planner_active_bible_tutor_step_does_not_widen_to_full_module_resources() -> None:
    state = make_state_for_bible_tutor_step(
        active_step_scope_id="step:observation",
        active_binding_ids=["phase:查經互動模組"],
    )

    out = planner.run(state)

    assert out["active_instruction_resources"] == ["observation_guide.md"]
```

- [ ] **Step 2: Add a failing planner test for Church Ministry clarification -> core progression**

```python
def test_planner_church_ministry_progresses_from_clarification_to_core_scope() -> None:
    state = make_state_for_church_ministry(
        active_step_scope_id="step:clarification",
        selected_routing_rule_id="routing:template_vs_dpo",
        user_query="請繼續",
    )

    out = planner.run(state)

    assert out["session_execution_state"]["active_step_scope_id"] == "step:core_workflow_execution"
    assert out["session_execution_state"]["primary_scope_title"] == "核心流程"
```

- [ ] **Step 3: Add a failing planner test for Church Ministry optimization persistence**

```python
def test_planner_church_ministry_optimization_turn_persists_executable_followup_scope() -> None:
    state = make_state_for_church_ministry(
        active_step_scope_id="step:core_workflow_execution",
        user_query="優化這個 Prompt",
    )

    out = planner.run(state)
    persisted = out["session_execution_state"]

    assert persisted["active_service_block_id"] == "followup_module:optimization_module"
    assert persisted["primary_scope_title"] == "Optimization Module"
    assert persisted["active_instruction_resources"] == [
        "Optimization Strategy Library.md",
        "dynamic_prompt_optimizer.md",
    ]
```

- [ ] **Step 4: Add a protected non-regression planner test for `與孩子一起成長`**

```python
def test_planner_parenting_route_still_persists_visible_workflow_state() -> None:
    state = make_state_for_parenting_app(user_query="最近在教養孩子時，我遇到的挑戰是…")

    out = planner.run(state)
    persisted = out["session_execution_state"]

    assert persisted["active_workflow"]
    assert persisted["primary_scope_title"]
```

- [ ] **Step 5: Run the targeted planner tests and verify they fail**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py -k "does_not_widen_to_full_module_resources or progresses_from_clarification_to_core_scope or optimization_turn_persists_executable_followup_scope or parenting_route_still_persists_visible_workflow_state" -v
```

Expected:
- Bible Tutor and Church Ministry tests fail before planner changes.
- Parenting non-regression should pass or expose an unexpected shared regression.

- [ ] **Step 6: Commit the red planner tests**

```bash
git add C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "test: lock planner persistence regressions for resource scope and optimization"
```

### Task 4: Narrow Planner Resource Precedence and Persistence

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Add one helper that resolves the canonical active resource scope before any broad binding expansion**

```python
def _canonical_active_resource_scope(state: dict) -> dict[str, object]:
    return {
        "active_step_scope_id": state.get("active_step_scope_id"),
        "active_service_block_id": state.get("active_service_block_id"),
        "resource_refs": list(state.get("resource_refs") or []),
        "bundled_resource_refs": list(state.get("bundled_resource_refs") or []),
    }
```

- [ ] **Step 2: Suppress broad phase expansion when the canonical active scope already owns resources**

```python
if canonical_scope["resource_refs"] or canonical_scope["bundled_resource_refs"]:
    selected_resource_ids = list(canonical_scope["resource_refs"]) + list(canonical_scope["bundled_resource_refs"])
else:
    selected_resource_ids = _expand_phase_bindings(...)
```

- [ ] **Step 3: Persist Church Ministry core workflow state from canonical step scope**

```python
if next_step_scope_id == "step:core_workflow_execution":
    session_execution_state["active_step_scope_id"] = next_step_scope_id
    session_execution_state["primary_scope_title"] = "核心流程"
```

- [ ] **Step 4: Promote Church Ministry optimization turn into the canonical executable follow-up module**

```python
if _is_optimization_turn(user_query, current_scope):
    session_execution_state["active_service_block_id"] = "followup_module:optimization_module"
    session_execution_state["primary_scope_id"] = "followup_module:optimization_module"
    session_execution_state["primary_scope_title"] = "Optimization Module"
    session_execution_state["active_instruction_resources"] = [
        "Optimization Strategy Library.md",
        "dynamic_prompt_optimizer.md",
    ]
```

- [ ] **Step 5: Add a validation check before returning persisted session state**

```python
def _validate_persisted_execution_path(session_execution_state: dict, runtime_registry: dict) -> None:
    active_service_block_id = session_execution_state.get("active_service_block_id")
    active_step_scope_id = session_execution_state.get("active_step_scope_id")
    if active_service_block_id and active_service_block_id not in runtime_registry["service_blocks"]:
        raise ValueError(f"Unknown active_service_block_id: {active_service_block_id}")
    if active_step_scope_id and active_step_scope_id not in runtime_registry["steps"]:
        raise ValueError(f"Unknown active_step_scope_id: {active_step_scope_id}")
```

- [ ] **Step 6: Run the targeted planner tests and verify they pass**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py -k "does_not_widen_to_full_module_resources or progresses_from_clarification_to_core_scope or optimization_turn_persists_executable_followup_scope or parenting_route_still_persists_visible_workflow_state" -v
```

Expected:
- All four targeted planner tests pass.

- [ ] **Step 7: Run the full planner suite**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py -v
```

Expected:
- Entire file passes.

- [ ] **Step 8: Commit the planner implementation**

```bash
git add C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "feat: enforce canonical planner resource scope and persistence"
```

### Task 5: Lock GUI Payload Regressions

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Modify if needed: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py`

- [ ] **Step 1: Add a failing GUI payload test for Bible Tutor narrow step scope**

```python
def test_session_messages_workflow_status_bible_tutor_narrow_step_scope_payload() -> None:
    payload = fetch_session_messages_payload_for_bible_tutor_step("step:observation")

    assert payload["workflow_status"]["current_step"] == "細察事實 (Observation)"
    assert payload["messages"][-1]["retrievalSummary"]["selectedInstructionFiles"] == ["observation_guide.md"]
```

- [ ] **Step 2: Add a failing GUI payload test for Church Ministry core workflow visibility**

```python
def test_session_messages_workflow_status_shows_core_workflow_when_core_scope_is_active() -> None:
    payload = fetch_session_messages_payload_for_church_ministry("step:core_workflow_execution")

    assert payload["workflow_status"]["current_step"] == "核心流程"
```

- [ ] **Step 3: Add a failing GUI payload test for Church Ministry optimization visibility**

```python
def test_session_messages_workflow_status_shows_optimization_module_when_followup_scope_is_active() -> None:
    payload = fetch_session_messages_payload_for_church_ministry("followup_module:optimization_module")

    assert payload["workflow_status"]["current_step"] == "Optimization Module"
    assert payload["messages"][-1]["retrievalSummary"]["selectedInstructionFiles"] == [
        "Optimization Strategy Library.md",
        "dynamic_prompt_optimizer.md",
    ]
```

- [ ] **Step 4: Add a protected non-regression GUI payload test for `與孩子一起成長`**

```python
def test_session_messages_workflow_status_parenting_app_still_shows_visible_routed_workflow() -> None:
    payload = fetch_session_messages_payload_for_parenting_route()

    assert payload["workflow_status"]["workflow_title"]
    assert payload["workflow_status"]["current_step"]
```

- [ ] **Step 5: Run the targeted GUI payload tests and verify they fail if planner payload is still wrong**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py -k "bible_tutor_narrow_step_scope_payload or shows_core_workflow_when_core_scope_is_active or shows_optimization_module_when_followup_scope_is_active or parenting_app_still_shows_visible_routed_workflow" -v
```

Expected:
- Bible Tutor and Church Ministry tests fail before final payload alignment.
- Parenting non-regression should pass.

- [ ] **Step 6: If needed, make a minimal GUI-payload alignment change in `main.py`**

```python
workflow_status["current_step"] = (
    runtime_snapshot.get("primary_scope_title")
    or runtime_snapshot.get("active_step_title")
    or workflow_status.get("current_step")
)
```

- [ ] **Step 7: Run the targeted GUI payload tests and verify they pass**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py -k "bible_tutor_narrow_step_scope_payload or shows_core_workflow_when_core_scope_is_active or shows_optimization_module_when_followup_scope_is_active or parenting_app_still_shows_visible_routed_workflow" -v
```

Expected:
- All four targeted GUI payload tests pass.

- [ ] **Step 8: Commit the builder-facing payload alignment**

```bash
git add C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py
git commit -m "test: lock gui payload regressions for step and optimization scope"
```

### Task 6: Run the Practical Standard and Live-Readiness Verification

**Files:**
- No code changes expected.
- Verify against:
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_llm_runtime_compat.py`

- [ ] **Step 1: Run compile-contract gate**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py -v
```

Expected:
- PASS

- [ ] **Step 2: Run planner/runtime persistence gate**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py -v
```

Expected:
- PASS

- [ ] **Step 3: Run GUI payload gate**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py -k "bible_tutor_narrow_step_scope_payload or shows_core_workflow_when_core_scope_is_active or shows_optimization_module_when_followup_scope_is_active or parenting_app_still_shows_visible_routed_workflow" -v
```

Expected:
- PASS

- [ ] **Step 4: Run cross-app non-regression gate**

Run:

```powershell
python -m pytest C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_llm_runtime_compat.py -v
```

Expected:
- PASS

- [ ] **Step 5: Record live verification checklist for manual run**

```text
Bible Tutor:
- starter "我想查考一段經文"
- confirm only observation guide loads at observation step
- advance step and confirm only identify-relationships guide loads

Church Ministry:
- starter prompt-designer question
- confirm clarification resources are narrow
- continue to core and confirm GUI shows 核心流程
- optimize prompt and confirm GUI shows Optimization Module and only optimization files load

與孩子一起成長:
- rerun one working starter
- confirm routed workflow/mode still shows
```

- [ ] **Step 6: Commit the verification-backed completion state**

```bash
git add C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_instruction_understanding_service.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/instruction_understanding_service.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py
git commit -m "feat: harden snapshot-first runtime scope for bible tutor and church ministry"
```

## Self-Review

- Spec coverage:
  - Snapshot contract hardening is covered in Tasks 1-2.
  - Planner precedence and persistence consistency is covered in Tasks 3-4.
  - GUI payload consistency is covered in Task 5.
  - Protected non-regression for `與孩子一起成長` is covered in Tasks 1, 3, and 5.
- Placeholder scan:
  - No `TBD`, `TODO`, or deferred implementation placeholders remain.
- Type consistency:
  - The plan uses the same canonical concepts throughout:
    - `procedure_steps.resource_refs`
    - `followup_module:optimization_module`
    - `active_step_scope_id`
    - `active_service_block_id`
    - `primary_scope_title`
