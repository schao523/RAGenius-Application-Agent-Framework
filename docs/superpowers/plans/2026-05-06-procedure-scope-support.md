# Procedure Scope Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a layered procedure/step/support-module contract so procedure-triggered turns keep the procedure as primary scope while step-selected resources and one primary support module are merged into execution and retrieval.

**Architecture:** Extend the runtime schema first, then teach the instruction parser to emit procedural scope structures and step activation metadata. Update the planner to select layered scopes and merge step/module requests, while keeping retrieval request-driven and backward compatible.

**Tech Stack:** Python, Pydantic, unittest, existing planner/retrieval runtime in `ragenius_app_skeleton`

---

### Task 1: Add layered scope models to the runtime contract

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/runtime_models.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_load_template_registry.py`

- [ ] **Step 1: Write failing model tests for layered procedure state**

Add tests that construct and serialize:
- `ProcedureStepActivation`
- `PrimarySupportModuleActivation`
- new layered fields on `SessionExecutionState`
- new provenance fields on `ResourceRequest`

Expected checks:
- default values are backward compatible
- `to_plain_dict()` preserves the new fields
- older payloads without the new fields still validate

- [ ] **Step 2: Run model-focused tests to verify failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry.LoadTemplateRegistryTests -v`
Expected: fail on missing models/fields

- [ ] **Step 3: Add the new runtime model types**

Add to `runtime_models.py`:
- `PrimaryScopeLayer` or equivalent explicit scope-selection payloads
- `ProcedureStepActivation`
- `PrimarySupportModuleActivation`

Extend:
- `ResourceRequest`
  - `source_layer`
  - `step_scope_id`
  - `support_module_id`
- `SessionExecutionState`
  - `primary_scope_id`
  - `primary_scope_type`
  - `primary_scope_title`
  - `active_step_scope_id`
  - `primary_support_module_id`
  - `primary_support_module_title`

- [ ] **Step 4: Re-run the model-focused tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry.LoadTemplateRegistryTests -v`
Expected: model serialization tests pass

---

### Task 2: Extend the instruction parser to emit procedural scope candidates

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/load_template_registry.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_load_template_registry.py`

- [ ] **Step 1: Write failing parser tests for procedural scope extraction**

Add tests proving the parser can emit:
- a procedure scope candidate from a narrative section like `Interaction Logic & Execution Flow`
- step records under that procedure
- a step activation payload that references:
  - direct step resources
  - one primary support module

Use Church Ministry-style fixtures for the parser-only tests.

- [ ] **Step 2: Run the new parser tests to verify failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry.LoadTemplateRegistryTests.test_<new_test_name> -v`
Expected: fail because procedure scope/step activation is not emitted yet

- [ ] **Step 3: Add parser extraction for procedural scopes and step activations**

In `load_template_registry.py`:
- distinguish procedure-oriented sections from support/resource sections
- emit procedure scope candidates separately from support module scope candidates
- add step-level activation metadata
- allow a step to declare one `primary_support_module_id`

Keep output additive so existing `instruction_modules`, `instruction_blocks`, and `phase_resource_bindings` remain available during migration.

- [ ] **Step 4: Re-run parser tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry.LoadTemplateRegistryTests -v`
Expected: parser tests pass, including existing registry/binding coverage

---

### Task 3: Update planner selection to use layered scopes

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Write failing planner tests for procedure-primary layering**

Add tests for both trigger scenarios:
1. direct module trigger
- module becomes primary scope
- no active step scope
- no primary support module scope

2. procedure trigger
- procedure becomes primary scope
- step becomes active step scope
- one support module becomes primary support module scope
- merged resource requests include step + module provenance

Use Church Ministry and one generic non-Church fixture.

- [ ] **Step 2: Run the focused planner tests to verify failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_<new_test_name> -v`
Expected: fail because planner currently only has flat selected workflow/module/block state

- [ ] **Step 3: Implement layered scope selection in planner**

In `planner.py`:
- keep pre-routing classification unchanged
- add procedure selection output separate from support-module selection
- when a procedure is selected:
  - persist procedure as primary scope
  - resolve current step
  - derive step activation
  - optionally resolve one primary support module from that step
- when no procedure is selected but a module is directly triggered:
  - promote module as primary scope

Update `session_execution_state` construction to populate the new layered fields.

- [ ] **Step 4: Add request provenance when building merged resource requests**

When planner emits `ResourceRequest`s, populate:
- `source_layer`
- `step_scope_id`
- `support_module_id`

Expected source values:
- `procedure_step`
- `support_module`
- `direct_query`

- [ ] **Step 5: Re-run planner tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node -v`
Expected: old and new planner tests pass

---

### Task 4: Keep retrieval request-driven while honoring new provenance

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/retrieve.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_retrieve_node.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py`

- [ ] **Step 1: Write failing retrieval tests for layered request provenance**

Add tests asserting that retrieval:
- consumes merged resource requests without needing to understand app-specific procedure names
- preserves step/module provenance in summaries/debug trace
- stays app-scoped

- [ ] **Step 2: Run the focused retrieval tests to verify failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_retrieve_node -v`
Expected: fail on missing provenance fields or summary propagation

- [ ] **Step 3: Update retrieval summary/debug handling**

In `retrieve.py`:
- keep selection request-driven
- do not add procedure-specific logic
- preserve `source_layer`, `step_scope_id`, and `support_module_id` in prepared/summary state where relevant

- [ ] **Step 4: Re-run retrieval and pipeline tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v`
Expected: retrieval and pipeline tests pass

---

### Task 5: Persist and expose layered scope metadata

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/persist_run.py`
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/chat_service.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_persist_run_node.py`
- Test: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py`

- [ ] **Step 1: Write failing persistence tests for layered scope summary fields**

Add tests asserting summaries now expose:
- `primary_scope`
- `active_step_scope`
- `primary_support_module_scope`
- request provenance summary

- [ ] **Step 2: Run persistence tests to verify failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_persist_run_node -v`
Expected: fail on missing fields

- [ ] **Step 3: Update summary derivation**

In `persist_run.py` and `chat_service.py`:
- derive layered scope fields from `turn_execution_plan` and `session_execution_state`
- do not remove existing legacy-compatible summary fields yet

- [ ] **Step 4: Re-run persistence and runtime-contract tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_persist_run_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v`
Expected: pass

---

### Task 6: Add cross-app regressions for both trigger scenarios

**Files:**
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_load_template_registry.py`
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py`
- Modify: `C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py`

- [ ] **Step 1: Add Church Ministry regression**

Cover:
- procedure primary scope = `Interaction Logic & Execution Flow`
- support module scope = `Knowledge Modules` or `Instruction Modules`
- merged requests include proper provenance

- [ ] **Step 2: Add GPT Application Design Assistant regression**

Cover:
- direct module trigger path
- module becomes primary scope when no procedure is selected

- [ ] **Step 3: Add Vibe Story Director regression**

Cover:
- procedure/starter remains primary scope
- active step may activate one support module
- artifact contract remains intact

- [ ] **Step 4: Run cross-app tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v`
Expected: pass

---

### Task 7: Full verification and cleanup

**Files:**
- Verify only; no required file creation

- [ ] **Step 1: Run the broader backend verification set**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_load_template_registry ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_persist_run_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts ragenius_app_skeleton.tests.test_builder_chat_integration -v`

Expected: all targeted tests pass

- [ ] **Step 2: Review for compatibility drift**

Check that existing fields still populate:
- `selected_instruction_block`
- `active_binding_ids`
- `active_workflow`
- `active_step_order`

Expected: old tests remain green while new layered fields are authoritative for new logic

- [ ] **Step 3: Commit**

```bash
git add C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/runtime_models.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/load_template_registry.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/planner.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/retrieve.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/workflows/nodes/persist_run.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/chat_service.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_load_template_registry.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_planner_node.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_retrieve_node.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_persist_run_node.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py         C:/Users/User/Documents/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/tests/test_builder_chat_integration.py

git commit -m "feat: layer procedure scope over step and support module activation"
```
