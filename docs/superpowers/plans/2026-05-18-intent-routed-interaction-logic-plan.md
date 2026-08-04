# Intent-Routed Interaction Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** introduce `intent_routed_interaction_logic` as the correct top-level contract for rule-routed apps, keep executable target validation explicit, and align runtime/UI behavior with logic-first applications.

**Architecture:** update compiler mode selection, add a new validator/normalizer branch for rule-routed interaction apps, then adjust runtime/UI assumptions so logic-only routes are valid without executable steps.

**Tech Stack:** Python, FastAPI, unittest, React/Vite

---

## File Structure

- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.jsx`
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Modify: `ragenius_app_skeleton/tests/test_builder_chat_integration.py`
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.test.jsx`

## Task 1: Add failing backend tests for the new mode

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] Add a failing test that a rule-routed app with logic blocks and routing rules is valid under `intent_routed_interaction_logic` without `primary_workflow` or global `procedure_steps`.
- [ ] Add a failing test that `與孩子一起成長`-shaped semantics no longer fail for missing top-level executable workflows.
- [ ] Add a failing test that a true executable multi-workflow app still requires executable workflow targets under `intent_routed_multi_workflow`.
- [ ] Run the targeted tests and confirm failure before implementation.

## Task 2: Update compile prompt and semantic mode selection

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

- [ ] Replace the binary mode prompt contract with a three-way mode contract:
  - `single_default_workflow`
  - `intent_routed_multi_workflow`
  - `intent_routed_interaction_logic`
- [ ] Ensure rule-routed, logic-first apps are directed toward the new mode.
- [ ] Keep backward compatibility for existing compiled records and legacy prompt consumers.

## Task 3: Implement validation branch for `intent_routed_interaction_logic`

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

- [ ] Add validator rules for `intent_routed_interaction_logic`.
- [ ] Require `routing_rules` or `interaction_logic_blocks`.
- [ ] Remove the mode-wide requirement for:
  - `primary_workflow`
  - global `procedure_steps`
- [ ] Keep executable validation for explicit workflow/module targets when they are present.
- [ ] Preserve current strict validation for `single_default_workflow` and `intent_routed_multi_workflow`.

## Task 4: Adjust normalization to preserve logic-first apps

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

- [ ] Keep orchestration and routing policy in `interaction_logic_blocks`.
- [ ] Ensure missing executable targets no longer invalidate the whole app when the top-level mode is `intent_routed_interaction_logic`.
- [ ] Preserve existing explicit-target resolution for real workflows/modules.
- [ ] Confirm `多重需求分層規則` and similar blocks never need to be rewritten into workflows under the new mode.

## Task 5: Update preview/readiness semantics

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.jsx`
- Modify tests in frontend/backend integration

- [ ] Make preview payloads surface the new mode clearly.
- [ ] Ensure chat readiness for `intent_routed_interaction_logic` does not require executable step ownership.
- [ ] Keep error display accurate when executable routes fail within the logic-first mode.
- [ ] Add UI tests for logic-only valid models versus executable invalid models.

## Task 6: Fix planner/runtime handling of logic-only routes

**Files:**
- Modify: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Modify: `ragenius_app_skeleton/tests/test_planner_node.py`

- [ ] Ensure planner can activate a logic-only route without requiring workflow-step progression.
- [ ] Preserve executable step activation when the chosen target is a real workflow/module with steps.
- [ ] Add tests that distinguish:
  - logic-only active route
  - executable active route

## Task 7: Fix executed-step UI assumptions

**Files:**
- Modify: frontend runtime/status components as needed
- Add/adjust tests

- [ ] Make the GUI step panel tolerant of logic-only routes.
- [ ] Show no executed steps as valid when the current route has no executable procedure model.
- [ ] Do not suppress executed steps when a real executable route is active.

## Task 8: Regression verification across app families

**Files:**
- Modify tests as needed

- [ ] Verify `與孩子一起成長` compiles under `intent_routed_interaction_logic`.
- [ ] Verify `Bible Tutor` compiles under the correct mode and no longer fails on forced `intent_routed_multi_workflow` requirements.
- [ ] Verify true `single_default_workflow` behavior remains unchanged.
- [ ] Verify true executable multi-workflow apps still fail when executable targets are missing.

## Task 9: Full verification

- [ ] Run:
  - `python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service`
  - `python -m unittest ragenius_app_skeleton.tests.test_llm_runtime_compat`
  - relevant planner/integration/frontend test slices
- [ ] Restart backend.
- [ ] Recompile `與孩子一起成長` and `Bible Tutor`.
- [ ] Inspect latest active/attempt snapshots to confirm:
  - new mode selected appropriately
  - no forced `intent_routed_multi_workflow` validation failure
  - executable targets preserved where explicit
  - logic-only routes no longer treated as invalid

## Acceptance Criteria

- [ ] `與孩子一起成長` recompiles without `intent_routed_multi_workflow` validation errors
- [ ] `Bible Tutor` recompiles successfully under the corrected mode
- [ ] top-level routing policy no longer masquerades as workflow execution
- [ ] executable workflows/modules still validate when explicitly present
- [ ] GUI no longer treats absence of executed steps as failure for logic-only routes
