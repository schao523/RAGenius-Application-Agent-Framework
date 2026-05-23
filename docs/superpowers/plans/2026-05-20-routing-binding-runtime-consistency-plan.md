# Routing Binding Runtime Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make compiled route selection, executable target binding, and GUI-visible workflow state consistent across Bible Tutor, 與孩子一起成長, and Church Ministry without changing retrieval behavior or breaking other apps.

**Architecture:** Keep the fix inside the compile/runtime projection and planner layers. The compiler must emit a canonical runtime contract that can resolve routes to executable targets, and the planner must arbitrate shadow-vs-compiled routes, persist concrete workflow/module state, and preserve logic-only routing when appropriate.

**Tech Stack:** Python, unittest, SQLite-backed persisted session state, existing `planner.py` hybrid-active runtime path, existing `instruction_understanding_service.py` compile normalization.

---

## File Structure

- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
  - Add route-evidence arbitration so shadow-selected routing rules cannot override stronger compiled rule evidence.
  - Resolve role-targeted routes to concrete executable workflow/module targets where possible.
  - Persist GUI-facing workflow/module/step state consistently for hybrid-active sessions.
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
  - Strengthen hybrid runtime projection so executable workflow ids used by semantic role/workflow routing are also present in the runtime service-block/procedure shape when appropriate.
  - Preserve module-owned procedure ownership and prevent role/workflow aliases from drifting away from executable ids.
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
  - Add route-arbitration regressions for Bible Tutor.
  - Add role-to-executable binding regressions for 與孩子一起成長.
  - Add clarification/default workflow binding regressions for Church Ministry.
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
  - Add compile/projection regressions for runtime-executable workflow/service-block consistency across semantic workflow ids and hybrid runtime ids.
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
  - Extend GUI-facing workflow status regression coverage where needed after planner/compiler changes.

## Task 1: Lock Bible Tutor route arbitration in planner tests

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Write the failing tests**

Add tests that model Bible Tutor hybrid routing with:
- compiled rules:
  - `route_to_bible_study` keywords `查考, 研經, 經文`
  - `route_to_life_application` keywords `生活, 應用, 挑戰, 困難, 方向`
- shadow output incorrectly selecting `route_to_bible_study`
- query `我正在面對生活中的一些問題，想知道聖經怎麼教導或給我方向。`

Expected assertions:
- selected routing rule becomes `route_to_life_application`
- no module queue is activated on entry
- no `active_step_scope_id` is set

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_bible_tutor_life_guidance_query_prefers_life_application_over_shadow_bible_study`

Expected: `FAIL` because planner currently trusts shadow-selected `route_to_bible_study`.

- [ ] **Step 3: Write minimal planner arbitration code**

In `planner.py`, add a helper that:
- computes deterministic best-match route from compiled `routing_rules`
- compares shadow-selected rule against deterministic evidence
- prefers deterministic rule when:
  - deterministic rule has explicit trigger evidence
  - shadow-selected rule conflicts with it
  - shadow-selected route would bind a more specific executable study path

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_bible_tutor_life_guidance_query_prefers_life_application_over_shadow_bible_study`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/workflows/nodes/planner.py
git commit -m "test/feat: arbitrate hybrid routes against compiled evidence"
```

## Task 2: Lock 與孩子一起成長 role-to-executable binding in planner tests

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Write the failing tests**

Add tests for a hybrid-active session where:
- route selects `route_behavior_to_consultant`
- route target is `role`
- role profile permits `3x1_advice_workflow`
- semantic workflow exists
- hybrid runtime currently lacks matching active executable binding

Expected assertions:
- persisted/session execution state gets a concrete workflow or service-block binding
- GUI-facing workflow status inputs are non-null:
  - `active_workflow` or `active_service_block_id`
  - `primary_scope_id`

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_grow_with_children_role_route_resolves_to_executable_target`

Expected: `FAIL` because the current state only persists role + routing rule.

- [ ] **Step 3: Write minimal planner binding code**

In `planner.py`, when a route targets a role:
- inspect role-permitted workflows/modules from compiled runtime/semantic metadata
- resolve to one executable target
- persist:
  - `active_workflow` or `active_service_block_id`
  - `primary_scope_id`
  - `primary_scope_type`
  - `active_execution_mode` when known

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_grow_with_children_role_route_resolves_to_executable_target`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/workflows/nodes/planner.py
git commit -m "test/feat: resolve role routes to executable runtime targets"
```

## Task 3: Lock Church Ministry clarification binding in tests

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Write the failing tests**

Add:
- a compiler/projection test ensuring hybrid/default workflow ids match executable workflow registry ids for Church Ministry
- a planner test where a starter needing clarification activates the clarification/default workflow and first interactive step

Expected assertions:
- hybrid `default_workflow_id` resolves to actual executable workflow/service-block id
- planner persists active workflow/step

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_church_ministry_hybrid_default_workflow_matches_executable_registry`
- `python -m unittest ragenius_app_skeleton.tests.test_planner_node.PlannerNodeTests.test_church_ministry_prompt_designer_starter_binds_clarification_workflow`

Expected: `FAIL`

- [ ] **Step 3: Write minimal compiler projection code**

In `instruction_understanding_service.py`:
- when semantic workflow ids are part of the active contract, ensure the hybrid runtime model projects executable workflow/service-block ids that the planner can bind directly
- normalize `default_workflow_id`, workflow service blocks, procedure owners, and clarification gate refs to the same canonical executable id family

- [ ] **Step 4: Run tests to verify they pass**

Run the two targeted tests above.

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/tests/test_instruction_understanding_service.py ragenius_app_skeleton/tests/test_planner_node.py ragenius_app_skeleton/backend/app/instruction_understanding_service.py
git commit -m "test/feat: align church workflow projection with runtime bindings"
```

## Task 4: Preserve module-owned procedure integrity and support-module boundaries

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] **Step 1: Write the failing tests**

Add regressions that assert:
- module-owned procedures remain owned by the module
- support modules are not auto-promoted when a logic-only route is active
- nested/runtime projection does not create a second executable identity for the same concept

- [ ] **Step 2: Run tests to verify they fail**

Run the new targeted tests.

Expected: `FAIL`

- [ ] **Step 3: Write minimal compiler/planner code**

In `instruction_understanding_service.py`:
- keep one executable identity across route target, service block, and procedure owner

In `planner.py`:
- do not auto-promote support modules when the resolved route is logic-only
- preserve module-owned step binding only when the route actually selected that module

- [ ] **Step 4: Run tests to verify they pass**

Run the targeted tests added in Step 1.

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/backend/app/instruction_understanding_service.py ragenius_app_skeleton/workflows/nodes/planner.py ragenius_app_skeleton/tests/test_instruction_understanding_service.py ragenius_app_skeleton/tests/test_planner_node.py
git commit -m "test/feat: preserve module ownership and support boundaries"
```

## Task 5: Verify GUI-facing workflow status and cross-app non-regression

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Test: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Write the failing GUI-facing regression if needed**

If planner/compiler fixes do not already guarantee it, add a builder integration test asserting:
- `與孩子一起成長` routed starter exposes workflow status
- Church Ministry clarification starter exposes workflow status
- Bible Tutor life-application starter does not expose Bible-study step status

- [ ] **Step 2: Run targeted integration tests to verify failure**

Run the new targeted builder integration test(s).

Expected: `FAIL` before final wiring is complete.

- [ ] **Step 3: Write minimal glue code**

Only if required by the failing integration tests, adjust planner/main status projection to surface already-persisted workflow/service-block/step fields correctly.

- [ ] **Step 4: Run full verification**

Run:
- `python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service`
- `python -m unittest ragenius_app_skeleton.tests.test_planner_node`
- `python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration`
- `python -m unittest ragenius_app_skeleton.tests.test_llm_runtime_compat`

Expected:
- all pass
- no regression in Bible Tutor module-step behavior
- no regression in Church Ministry clarification behavior
- no regression in existing support-module behaviors

- [ ] **Step 5: Commit**

```bash
git add ragenius_app_skeleton/tests/test_builder_chat_integration.py ragenius_app_skeleton/backend/app/main.py ragenius_app_skeleton/workflows/nodes/planner.py
git commit -m "test/feat: surface routed workflow state consistently in gui payloads"
```

## Self-Review

- Spec coverage:
  - Bible Tutor route arbitration: covered in Task 1
  - 與孩子一起成長 role/executable binding: covered in Task 2
  - Church Ministry clarification binding: covered in Task 3
  - module ownership/support boundaries: covered in Task 4
  - GUI-visible routed status: covered in Task 5
- Placeholder scan:
  - No `TODO`, `TBD`, or “appropriate handling” placeholders remain
- Type consistency:
  - Plan consistently refers to:
    - `selected_routing_rule_id`
    - `active_workflow`
    - `active_service_block_id`
    - `primary_scope_id`
    - `default_workflow_id`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-20-routing-binding-runtime-consistency-plan.md`.

Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

This session is proceeding with inline execution because the user explicitly asked to execute it test-first in the current session.
