# Mode Inference And Runtime Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `與孩子一起成長` compile reliably as a logic-first app even when the semantic compiler omits `primary_service_mode`, and make Bible Tutor's active hybrid runtime model expose one coherent routing/execution shape for runtime and GUI consumers.

**Architecture:** Keep the semantic compiler prompt unchanged as guidance, then harden the post-LLM compile path in one place: deterministic mode inference and hybrid runtime projection inside `instruction_understanding_service.py`. The fix must preserve existing support-module ids for unaffected apps while normalizing the final runtime-facing structures for Bible Tutor and `與孩子一起成長`.

**Tech Stack:** Python, `unittest`, existing instruction-understanding compiler/validator/runtime projection pipeline in `ragenius_app_skeleton`

---

### Task 1: Lock missing-mode inference and parenting logic-first classification with failing tests

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Add a failing compile-level test for missing `primary_service_mode` on a parenting-shaped semantic result**
- Semantic compiler returns no `primary_service_mode`
- Deterministic contract comes from `self._grow_with_child_markdown()` / `self._grow_with_child_documents()`
- Expected:
  - compile succeeds
  - `hybrid_instruction_runtime_model.primary_service_mode == "intent_routed_interaction_logic"`

- [ ] **Step 2: Add a failing validation-level test for missing `primary_service_mode` inference**
- Use `_validate_semantic_compile_candidate(...)`
- Provide:
  - no `primary_service_mode`
  - interaction-logic blocks with layered routing/orchestration
  - routed workflow/module targets
- Expected:
  - validation succeeds
  - normalized model has `primary_service_mode == "intent_routed_interaction_logic"`

- [ ] **Step 3: Run the two new tests and verify they fail for the right reason**
Run:
```powershell
python -m unittest `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_parenting_shape_infers_interaction_logic_when_mode_missing `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_validate_semantic_compile_candidate_infers_logic_first_mode_when_missing
```

---

### Task 2: Lock Bible Tutor hybrid runtime projection with failing tests

**Files:**
- Modify: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`

- [ ] **Step 1: Add a failing compile-level test that Bible Tutor publishes top-level routing rules in the hybrid runtime model**
- Use `self._bible_tutor_markdown()` / `self._bible_tutor_documents()`
- Semantic compiler returns the current logic-first Bible Tutor shape
- Expected:
  - `hybrid_instruction_runtime_model.routing_rules` is non-empty
  - at least one rule maps Bible-study mode into executable workflow/module targets

- [ ] **Step 2: Add a failing compile-level test that Bible Tutor uses one workflow identity across logic and executable layers**
- Expected:
  - `logic:mode_bible_study.behavior_policy.primary_workflow_id`
  - matches one `instruction_service_blocks[].block_id`
  - and one `instruction_procedures[].service_block_id`

- [ ] **Step 3: Add a failing compile-level test that step resource refs are copied into top-level `procedure_steps`**
- Expected:
  - `step:observation` in top-level `procedure_steps`
  - includes `resource_refs = ["observation_guide.md"]`

- [ ] **Step 4: Run the new Bible Tutor tests and verify they fail before implementation**
Run:
```powershell
python -m unittest `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_bible_tutor_populates_top_level_routing_rules `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_bible_tutor_uses_one_workflow_identity `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_bible_tutor_copies_step_resource_refs
```

---

### Task 3: Implement deterministic mode inference in one normalization path

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

- [ ] **Step 1: Add a helper that infers `primary_service_mode` when missing**
- Inputs:
  - normalized semantic model
  - deterministic contract
- Output:
  - one of:
    - `single_default_workflow`
    - `intent_routed_multi_workflow`
    - `intent_routed_interaction_logic`
    - `None`

- [ ] **Step 2: Prefer logic-first inference when the semantic shape is primarily routing/orchestration**
- Signals:
  - interaction-logic blocks with mode/rule/layer/orchestration content
  - no single default workflow
  - routed subordinate workflow/module targets

- [ ] **Step 3: Apply inference before validation requires the field**
- If semantic result omits `primary_service_mode`, populate it before the `primary_service_mode is required` check

- [ ] **Step 4: Preserve current reclassification path as a second-pass correction only**
- Existing `intent_routed_multi_workflow -> intent_routed_interaction_logic` reclassification stays
- Missing-mode inference becomes the earlier recovery path

---

### Task 4: Normalize Bible Tutor runtime projection for planner/UI consumers

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

- [ ] **Step 1: Project routing rules into top-level `hybrid_instruction_runtime_model.routing_rules`**
- Preserve existing nested logic routing
- Also emit runtime-facing routing rules that the planner/UI can read directly

- [ ] **Step 2: Unify the Bible-study workflow identity across layers**
- Ensure the logic-layer primary workflow id equals the executable service-block/procedure owner id
- Do not keep one logic alias and one executable alias for the same workflow

- [ ] **Step 3: Copy step resource refs into top-level `procedure_steps.resource_refs`**
- For Bible Tutor steps like `step:observation`
- Preserve step-scoped `.md` refs
- Do not widen them back into module-wide bundles

- [ ] **Step 4: Keep support-module ids for other apps unchanged**
- No broad renaming of Church Ministry or GPT Application Design Assistant support-module ids

---

### Task 5: Verify non-regression and summarize live follow-up

**Files:**
- Test: `ragenius_app_skeleton/tests/test_instruction_understanding_service.py`
- Test: `ragenius_app_skeleton/tests/test_planner_node.py`
- Test: `ragenius_app_skeleton/tests/test_llm_runtime_compat.py`

- [ ] **Step 1: Run the targeted new regressions**
```powershell
python -m unittest `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_parenting_shape_infers_interaction_logic_when_mode_missing `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_validate_semantic_compile_candidate_infers_logic_first_mode_when_missing `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_bible_tutor_populates_top_level_routing_rules `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_bible_tutor_uses_one_workflow_identity `
  ragenius_app_skeleton.tests.test_instruction_understanding_service.InstructionUnderstandingServiceTests.test_compile_instruction_understanding_bible_tutor_copies_step_resource_refs
```

- [ ] **Step 2: Run the full instruction-understanding suite**
```powershell
python -m unittest ragenius_app_skeleton.tests.test_instruction_understanding_service
```

- [ ] **Step 3: Run non-regression slices**
```powershell
python -m unittest ragenius_app_skeleton.tests.test_planner_node
python -m unittest ragenius_app_skeleton.tests.test_llm_runtime_compat
```

- [ ] **Step 4: Live follow-up after code is green**
- Restart backend
- Recompile `與孩子一起成長`
- Recompile Bible Tutor
- Verify:
  - `與孩子一起成長` active snapshot uses `intent_routed_interaction_logic`
  - Bible Tutor active snapshot keeps `intent_routed_interaction_logic`
  - Bible Tutor top-level runtime carries routing, executable blocks, procedures, steps, and step resource refs consistently
