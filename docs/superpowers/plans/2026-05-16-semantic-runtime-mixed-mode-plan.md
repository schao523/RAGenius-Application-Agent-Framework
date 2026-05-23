# Semantic Runtime Mixed-Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make hybrid app compile/publish/runtime behavior correct across procedural, executable intent-routed, and mixed conversational app families, while keeping invalid semantic models from being treated as active chat-ready models.

**Architecture:** Classify semantic route targets by capability, tighten publish/readiness semantics around valid active models, and finish planner follow-up scope activation so runtime state, resource binding, and admin/chat UX all agree on the same active semantic model.

**Tech Stack:** FastAPI, Python unittest, React/Vite, Builder-backed instruction snapshots, semantic hybrid runtime model

---

## File Structure

- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
  - semantic normalization, grounding, validation, publish policy, preview semantics
- Modify: `ragenius_app_skeleton/backend/app/main.py`
  - admin detail response shaping and readiness projection
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
  - active follow-up scope promotion and dependency resource binding
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
  - compile gating and instruction-understanding state derivation
- Modify: `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.jsx`
  - active-vs-attempt status rendering
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
  - validator, publish, preview regression tests
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - admin detail and workflow status integration tests
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
  - follow-up activation and resource-loading tests
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`
  - compile gating tests
- Modify: `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.test.jsx`
  - panel status rendering tests

### Task 1: Fix frontend compile gating semantics

**Files:**
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Test: `ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing frontend test for invalid semantic hybrid models**

Add a case around `resolveInstructionUnderstandingState` coverage that asserts a hybrid app with a compiled id but `semantic_compile_valid = false` still yields `compileRequired = true`.

```jsx
it("keeps compileRequired true for hybrid apps when semantic validity is false", () => {
  const preview = {
    compiled_id: "record-1",
    compile_required: false,
    semantic_compile_attached: true,
    semantic_compile_valid: false,
    primary_service_mode: "intent_routed_multi_workflow",
  };

  const state = resolveInstructionUnderstandingState({
    instruction_understanding_preview: preview,
  });

  expect(state.compileRequired).toBe(true);
});
```

- [ ] **Step 2: Run the targeted frontend test to verify it fails**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- App.test.jsx
```

Expected:

- test fails because current logic only checks `compile_required || !compiled_id`

- [ ] **Step 3: Implement semantic-validity-aware compile gating**

Update the state derivation so hybrid modes require semantic validity before chat is treated as ready.

```jsx
const hybridMode = new Set([
  "single_default_workflow",
  "intent_routed_multi_workflow",
  "hybrid_active",
]);

const requiresValidSemanticModel =
  hybridMode.has(String(preview.primary_service_mode || "").trim()) ||
  preview.semantic_compile_attached;

const compileRequired = Boolean(
  preview.compile_required ||
  !preview.compiled_id ||
  (requiresValidSemanticModel && preview.semantic_compile_valid === false)
);
```

- [ ] **Step 4: Run the targeted frontend test to verify it passes**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- App.test.jsx
```

Expected:

- `PASS`

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/App.test.jsx
git commit -m "fix: require semantic validity for hybrid chat readiness"
```

### Task 2: Prevent invalid semantic models from becoming active

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Write the failing backend test for invalid-active publish prevention**

Add a test that compiles an invalid semantic attempt for an app with no prior valid semantic model and asserts:
- `publish_status != "active"`
- preview indicates compile-required / no valid semantic model

```python
def test_invalid_semantic_compile_without_prior_valid_model_stays_diagnostic_only():
    record = compile_instruction_understanding(...)
    assert record["publish_status"] == "diagnostic_only"
    assert record["compiled_contract"]["semantic_compile"]["valid"] is False
```

- [ ] **Step 2: Run the targeted backend test to verify it fails**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -k invalid_semantic_compile_without_prior_valid_model
```

Expected:

- failure because invalid semantic models can still publish `active`

- [ ] **Step 3: Tighten publish policy**

In `_should_publish_compiled_record(...)`, require semantic validity before publishing hybrid semantic models as active.

```python
if semantic_attached and not semantic_valid:
    return False
```

Add or preserve explicit diagnostic metadata so the latest failed attempt remains inspectable.

- [ ] **Step 4: Extend preview/detail semantics**

Make preview/detail payloads surface:
- active valid semantic model summary
- latest diagnostic-only attempt summary
- compile-required when no valid active semantic model exists

```python
preview["latest_attempt"] = {
    "compiled_id": latest_attempt.get("compiled_id"),
    "semantic_compile_valid": latest_attempt_semantic_valid,
    "validation_errors": latest_attempt_errors,
}
```

- [ ] **Step 5: Run the targeted backend test to verify it passes**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -k invalid_semantic_compile_without_prior_valid_model
```

Expected:

- `OK`

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/backend/app/instruction_understanding_service.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "fix: keep invalid semantic compile attempts diagnostic only"
```

### Task 3: Add mixed-mode validation for Bible Tutor-style apps

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Write failing validator tests for mixed-mode routing**

Add tests asserting:
- procedural route `wf:bible_study` requires executable steps
- conversational routes `wf:theology_discussion`, `wf:life_application`, `wf:general_qna` are valid without steps when grounded interaction semantics exist

```python
def test_mixed_mode_validator_allows_conversational_routes_without_procedure_steps():
    candidate = {...}
    result = _validate_semantic_compile_candidate(candidate, deterministic_contract)
    assert result["valid"] is True
```

- [ ] **Step 2: Run the targeted validator tests to verify failure**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -k mixed_mode_validator
```

Expected:

- failure because current validator requires executable `procedure_steps` for all routed workflows

- [ ] **Step 3: Introduce route capability classification**

Add normalization/grounding helpers that derive per-route capability:

```python
def _classify_route_target_capability(route_target, deterministic_contract):
    ...
    return "procedural" | "conversational" | "module_only"
```

Use deterministic sections such as procedures, procedure steps, mode-detection blocks, and entry/interaction logic to infer the capability.

- [ ] **Step 4: Update validation rules to be capability-aware**

Replace blanket executable-step requirements with:

```python
if target_capability == "procedural":
    require_executable_steps(...)
elif target_capability == "conversational":
    require_grounded_interaction_semantics(...)
elif target_capability == "module_only":
    require_grounded_module_binding(...)
```

- [ ] **Step 5: Run the targeted validator tests to verify they pass**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -k mixed_mode_validator
```

Expected:

- `OK`

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/backend/app/instruction_understanding_service.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py
git commit -m "feat: support mixed procedural and conversational route validation"
```

### Task 4: Finish Church Ministry follow-up activation and dependency resource loading

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Write the failing planner test for follow-up scope activation**

Add a test where:
- bundled generation is complete
- optimization follow-up is semantically selected or queued
- planner must promote `followup_module:optimization_module` to active scope
- `Optimization Strategy Library.md` must appear in selected resources

```python
def test_planner_promotes_queued_followup_module_and_loads_dependency_resource():
    result = planner_node(...)
    assert result["runtime_state"]["active_service_block_type"] == "followup_module"
    assert "Optimization Strategy Library.md" in result["retrieval_summary"]["selected_resource_filenames"]
```

- [ ] **Step 2: Run the targeted planner test to verify it fails**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System
python -m unittest ragenius_app_skeleton.tests.test_planner_node -k queued_followup_module
```

Expected:

- failure because queued follow-up state may not be promoted into active scope and dependency binding

- [ ] **Step 3: Tighten follow-up promotion logic**

Update queued follow-up promotion so active scope, binding scope, and resource loading all resolve from the same selected follow-up block.

```python
if bundled_execution_completed and queued_followup_module_id:
    active_service_block_type = "followup_module"
    active_service_block_id = queued_followup_module_id
    active_binding_scope_ids.add(queued_followup_module_id)
```

- [ ] **Step 4: Add or update integration assertion**

In chat integration coverage, assert session/messages workflow status surfaces `Optimization Module` after optimization flow and includes the dependency resource.

```python
assert workflow_status["current_step"] == "Optimization Module"
assert "Optimization Strategy Library.md" in selected_resource_filenames
```

- [ ] **Step 5: Run the targeted planner and integration tests**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System
python -m unittest ragenius_app_skeleton.tests.test_planner_node -k queued_followup_module
python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration -k followup_module
```

Expected:

- `OK`

- [ ] **Step 6: Commit**

```bash
git add ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/tests/test_builder_chat_integration.py
git commit -m "fix: promote semantic followup modules into active runtime scope"
```

### Task 5: Improve admin panel visibility of active model versus latest failed attempt

**Files:**
- Modify: `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Test: `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.test.jsx`

- [ ] **Step 1: Write the failing panel test for latest failed attempt visibility**

Add a panel test asserting the UI can display:
- active model validity
- latest failed attempt exists
- latest failed attempt error summary

```jsx
it("shows latest failed attempt separately from active model", () => {
  render(<InstructionsPanel understandingDetail={detail} ... />);
  expect(screen.getByText(/latest failed attempt/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the targeted panel test to verify it fails**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- InstructionsPanel.test.jsx
```

Expected:

- failure because panel currently only renders a coarse compiled/review/cache status

- [ ] **Step 3: Implement active-vs-attempt display**

Render separate sections or labels for:
- active compiled model
- latest failed attempt
- validation error summary

```jsx
{latestAttempt && latestAttempt.semantic_compile_valid === false ? (
  <div>
    <strong>Latest failed attempt</strong>
    <pre>{latestAttempt.validation_errors.join("\n")}</pre>
  </div>
) : null}
```

- [ ] **Step 4: Run the targeted panel test to verify it passes**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- InstructionsPanel.test.jsx
```

Expected:

- `PASS`

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/frontend/src/components/InstructionsPanel.jsx ragenius_app_skeleton/frontend/src/components/InstructionsPanel.test.jsx ragenius_app_skeleton/frontend/src/App.jsx
git commit -m "feat: show latest failed instruction-understanding attempts in admin ui"
```

### Task 6: Re-verify the three real apps

**Files:**
- No new source files required
- Test: targeted backend test files above

- [ ] **Step 1: Run backend regression suites**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service
python -m unittest ragenius_app_skeleton.tests.test_planner_node
python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration
```

Expected:

- all pass

- [ ] **Step 2: Run targeted frontend regression suites**

Run:

```powershell
cd C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- App.test.jsx InstructionsPanel.test.jsx
```

Expected:

- all pass

- [ ] **Step 3: Manual acceptance checks**

Use the live frontend/backend pair and verify:

- Church Ministry
  - compile valid
  - optimization activates follow-up scope
  - `Optimization Strategy Library.md` loads

- `與孩子一起成長`
  - compiled model remains active and valid
  - routed session behaves more concretely than the old pseudo-workflow shape

- Bible Tutor
  - compile is valid for mixed-mode structure
  - Bible Study retains executable-step path
  - conversational modes no longer fail merely for lacking fixed step sequences
  - invalid-model warning behavior matches semantic validity

- [ ] **Step 4: Commit final verification-safe changes**

```bash
git add -A
git commit -m "fix: align mixed-mode semantic runtime validation and readiness"
```

## Self-Review

Spec coverage:

- Mixed-mode validator design: covered in Task 3
- Active-vs-attempt publish/readiness semantics: covered in Tasks 1, 2, and 5
- Church Ministry follow-up activation/resource loading: covered in Task 4
- `與孩子一起成長` protection against pseudo-workflow regressions: covered through strict executable-route handling in Task 3 and final acceptance in Task 6

Placeholder scan:

- No `TODO`, `TBD`, or deferred placeholders remain

Type consistency:

- `semantic_compile_valid`, `compileRequired`, `publish_status`, `procedure_steps`, and `followup_module` names are consistent with current code terminology

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-16-semantic-runtime-mixed-mode-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
