# Routing And Runtime Contract Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate recurring compile, routing, runtime persistence, and GUI-state regressions across Bible Tutor, ???????, and Church Ministry by enforcing one canonical contract from compiled understanding through persisted session state.

**Architecture:** Treat these failures as contract bugs, not app-specific bugs. The canonical source of truth is the compiled hybrid runtime model; routing arbitration, executable target resolution, nested runtime projection, and persisted session state must all derive from it without inventing parallel ids or fallback-only paths. Fixes must be verified at four layers: compile contract, planner/runtime persistence, GUI payload, and cross-app non-regression.

**Tech Stack:** Python, FastAPI, SQLite (`runtime_state.db`), compiled understanding snapshots, planner/runtime state models, unittest.

---

## Issue Summary

1. **Compiled routing is not authoritative enough**
- Hybrid shadow routing can still win against stronger compiled evidence.
- Some active snapshots omit normalized `trigger_keywords`, so deterministic arbitration cannot work live.

2. **Role/logic routes do not always resolve to executable runtime targets**
- Some apps compile role-only routes without projecting concrete workflow/module service blocks.
- Result: `active_workflow`, `active_service_block_id`, and `active_step_scope_id` remain null.

3. **Canonical ids still drift by layer**
- The same concept can appear with different ids in routing, logic blocks, service blocks, procedures, follow-up modules, and session state.
- This recurrence has appeared as workflow/module drift in all three apps.

4. **Nested `instruction_runtime_model` is still not guaranteed to be a pure compatibility projection**
- Legacy broad module shapes and pseudo-step queues can override cleaner canonical runtime shapes.
- Result: broad resource loading and wrong GUI/module state.

5. **Module-owned procedures and follow-up modules are not consistently first-class executable paths**
- Bible Tutor module-owned study flow and Church Ministry optimization module both show this weakness in different forms.

6. **Persisted session state can be internally inconsistent**
- Route id, role id, workflow id, support module id, and active step can describe different paths in the same session row.

7. **Validation does not yet enforce the full runtime contract**
- Invalid or weak shapes still publish or persist, then fail later in planner/runtime/GUI.

## Practical Standard

Do not call a recurring issue fixed unless all four are true:
- compile contract test passes
- planner/runtime persistence test passes
- GUI payload test passes
- cross-app non-regression suite passes

## File Map

- `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
  - Compile-time normalization and validation of routing rules, logic blocks, service blocks, procedures, steps, follow-up modules, and nested runtime projection.
- `ragenius_app_skeleton/workflows/nodes/planner.py`
  - Route arbitration, role-to-executable resolution, module/follow-up activation, step activation, session-state shaping, and resource planning.
- `ragenius_app_skeleton/workflows/nodes/load_template_registry.py`
  - Rehydration of persisted session state into runtime execution state; must enforce state consistency rather than accepting drift.
- `ragenius_app_skeleton/workflows/runtime_models.py`
  - Session execution state invariants and validation rules.
- `ragenius_app_skeleton/backend/app/main.py`
  - GUI payload shaping for workflow/module/step status.
- `ragenius_app_skeleton/backend/app/chat_repos.py`
  - Durable session persistence surface; useful for persistence-level regression coverage, not primary fix target.
- `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
  - Compile contract regression suite.
- `ragenius_app_skeleton/tests/test_planner_node.py`
  - Planner/runtime persistence regressions.
- `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - GUI payload regressions.
- `ragenius_app_skeleton/tests/test_chat_repos.py`
  - Durable session persistence regressions where needed.

### Task 1: Lock Cross-App Contract Regressions

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Add failing compile-contract tests for active snapshot shape gaps**

Add regressions that assert:
- Bible Tutor `routing_rules[*].trigger_keywords` are populated from logic-block triggers.
- `???????` role routes project concrete executable parenting targets into runtime-bindable service blocks.
- Church Ministry optimization follow-up module uses one canonical id across follow-up modules and service blocks.

- [ ] **Step 2: Add failing planner/runtime persistence tests for the observed live sessions**

Add regressions that assert:
- Bible Tutor life-guidance starter persists Life Application route instead of Bible Study when compiled evidence favors it.
- `???????` routed starter persists non-null executable workflow/module state.
- Church Ministry optimization turn persists the optimization module, not only bundled step `2*` pseudo-steps.

- [ ] **Step 3: Add failing GUI payload tests for visible routed state**

Add regressions that assert:
- Bible Tutor GUI status shows Life Application for the life-guidance starter.
- `???????` GUI status shows a routed parenting workflow/mode.
- Church Ministry GUI status shows `Optimization Module` when optimization is activated.

- [ ] **Step 4: Run only the new targeted tests and confirm failure reasons match the known bugs**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service -k routing
python -m unittest ragenius_app_skeleton.tests.test_planner_node -k optimization
python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration -k workflow_status
```
Expected: failures that demonstrate missing trigger projection, missing executable role binding, and wrong optimization follow-up activation.

### Task 2: Make Compiled Routing Rules Self-Sufficient

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Project normalized routing evidence onto runtime routing rules**

Implement compile-time projection so each hybrid runtime `routing_rule` includes normalized fields needed by planner arbitration:
- `trigger_keywords`
- canonical `target_type`
- canonical `target_id`
- `target_logic_block_id` when present
- stable priority

- [ ] **Step 2: Enforce route-target canonicalization through one registry**

Normalize routes so they cannot carry module ids in workflow fields or follow-up ids under alternate prefixes. Route targets must resolve through the same canonical executable-target registry used for service blocks and procedures.

- [ ] **Step 3: Run compile-contract tests and confirm pass**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service
```
Expected: all compile-contract regressions pass; no duplicate or missing canonical route target fields remain.

### Task 3: Project Role Routes To Concrete Executable Targets

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Compile executable parenting workflows for `???????`-style role routes**

When an app is `intent_routed_interaction_logic` and routes to roles that are meant to enter concrete workflows, project those executable workflows into the runtime service-block registry with canonical ids matching what planner/runtime will persist.

- [ ] **Step 2: Resolve route-selected role to executable target at runtime**

Planner must convert the chosen role into exactly one of:
- executable workflow
- executable module
- explicit logic-only mode

If logic-only, GUI payload must still expose the mode consistently. If executable, persist workflow/module ids immediately.

- [ ] **Step 3: Prevent route/role divergence in persisted session state**

If a route selects `mentor`, runtime must not later persist `consultant` in the same turn unless an explicit, validated transition occurs. Add a guard before session persistence.

- [ ] **Step 4: Run planner tests and confirm pass**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_planner_node
```
Expected: `???????` route starter persists concrete executable state and keeps route/role consistent.

### Task 4: Unify Follow-Up Module Activation For Church Ministry

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Modify: `ragenius_app_skeleton/workflows/runtime_models.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Canonicalize follow-up module ids at compile time**

Ensure optimization/tool-selection follow-up modules use one id across:
- `followup_modules`
- `instruction_service_blocks`
- procedure ownership
- session state
- GUI payload

- [ ] **Step 2: Bind executable follow-up module on optimization turns**

Planner must activate the optimization module itself on the optimization turn instead of staying only on bundled step `2*` pseudo-step ids.

- [ ] **Step 3: Load module-scoped optimization resource when module activates**

When optimization module is active, resource plan must include `Prompt Optimization Library.md` in addition to any step-specific resources.

- [ ] **Step 4: Rehydrate persisted state without alias drift**

`load_template_registry` and runtime state validation must accept only canonical follow-up module ids; no synthetic `step:workflow:2` should stand in for the module after activation.

### Task 5: Make Nested Runtime A Strict Compatibility Projection

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Generate nested `instruction_runtime_model` only from canonical hybrid runtime data**

Remove any independent broad module or pseudo-step shapes that disagree with canonical service blocks/procedures/steps.

- [ ] **Step 2: Preserve step-scoped resources in nested projection**

If a concrete step is active, nested runtime must not expand all module resources by default.

- [ ] **Step 3: Suppress broad support/module expansion when concrete executable scope exists**

Planner resource loading must prefer active step/module scope and avoid reintroducing broad legacy phase expansion.

### Task 6: Tighten Persistence And GUI Contract Validation

**Files:**
- Modify: `ragenius_app_skeleton/workflows/runtime_models.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/load_template_registry.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`

- [ ] **Step 1: Add state invariants before persistence and on rehydration**

Reject or repair session states where:
- route id, role id, workflow id, service block id, or support module id describe conflicting paths
- executable ids do not exist in canonical runtime service blocks

- [ ] **Step 2: Make GUI payload derive from canonical persisted runtime state**

GUI status should show:
- explicit logic mode when logic-only
- workflow/module/step when executable
- no silent empty payload when a routed path exists but was not projected

- [ ] **Step 3: Run GUI payload regressions and confirm pass**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration
```
Expected: routed GUI state is visible for all three apps in the known regression cases.

### Task 7: Run Practical-Standard Verification

**Files:**
- Test only

- [ ] **Step 1: Compile contract test passes**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service
```
Expected: PASS

- [ ] **Step 2: Planner/runtime persistence test passes**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_chat_repos
```
Expected: PASS

- [ ] **Step 3: GUI payload test passes**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration
```
Expected: PASS

- [ ] **Step 4: Cross-app non-regression suite passes**

Run:
```powershell
python -m unittest ragenius_app_skeleton.tests.test_llm_runtime_compat
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_validate_semantic_compile_candidate_preserves_existing_support_module_ids_for_cross_app_routes
python -m unittest ragenius_app_skeleton.tests.test_planner_node
```
Expected: PASS, including Bible Tutor, `???????`, Church Ministry, and unaffected support-module flows.

## Guardrails

- Do not touch `rag_subsystem`.
- Do not hardcode application ids or app names into planner/compiler logic.
- Preserve existing canonical support-module ids where already working.
- Prefer compile/runtime contract fixes over ad hoc GUI-only patches.
- Do not call the issue fixed unless all four practical-standard gates pass.

## Self-Review

- Spec coverage: covers compile-time routing normalization, runtime executable binding, nested-runtime projection, persistence validation, GUI payload, and cross-app regression requirements.
- Placeholder scan: no TBD/TODO placeholders remain; each task has a concrete verification step.
- Type consistency: uses the same canonical concepts throughout: routing rule, logic block, executable target, service block, procedure, step, persisted session state.
