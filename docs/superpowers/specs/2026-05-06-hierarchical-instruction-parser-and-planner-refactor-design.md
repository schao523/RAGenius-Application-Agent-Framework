# Hierarchical Instruction Parser And Planner Refactor Design

**Date:** 2026-05-06  
**Status:** Approved-for-planning design spec  
**Scope:** `ragenius_app_skeleton` parser/planner contract only. No retrieval-core redesign.

## Goal

Refactor instruction parsing and planning so application instructions are interpreted as a hierarchical service contract rather than a flat collection of keyword blocks.

The new contract must correctly support:
- one default primary workflow per app
- explicit entry modes that route into workflows
- support modules that assist an active workflow or step
- follow-up modules that operate on prior outputs or required inputs
- supplementary workflows that provide a secondary service path inside the same app
- global execution policies that constrain interaction pacing and safety
- step-level resource binding for both markdown and retrieval-backed resources

This refactor is specifically intended to close the current gaps exposed by:
- Church Ministry Prompt Designer starter turns not activating any procedure/module
- incomplete step extraction from heading-style instruction sections
- inability to distinguish primary workflows from support/follow-up/supplementary blocks
- over-reliance on explicit trigger phrases for cold-start workflow activation

## Non-goals

This refactor must not:
- redesign instruction storage away from file-backed markdown
- rewrite core retrieval/indexing logic in `rag_subsystem`
- collapse Builder and App responsibilities
- redesign chat UX or Builder authoring UI in this iteration
- implement arbitrary multi-module dependency graphs beyond the existing single primary support module per active step

## Existing Problems

### 1. Flat parsing loses structure

The current parser scans `##` sections and ad hoc step patterns, but does not build a canonical heading tree. That causes parent/child ownership to be inferred inconsistently, especially when instructions use:
- `##` top-level sections
- `### Step N:` child steps
- nested trigger/rule/resource sections

### 2. Default workflows do not cold-start

If a workflow/procedure has no explicit trigger phrases, planner currently cannot select it on a new session unless some other selection path happens first. Church Ministry Prompt Designer demonstrates this failure.

### 3. Service block roles are conflated

The runtime does not distinguish clearly enough among:
- main service workflows
- support modules
- follow-up modules
- secondary standalone workflows
- cross-cutting policies

This causes selection and resource-binding logic to behave too uniformly.

### 4. Step extraction is too narrow

The current step parser is strongest on numbered-list items. Real instruction files often encode steps as heading sections like:
- `### Step 1 ...`
- `#### Step 2 ...`

Those must be parsed as canonical procedure steps.

### 5. Resource binding activates too late

Normal phase/module bindings often require a selected scope to exist before they can match. That is correct for support bindings, but wrong for default workflow entry on starter turns and first-session turns.

## Instruction Structure Rules

These rules are now part of the parser contract.

### 1. Heading markers are structural only

`#`, `##`, `###`, etc. are never part of a workflow name, module name, step name, or section title.

Examples:
- `## Interaction Logic & Execution Flow` -> title is `Interaction Logic & Execution Flow`
- `### Step 3：Routing` -> title is `Step 3：Routing`

### 2. Each application file has one top-level heading depth

For a single instruction file, top-level sections may start with either:
- `#`
- or `##`

but not both.

The parser must infer the top-level heading depth from the file and normalize all sections relative to it.

### 3. Parent-child ownership is hierarchical

Given top-level `#`:
- `##` belongs to the nearest preceding `#`
- `###` belongs to the nearest preceding `##`

Given top-level `##`:
- `###` belongs to the nearest preceding `##`
- `####` belongs to the nearest preceding `###`

A child remains within that parent until another heading of the same or higher level closes the scope.

### 4. Procedural steps may be expressed as headings or numbered lines

The parser must recognize both:
- heading-form steps such as `### Step 2：Routing`
- numbered/body-form steps such as `1. Analyze task`

Heading-form steps take precedence when both are present in the same procedure section.

## New Canonical Service-Block Model

The parser must classify top-level executable sections into explicit service-block types.

### Service block types

1. `primary_workflow`
- the app's main service path
- used by starter turns and the first user query in a new session unless a more specific explicit trigger wins

2. `entry_mode`
- a mode that classifies initial user intent and may route into a workflow
- examples: Bible Study / Theology Discussion / Life Application

3. `support_module`
- assists the currently active primary workflow or active step
- does not replace the primary scope
- may load resources, add analysis, or shape generation

4. `followup_module`
- operates on prior outputs, required artifacts, or later-stage inputs
- may require collected inputs before it can run
- often triggered after the primary workflow produces a draft/config/output

5. `supplementary_workflow`
- a secondary but substantial service path within the same app
- not the default main workflow
- may own its own procedure and state progression when explicitly triggered
- examples: Bible-study workflow inside a parenting app

6. `global_policy`
- cross-cutting execution rules
- examples: ask/wait/progress pacing, human-in-the-loop, safety escalation, output contract rules
- not independently selected as a user-facing scope

7. `resource_catalog`
- structured declaration of resources
- not executable by itself

8. `output_contract`
- output-format and quality constraints
- contributes policies and support resources, not service selection by itself

## Default Workflow Semantics

### Rule

If a workflow/procedure exists without explicit trigger conditions and it represents the application's main service, it must be treated as the default primary workflow.

### Precedence on a new session

For a starter turn or the first user query of a new chat session:

1. explicit trigger match for another service block wins
2. otherwise choose the default `primary_workflow`

### Scope persistence

When the default workflow is selected:
- it becomes `primary_scope`
- its active step becomes `active_step_scope`
- any support module activated by the step becomes `primary_support_module_scope`

## Explicit Trigger Semantics

Triggers may be declared by:
- starter question wording
- explicit `觸發` / `trigger` sections
- module `啟動條件` / `Trigger Conditions`
- command-like markers such as `/export_package`
- semantic trigger phrases embedded in a block

The parser must normalize triggers into structured conditions instead of leaving them as loose keywords only.

### Trigger categories

1. `starter_trigger`
- derived from starter questions or starter-specific wording

2. `query_phrase_trigger`
- explicit user-language trigger phrases

3. `command_trigger`
- slash-style or explicit command markers

4. `artifact_gate_trigger`
- block requires uploaded artifact or prior output before progression

5. `semantic_default_trigger`
- only for the default primary workflow when no more specific trigger wins

## New Parser Output Contract

The parser must produce a hierarchical runtime contract that sits above the existing resource-binding layer.

### A. `instruction_heading_tree`

A normalized tree representation of the instruction file.

Each node must include:
- `node_id`
- `level`
- `title`
- `body_text`
- `children`
- `source_span` if cheaply available
- `normalized_title`

Purpose:
- all later extraction is derived from this tree
- avoid repeated flat scans over markdown

### B. `instruction_service_blocks`

Canonical list of parsed service blocks.

Each block must include at minimum:
- `block_id`
- `block_type` (`primary_workflow`, `entry_mode`, `support_module`, `followup_module`, `supplementary_workflow`, `global_policy`, `resource_catalog`, `output_contract`)
- `title`
- `body_text`
- `parent_block_id`
- `trigger_conditions`
- `required_inputs`
- `resource_refs`
- `policy_refs`
- `is_default`

### C. `instruction_procedures`

Executable procedures derived from service blocks of type:
- `primary_workflow`
- `supplementary_workflow`
- optionally `followup_module` when it owns a real procedure

Each procedure must include:
- `procedure_id`
- `service_block_id`
- `title`
- `procedure_kind` (`primary`, `supplementary`, `followup`)
- `is_default`
- `entry_mode_ids`
- `trigger_conditions`
- `step_sequence`
- `output_targets`

### D. `procedure_steps`

Canonical step objects.

Each step must include:
- `step_id`
- `procedure_id`
- `order`
- `title`
- `body_text`
- `step_kind` (`clarification`, `analysis`, `routing`, `generation`, `validation`, `interaction_loop`, etc. when inferable)
- `wait_for_user`
- `advance_conditions`
- `resource_refs`
- `primary_support_module_id` (optional)
- `step_output_role` (optional)

### E. `support_modules`

Each support module must include:
- `module_id`
- `title`
- `purpose`
- `trigger_conditions`
- `required_inputs`
- `resource_refs`
- `can_be_suggested_by_assistant`

### F. `followup_modules`

Each follow-up module must include:
- `module_id`
- `title`
- `purpose`
- `trigger_conditions`
- `required_inputs`
- `depends_on_output_roles`
- `resource_refs`
- `can_be_suggested_by_assistant`

### G. `global_policies`

Each policy must include:
- `policy_id`
- `title`
- `policy_type`
- `rules`
- `applies_to`

Examples of `policy_type`:
- `interaction_pacing`
- `human_in_the_loop`
- `safety_escalation`
- `output_contract`
- `clarification_policy`

## Planner Refactor Contract

The planner must consume the new parser outputs in a layered way.

### 1. Session entry resolution

On a new session or starter turn:

1. detect explicit command triggers
2. detect explicit follow-up module triggers that do not require prior outputs
3. detect explicit support-module triggers only if they are designed as direct entry modules
4. detect explicit supplementary workflow triggers
5. detect explicit entry-mode triggers
6. detect explicit primary-workflow triggers
7. otherwise choose the default primary workflow

This is the main behavioral change required to fix Church Ministry.

### 2. Entry mode resolution

If an entry mode is selected:
- it may route into a procedure
- or it may define a behavior-only path

Example:
- Bible Study mode routes into the ten-step study procedure
- General Question mode routes into a non-procedural answering path

### 3. Procedure selection

If a procedure is selected:
- it becomes `primary_scope` if it is a primary workflow
- it becomes an alternate top-level scope if it is a supplementary workflow explicitly triggered for the turn/session

### 4. Step selection

The planner must select the active step based on:
- starter/new-session entry point
- required clarification inputs
- explicit step-advance continuation
- prior session state
- step-specific trigger conditions if defined

Step selection must work for heading-style steps.

### 5. Support module activation

A step may activate at most one primary support module.

Activation sources:
- step-declared support module
- explicit user trigger that enriches the active procedure
- assistant suggestion when allowed by the module contract

Support modules remain subordinate:
- `primary_scope` does not change
- support module is stored as `primary_support_module_scope`

### 6. Follow-up module activation

A follow-up module may activate when:
- its trigger conditions match
- and required inputs or output dependencies are satisfied

A follow-up module may:
- temporarily take over the current turn's main task
- but must preserve the underlying app/service continuity

For now, a follow-up module may become the turn's active executable block without rewriting the app-wide default workflow definition.

### 7. Supplementary workflow activation

A supplementary workflow is a secondary full service path.

When explicitly triggered:
- it may become the active top-level service for the turn/session
- it should not be squeezed into `primary_support_module_scope`
- it should own its own procedure steps and pacing rules

Example:
- `與孩子一起成長` primary service is parenting coaching
- Bible-study ten-step flow is a `supplementary_workflow`

## Resource-Binding Semantics Under The New Model

The existing resource-binding layer remains useful, but must be attached to the new service-block model.

### Procedure-step resource binding

Step resources are loaded when the step becomes active.

### Support-module resource binding

Support-module resources are merged into the active turn's requests with provenance:
- `source_layer = support_module`
- `support_module_id = ...`

### Follow-up-module resource binding

Follow-up-module resources are loaded only after required inputs/output dependencies are satisfied.

### Supplementary-workflow resource binding

Resources for a supplementary workflow are loaded under that workflow's active step, not under the default primary workflow.

## Updated Runtime Semantics

### Existing layered fields remain
- `primary_scope`
- `active_step_scope`
- `primary_support_module_scope`

### New required runtime distinction

The runtime must also distinguish whether the active service block for the turn is:
- the default primary workflow
- a follow-up module procedure
- a supplementary workflow

This can be represented by adding to `TurnExecutionPlan` and `SessionExecutionState`:
- `active_service_block_type`
- `active_service_block_id`
- `active_service_block_title`

This prevents `supplementary_workflow` from being incorrectly modeled as mere support.

## Classification Rules By Example

### Bible Tutor
- `Bible Study` = entry mode
- ten-step inductive study = primary workflow
- theology discussion / life application / general question = entry modes or alternate primary service behaviors
- Exegesis / Lexical modules = support modules
- interaction pacing = global policy

### GPT Application Design Assistant
- three-phase design process = primary workflow
- Use Case / Style Tone / Interaction Mode / engine modules = support modules
- Config Support / Interaction Logic Support / Testing & Optimization = follow-up modules
- Human-in-the-Loop = global policy

### Church Ministry Prompt Designer
- `Interaction Logic & Execution Flow` = default primary workflow
- `Knowledge Modules` and `Instruction Modules` = support modules
- `Optimization Module` and `Tool Selection Module` = follow-up modules
- output/quality/clarification rules = global policies and output contract

### Grow With Children
- parenting coaching with 3×1 / step-by-step / deep analysis = default primary workflow with internal branch logic
- Bible-study ten-step flow = supplementary workflow
- safety/danger handling = global policy

## Files Expected To Change In The Refactor

Primary parser/planner files:
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\load_template_registry.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\planner.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\runtime_models.py`

Supporting runtime/output files:
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\retrieve.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\workflows\nodes\persist_run.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_service.py`

Tests to add/update:
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_load_template_registry.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_planner_node.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_retrieve_node.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_persist_run_node.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_chat_pipeline_runtime_contracts.py`
- `C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py`

## Required Test Coverage

### Parser tests

Must prove:
- top-level heading depth inference works for `#` and `##`
- heading markers are excluded from names
- heading tree ownership is correct
- `### Step N:` sections become canonical procedure steps
- default primary workflow is inferred when no explicit trigger exists
- service-block classification works for all four analyzed instruction styles
- supplementary workflow classification is distinct from support-module classification

### Planner tests

Must prove:
- new-session starter turn falls into default primary workflow when no explicit module trigger wins
- Church Ministry starter turn activates `Interaction Logic & Execution Flow`
- Bible Tutor mode trigger routes to Bible-study workflow
- Grow With Children parenting questions stay in parenting primary workflow
- Grow With Children scripture-study request activates supplementary workflow instead
- follow-up module activation requires prior output/input where specified
- support module activation does not replace `primary_scope`
- supplementary workflow activation does not get stored as `primary_support_module_scope`

### Runtime/persistence tests

Must prove:
- resource requests preserve provenance under the new service-block model
- summaries expose the active service-block type cleanly
- old consumers of `primary_scope` / `active_step_scope` remain backward compatible where intended

## Migration Strategy

### Phase 1
- add hierarchical parser outputs alongside current flat outputs
- do not remove old fields yet

### Phase 2
- planner prefers new service-block outputs
- legacy flat fields remain populated for compatibility

### Phase 3
- retrieval/persistence consume richer service-block provenance

### Phase 4
- once test coverage is stable, reduce dependence on legacy flat block inference

## Success Criteria

This refactor is complete when all of the following are true:

1. Church Ministry starter turns activate the default primary workflow and load step/module resources when appropriate.
2. Bible Tutor correctly distinguishes primary study workflow from support modules.
3. GPT Application Design Assistant correctly distinguishes support modules from follow-up modules.
4. Grow With Children correctly keeps parenting coaching as the default primary workflow while allowing Bible study as a supplementary workflow.
5. The parser no longer depends on flat section scans as its primary structural model.
6. Planner cold-start behavior no longer requires explicit workflow triggers when a default workflow is clearly present.

## Recommended Next Step

Write the implementation plan against this spec before touching code. The plan should decompose work into:
1. heading-tree parser
2. service-block classification
3. default workflow inference
4. planner session-entry refactor
5. runtime/persistence compatibility
6. regression coverage
