# Generic Phase/Resource Binding Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the planner/runtime contract so instruction-driven apps can bind resources generically across phases, commands, dependency groups, and artifact-gated workflows without app-specific logic.

**Architecture:** Add a planner-native binding schema in `runtime_models.py`, populate it from parsed instruction blocks and resources during registry loading, select active bindings in `planner.py`, and let `retrieve.py` resolve resource requests from those bindings. Treat shared bundle artifacts, command-triggered flows, grouped dependencies, and gating preconditions as first-class runtime concepts rather than hidden instruction text.

**Tech Stack:** Python, Pydantic, unittest, existing `ragenius_app_skeleton` workflow nodes and runtime models.

---

## Proposed Schema

### New enum-like literals

Add to [runtime_models.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py):

- `BindingTriggerType`
  - `phase`
  - `module`
  - `workflow_step`
  - `command_trigger`
  - `artifact_gate`
  - `starter`
- `BindingMode`
  - `none`
  - `single_required`
  - `one_of`
  - `multi_required`
  - `ordered_multi`
- `ResourceKind`
  - `instruction_resource`
  - `template_resource`
  - `rubric_resource`
  - `schema_anchor`
  - `output_format_guide`
  - `resource_index`
  - `artifact_template`
- `ArtifactContractMode`
  - `none`
  - `produces_artifact`
  - `requires_artifact`
  - `updates_artifact`

### New models

Add to [runtime_models.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py):

```python
BindingTriggerType = Literal[
    "phase",
    "module",
    "workflow_step",
    "command_trigger",
    "artifact_gate",
    "starter",
]

BindingMode = Literal[
    "none",
    "single_required",
    "one_of",
    "multi_required",
    "ordered_multi",
]

ResourceKind = Literal[
    "instruction_resource",
    "template_resource",
    "rubric_resource",
    "schema_anchor",
    "output_format_guide",
    "resource_index",
    "artifact_template",
]

ArtifactContractMode = Literal[
    "none",
    "produces_artifact",
    "requires_artifact",
    "updates_artifact",
]

class DependencyGroup(BaseModel):
    group_id: str
    title: str
    resource_ids: List[str] = Field(default_factory=list)
    filenames: List[str] = Field(default_factory=list)
    ordered: bool = False
    notes: Optional[str] = None

class ArtifactContract(BaseModel):
    mode: ArtifactContractMode = "none"
    artifact_role: Optional[str] = None
    filename_patterns: List[str] = Field(default_factory=list)
    schema_anchor_filename: Optional[str] = None
    required_for_progression: bool = False
    missing_artifact_prompt: Optional[str] = None

class PhaseResourceBinding(BaseModel):
    binding_id: str
    title: str
    trigger_type: BindingTriggerType
    binding_mode: BindingMode = "none"
    trigger_signals: List[str] = Field(default_factory=list)
    scope_id: Optional[str] = None
    step_order: Optional[int] = None
    resource_ids: List[str] = Field(default_factory=list)
    filenames: List[str] = Field(default_factory=list)
    resource_kinds: List[ResourceKind] = Field(default_factory=list)
    dependency_groups: List[str] = Field(default_factory=list)
    artifact_contract: ArtifactContract = Field(default_factory=ArtifactContract)
    objective: Optional[str] = None
    activation_reason: Optional[str] = None
    priority: int = 100
```

### Minimal changes to existing models

Extend existing models in [runtime_models.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py):

- `InstructionRuntimeModel`
  - add `dependency_groups: List[DependencyGroup]`
  - add `phase_resource_bindings: List[PhaseResourceBinding]`
- `InstructionBlock`
  - add `declared_binding_id: Optional[str]`
  - add `command_triggers: List[str]`
  - add `artifact_role: Optional[str]`
- `ResourceRequest`
  - add `binding_id: Optional[str]`
  - add `resource_kind: Optional[ResourceKind]`
  - add `dependency_group_id: Optional[str]`
  - add `artifact_role: Optional[str]`
  - add `required_for_progression: bool = False`
- `SessionExecutionState`
  - add `active_binding_ids: List[str]`
  - add `active_dependency_group_ids: List[str]`
  - add `active_artifact_roles: List[str]`
  - add `artifact_gate_status: Dict[str, Any]`

### Behavioral intent of the schema

- `PhaseResourceBinding` is the planner/runtime unit of resource activation.
- `DependencyGroup` lets a phase bind named families instead of repeating flat filename lists.
- `ArtifactContract` distinguishes normal retrieval from shared artifact gating and schema anchoring.
- `ResourceRequest` remains the retrieval-facing unit, derived from active bindings.

---

## File Map

### Core runtime models
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`

### Instruction parsing / registry building
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`

### Planning / binding selection
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`

### Retrieval / artifact gating
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`

### Execution / state persistence
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\execute_turn_plan.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`

### Tests
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_retrieve_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- Create if needed: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\fixtures\vibe_story_director_runtime_model.json`

---

### Task 1: Add the new binding schema to runtime models

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`

- [ ] **Step 1: Write the failing tests for new model fields**

Add tests that instantiate `InstructionRuntimeModel`, `PhaseResourceBinding`, `DependencyGroup`, and `ArtifactContract` with:
- a `one_of` binding
- an `ordered_multi` binding
- an artifact-gated binding

Expected assertions:
- Pydantic accepts valid enum values
- default lists are empty
- nested models serialize cleanly with `model_dump()` / plain dict conversion

- [ ] **Step 2: Run the focused test file to verify failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v`
Expected: FAIL because the new classes/fields do not exist.

- [ ] **Step 3: Add the new literals and models to runtime_models.py**

Implement the schema from the “Proposed Schema” section above.

- [ ] **Step 4: Extend existing models with the new fields**

Update:
- `InstructionRuntimeModel`
- `InstructionBlock`
- `ResourceRequest`
- `SessionExecutionState`

Keep defaults backward-compatible so old fixtures still load.

- [ ] **Step 5: Re-run the focused tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v`
Expected: PASS for model-shape assertions, or advance to the next missing-parser failure.

### Task 2: Parse generic bindings from instruction structures

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`

- [ ] **Step 1: Write failing parser tests for binding extraction**

Add tests that feed representative instruction text fragments covering:
- a starter/phase block with `.md` references
- a command like `/generate_video_prompt`
- a block that says “if upload missing, prompt user to upload Bundle.md”
- a block with multiple support references

Assert that the resulting runtime model includes:
- `phase_resource_bindings`
- `dependency_groups`
- `artifact_contract`

- [ ] **Step 2: Run parser tests to confirm failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v`
Expected: FAIL because parser does not emit bindings yet.

- [ ] **Step 3: Implement generic extraction helpers**

In `load_template_registry.py`, add helpers that derive bindings from parsed instruction blocks without app-name rules:
- detect command triggers from `/command` patterns
- detect filename references ending in `.md`, `.docx`, `.zip` where relevant
- detect artifact-gate language like “upload”, “if missing”, “before executing”, “load bundle”
- group co-mentioned resources into `DependencyGroup` when a block references 2+ support resources

- [ ] **Step 4: Map parsed blocks to `PhaseResourceBinding`**

Derive generic bindings from:
- starter blocks
- phase blocks
- support module blocks
- output/export blocks
- command blocks

Selection rules:
- one filename -> `single_required`
- explicit alternatives -> `one_of`
- 2+ co-required resources -> `multi_required`
- ordered step references -> `ordered_multi`
- no files but artifact gate -> `none` + `artifact_contract`

- [ ] **Step 5: Re-run parser tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_load_template_registry -v`
Expected: PASS.

### Task 3: Select active bindings during planning

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`

- [ ] **Step 1: Write failing planner tests for binding activation**

Add tests covering generic cases:
- generation request that should activate a phase binding with `multi_required` resources
- command-trigger turn like `/generate_video_prompt`
- session follow-up that requires an uploaded artifact gate
- phase turn that should activate a dependency group rather than a single resource

Assert:
- `turn_execution_plan.resource_requests` contain binding-linked requests
- `SessionExecutionState.active_binding_ids` is updated
- `active_dependency_group_ids` / `active_artifact_roles` are updated

- [ ] **Step 2: Run the planner tests to confirm failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node -v`
Expected: FAIL because planner does not reason over bindings yet.

- [ ] **Step 3: Implement binding selection helpers**

In `planner.py`, add generic helpers such as:
- `_match_phase_resource_bindings(...)`
- `_match_command_bindings(...)`
- `_match_artifact_gate_bindings(...)`
- `_expand_dependency_group_requests(...)`

Selection must use:
- current turn intent
- active phase/mode/workflow context
- explicit command markers
- current session uploads / prior outputs
- activation signals and trigger phrases from bindings

- [ ] **Step 4: Derive `ResourceRequest`s from active bindings**

For each selected binding:
- set `binding_id`
- set `resource_kind`
- set `dependency_group_id` when applicable
- set `artifact_role` / `required_for_progression` when applicable
- preserve `filename`, `purpose`, `objective`, `stage_label`, `request_reason`

- [ ] **Step 5: Update session state hydration**

Populate:
- `active_binding_ids`
- `active_dependency_group_ids`
- `active_artifact_roles`
- `artifact_gate_status`

- [ ] **Step 6: Re-run planner tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_planner_node -v`
Expected: PASS.

### Task 4: Enforce artifact gating and group-based retrieval

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_retrieve_node.py`

- [ ] **Step 1: Write failing retrieval tests for binding-driven loading**

Add tests for:
- `one_of` binding selects a single matching file
- `multi_required` binding loads all referenced files
- artifact gate marks retrieval as blocked when required upload is absent
- command-trigger binding loads export-template resources

Assert:
- `instruction_resource_context` / `prepared_inputs` reflect the active binding
- retrieval debug trace captures blocked artifact gate reason

- [ ] **Step 2: Run retrieval tests to confirm failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_retrieve_node -v`
Expected: FAIL before implementation.

- [ ] **Step 3: Implement binding-aware request resolution**

In `retrieve.py`:
- respect `binding_id`, `dependency_group_id`, and `resource_kind`
- resolve `one_of` by choosing the best matching available document/resource
- resolve `multi_required` and `ordered_multi` by loading all required requests
- short-circuit retrieval when `required_for_progression` artifact is missing

- [ ] **Step 4: Record artifact-gate status in debug trace**

Add trace fields such as:
- `retrieval_bypassed`
- `retrieval_bypass_reason`
- `artifact_gate_status`
- `active_binding_ids`

- [ ] **Step 5: Re-run retrieval tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_retrieve_node -v`
Expected: PASS.

### Task 5: Carry binding/artifact context through execution and summaries

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\execute_turn_plan.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- Test: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_persist_run_node.py`

- [ ] **Step 1: Write failing pipeline tests for binding metadata visibility**

Add tests asserting summaries expose:
- `active_binding_ids`
- `active_dependency_group_ids`
- `artifact_gate_status`
- selected resource filenames/kinds

- [ ] **Step 2: Run focused pipeline tests to confirm failure**

Run: `python -m unittest ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts ragenius_app_skeleton.tests.test_persist_run_node -v`
Expected: FAIL because summary fields do not exist yet.

- [ ] **Step 3: Persist binding/artifact metadata**

In `persist_run.py` and `chat_service.py`, add summary exposure for:
- active bindings
- dependency groups
- artifact gate decisions
- schema-anchor resources

Keep existing summary contract backward-compatible.

- [ ] **Step 4: Keep execution state consistent**

In `execute_turn_plan.py`, ensure generated/required artifact roles can update `SessionExecutionState.artifact_gate_status` and `assembly_state` without inventing app-specific logic.

- [ ] **Step 5: Re-run focused pipeline tests**

Run: `python -m unittest ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts ragenius_app_skeleton.tests.test_persist_run_node -v`
Expected: PASS.

### Task 6: Prove the contract across three instruction styles

**Files:**
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- Modify: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- Create if helpful: `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\fixtures\vibe_story_director_runtime_model.json`

- [ ] **Step 1: Add Church Ministry Prompt Designer generic binding coverage**

Cover:
- `one_of` route (`template_library.md` vs `dynamic_prompt_optimizer.md`)
- `multi_required` output-rule bundle
- tool-selection mapping pair

- [ ] **Step 2: Add GPT Application Design Assistant coverage**

Cover:
- single-resource phase binding
- multi-resource interaction/configuration phase binding
- support module group activation

- [ ] **Step 3: Add Vibe Story Director coverage**

Cover:
- starter-triggered binding
- command-triggered binding (`/generate_video_prompt`)
- artifact-gated starter requiring `Director Bundle.md`
- schema-anchor binding via `Director_Bundle_Spec.md`

- [ ] **Step 4: Run the full regression set**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_load_template_registry ragenius_app_skeleton.tests.test_planner_node ragenius_app_skeleton.tests.test_retrieve_node ragenius_app_skeleton.tests.test_chat_pipeline_runtime_contracts ragenius_app_skeleton.tests.test_persist_run_node -v`

Expected: PASS.

### Task 7: Final verification and cleanup

**Files:**
- Modify only if needed based on failures uncovered by full regression.

- [ ] **Step 1: Run the broader runtime suite**

Run:
`python -m unittest ragenius_app_skeleton.tests.test_builder_chat_integration ragenius_app_skeleton.tests.test_execute_turn_plan_node ragenius_app_skeleton.tests.test_answer_node -v`

Expected: PASS.

- [ ] **Step 2: Inspect for compatibility regressions**

Verify that apps without rich phase/resource structure still produce valid `turn_execution_plan` and empty binding collections by default.

- [ ] **Step 3: Commit**

```bash
git add ragenius_app_skeleton/workflows/runtime_models.py \
        ragenius_app_skeleton/workflows/nodes/load_template_registry.py \
        ragenius_app_skeleton/workflows/nodes/planner.py \
        ragenius_app_skeleton/workflows/nodes/retrieve.py \
        ragenius_app_skeleton/workflows/nodes/execute_turn_plan.py \
        ragenius_app_skeleton/workflows/nodes/persist_run.py \
        ragenius_app_skeleton/backend/app/chat_service.py \
        ragenius_app_skeleton/tests/test_load_template_registry.py \
        ragenius_app_skeleton/tests/test_planner_node.py \
        ragenius_app_skeleton/tests/test_retrieve_node.py \
        ragenius_app_skeleton/tests/test_chat_pipeline_runtime_contracts.py \
        ragenius_app_skeleton/tests/test_persist_run_node.py

git commit -m "feat: add generic phase and artifact resource binding contract"
```

---

## Design notes that should guide implementation

1. Do not hardcode app names, PDF titles, or specific workflow names.
2. Derive bindings from parsed instruction structure and generic signals:
   - explicit filenames
   - command markers
   - phase/module/starter headings
   - artifact-gate language
   - grouped support-resource references
3. Keep `ResourceRequest` as the retrieval-facing unit. Do not bypass it with bespoke retrieval paths.
4. Keep all new fields optional/defaulted so existing runtime records remain readable.
5. Prefer emitting binding metadata even when no resource is loaded; visibility matters for debugging gating failures.

## Spec coverage check

Covered requirements:
- generic phase/resource binding
- artifact anchors / shared bundles
- command-triggered binding
- grouped dependency sets
- artifact-gated progression
- cross-app validation against Church Ministry Prompt Designer, GPT Application Design Assistant, and Vibe Story Director

Known non-goals for this plan:
- frontend redesign
- builder storage redesign
- rag_subsystem retrieval rewrite

## Placeholder scan

No `TODO` / `TBD` placeholders intentionally left in implementation tasks.

## Type consistency check

Primary new runtime names used consistently across tasks:
- `PhaseResourceBinding`
- `DependencyGroup`
- `ArtifactContract`
- `BindingTriggerType`
- `BindingMode`
- `ResourceKind`
- `ArtifactContractMode`

---

Plan complete and saved to `docs/superpowers/plans/2026-05-05-generic-phase-resource-binding-contract.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
