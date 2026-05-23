# Bundled Execution Unit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic bundled execution mode so generation-oriented procedures can execute several internal instruction steps as one unit while preserving the existing immediate-step checkpoint model.

**Architecture:** Keep workflow and checkpoint-step selection explicit, but extend procedure steps with an execution mode. Interactive steps continue to behave as they do today. Bundled steps become entry points that aggregate resources across multiple internal steps and let the LLM execute the internal sequence as one unit in a single turn.

**Tech Stack:** Python, Pydantic runtime models, planner/retrieval nodes, unittest.

---

## File Map

### Files to modify
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
  - add bundled execution fields to step/session/turn contracts
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
  - infer bundled vs interactive execution mode
  - materialize bundled step metadata
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
  - select bundled entry steps
  - aggregate bundled resources
  - persist bundled execution state
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`
  - consume aggregated bundled requests with provenance
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`
  - parser/runtime-model regressions
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
  - bundled step activation/progression regressions
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_retrieve_node.py`
  - bundled resource aggregation and provenance regressions
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
  - end-to-end runtime assertions for Church Ministry/GPT App Design behavior

### Files to inspect while implementing
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\docs\superpowers\specs\2026-05-07-bundled-execution-unit-design.md`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\docs\superpowers\specs\2026-05-06-procedure-scope-support-design.md`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\docs\superpowers\specs\2026-05-06-hierarchical-instruction-parser-and-planner-refactor-design.md`

---

### Task 1: Extend Runtime Models For Bundled Execution

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`

- [ ] **Step 1: Write failing model/serialization tests**

Add tests that assert:
- `ProcedureStepDefinition` accepts `execution_mode`
- bundled step definitions can carry `bundled_step_ids`, `bundled_resource_refs`, `stop_after_completion`
- turn/session execution state can serialize `active_execution_mode`, `active_bundled_step_ids`, `bundled_entry_step_id`

Run:
`python -m unittest ragenius_app_skeleton.tests.test_load_template_registry.LoadTemplateRegistryTests -v`
Expected: fail on missing model fields

- [ ] **Step 2: Add minimal runtime-model fields**

Add to `ProcedureStepDefinition`:
- `execution_mode: Literal["interactive", "bundled"] = "interactive"`
- `bundled_step_ids: List[str] = Field(default_factory=list)`
- `bundled_resource_refs: List[str] = Field(default_factory=list)`
- `stop_after_completion: bool = False`

Add session/turn execution fields where needed:
- `active_execution_mode`
- `active_bundled_step_ids`
- `bundled_execution_completed`
- `bundled_entry_step_id`

- [ ] **Step 3: Re-run model tests**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_load_template_registry.LoadTemplateRegistryTests -v`
Expected: model tests pass

---

### Task 2: Parse Bundled Execution Steps Conservatively

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`

- [ ] **Step 1: Write failing parser regressions**

Add regressions that assert:
- Church Ministry maps:
  - Step 0 / Step 1 -> `interactive`
  - Step 2 -> `bundled`
  - bundled members include Step 2, 3, 4, 5
  - bundled resource refs include routing/output resources
- GPT Application Design-like fixture can mark a generation/configuration phase as bundled
- Bible Tutor remains interactive

Run:
`python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v`
Expected: fail on missing bundled metadata

- [ ] **Step 2: Implement bundled-step inference**

In `load_template_registry.py`:
- add a conservative classifier for procedure-step execution mode
- default uncertain cases to `interactive`
- mark explicit internal generation/routing/output/validation chains as `bundled`
- materialize `bundled_step_ids` and `bundled_resource_refs`

- [ ] **Step 3: Re-run parser tests**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v`
Expected: parser regressions pass

---

### Task 3: Planner Support For Bundled Entry Steps

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`

- [ ] **Step 1: Write failing planner tests**

Add regressions that assert:
- Church Ministry clarification turns still select interactive clarification step
- once `theme + audience + goal` threshold is satisfied, planner selects bundled entry step instead of stopping at workflow scope
- bundled entry step sets:
  - `active_step_scope`
  - `active_execution_mode = bundled`
  - `active_bundled_step_ids`
- GPT Application Design bundled phase can select its bundled entry step

Run:
`python -m unittest ragenius_app_skeleton.tests.test_planner_node -v`
Expected: fail on missing bundled planner behavior

- [ ] **Step 2: Implement bundled planner behavior**

In `planner.py`:
- when selected step has `execution_mode = bundled`
  - persist bundled execution fields
  - aggregate bundled resources into one execution unit
  - avoid substep-by-substep progression inside the turn
- preserve current behavior for `interactive` steps

- [ ] **Step 3: Re-run planner tests**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_planner_node -v`
Expected: bundled planner regressions pass

---

### Task 4: Retrieval Support For Bundled Resource Aggregation

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_retrieve_node.py`

- [ ] **Step 1: Write failing retrieval regressions**

Add tests that assert bundled execution requests:
- merge resources across bundled steps
- preserve bundled provenance in prepared inputs/debug trace
- avoid duplicate loads when bundled member steps share files

Run:
`python -m unittest ragenius_app_skeleton.tests.test_retrieve_node -v`
Expected: fail on missing bundled aggregation/provenance

- [ ] **Step 2: Implement minimal retrieval support**

In `retrieve.py`:
- consume the planner’s bundled aggregated requests
- keep provenance fields at bundled-entry-step level and optionally member-step level
- preserve existing request-driven behavior

- [ ] **Step 3: Re-run retrieval tests**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_retrieve_node -v`
Expected: retrieval regressions pass

---

### Task 5: End-To-End Runtime Contract Verification

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- Optionally modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`

- [ ] **Step 1: Write failing end-to-end regressions**

Add end-to-end assertions for Church Ministry:
- starter -> interactive clarification checkpoint
- audience reply -> still clarification checkpoint
- theme/goal-complete turn -> bundled generation entry step
- `.md` routing/output resources loaded in one shot
- prompt generated in the same turn

Add at least one GPT Application Design bundled-phase regression.

Run:
`python -m unittest ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v`
Expected: fail before integration complete

- [ ] **Step 2: Adjust any missing glue code**

Only if needed:
- ensure runtime summaries expose bundled execution fields
- ensure session execution state persists the bundled context cleanly

- [ ] **Step 3: Re-run end-to-end tests**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v`
Expected: end-to-end regressions pass

---

### Task 6: Full Verification

**Files:**
- No planned production-code changes
- Run verification against touched suites

- [ ] **Step 1: Run focused suites**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_load_template_registry ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts -v`
Expected: all pass

- [ ] **Step 2: Run full backend discovery**

Run:
`python -m unittest discover -s ragenius_app_skeleton/tests -p 'test_*.py' -v`
Expected: all pass

- [ ] **Step 3: Validate live Church Ministry case manually**

Manual sequence:
1. start new Church Ministry session
2. send starter question
3. answer audience
4. answer theme/passage

Expected:
- first turns show workflow + clarification checkpoint
- final turn shows bundled generation execution
- relevant `.md` resources load together
- optimized prompt is generated in the same turn

---

## Notes

- Keep this change generic. Do not hardcode Church Ministry-only planner behavior if the same bundled pattern can be inferred structurally.
- Keep bundled execution conservative. If the parser is not confident, default to `interactive`.
- Do not remove immediate-step support. Bundled execution extends it.
