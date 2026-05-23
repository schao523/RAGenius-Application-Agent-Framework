# Procedure Scope Support Design

**Goal:** Support two generic trigger paths in the app runner: direct support-module activation from a query, and procedure-driven execution where the procedure remains the primary scope while the active step can load resources and activate at most one primary support module.

**Status:** Approved design direction for planner/runtime contract change. No code changes in this document.

---

## Problem

The current planner/runtime contract is biased toward resource-bearing sections and direct module selection. It does not model procedure-oriented orchestration as a first-class runtime concept.

This causes three concrete gaps:

1. A query that should activate an execution procedure cannot keep that procedure as the durable top-level session scope.
2. A procedure step cannot explicitly declare its own resource needs and a primary support module in a structured, generic way.
3. Debug and persistence layers cannot distinguish between:
   - the primary procedure
   - the active step inside that procedure
   - the support module activated by that step

This is visible in instruction styles like Church Ministry Prompt Designer, where procedural sections such as `Interaction Logic & Execution Flow` express how the app should operate, while sections like `Knowledge Modules` and `Instruction Modules` provide support resources.

---

## Design Principles

1. Preserve orchestration intent
- If the user triggers a procedure, the procedure remains the primary scope for the turn and the session.

2. Separate orchestration from support
- Procedure and step are execution-control concepts.
- Support module and resource bindings are support concepts.
- They must not overwrite each other in runtime state.

3. Keep the contract generic
- No application-specific special casing.
- The same contract must work for:
  - procedure-driven apps
  - direct-module apps
  - mixed apps

4. Keep support-module activation constrained
- A procedure step may activate at most one primary support module.
- This keeps selection deterministic and avoids building a dependency graph engine prematurely.

5. Preserve current retrieval architecture
- Retrieval remains request-driven.
- The planner enriches request provenance, but retrieval should not need to understand app-specific orchestration semantics.

---

## Target Runtime Semantics

### Scenario A: Direct Module Trigger

A user query directly activates a support or instruction module.

Example shape:
- user asks for prompt optimization
- no procedure is selected
- `Optimization Module` is selected directly

Expected runtime semantics:
- primary scope = module
- active step scope = none
- primary support module = none
- resources come from the module directly

### Scenario B: Procedure Trigger

A user query activates an execution procedure.

Example shape:
- user triggers a guided workflow
- procedure selects the current step
- the current step may load resources and may activate one primary support module

Expected runtime semantics:
- primary scope = procedure
- active step scope = current step in procedure
- primary support module = optional, activated by the current step
- resource requests merge:
  - step-declared resources
  - resources from the step-selected support module

---

## Contract Additions

### 1. Scope Layers

The runtime contract should explicitly represent three layers:

1. `primary_scope`
- top-level selected execution unit for the turn
- examples:
  - procedure
  - workflow
  - directly triggered module

2. `active_step_scope`
- current step inside a selected procedure/workflow
- absent when the turn is not procedure-driven

3. `primary_support_module_scope`
- optional support module activated by the active step
- absent when the turn does not activate a support module

This allows the runtime to preserve procedure continuity without losing support context.

### 2. Procedure-Step Activation Contract

A procedure step needs its own activation payload.

New model:
- `ProcedureStepActivation`
  - `step_scope_id`
  - `step_order`
  - `step_title`
  - `resource_ids`
  - `filenames`
  - `dependency_group_ids`
  - `primary_support_module_id`
  - `activation_reason`

Purpose:
- capture what the selected step contributes to execution independently of support modules

### 3. Support Module Activation Contract

At most one primary support module may be activated by a step.

New model:
- `PrimarySupportModuleActivation`
  - `module_id`
  - `title`
  - `resource_ids`
  - `filenames`
  - `activation_reason`
  - `source`
    - `direct_query`
    - `procedure_step`

Purpose:
- distinguish direct module triggers from step-driven module activation while keeping a uniform runtime representation

### 4. Resource Request Provenance

Resource requests need explicit source provenance.

Extend `ResourceRequest` with:
- `source_layer`
  - `procedure_step`
  - `support_module`
  - `direct_query`
- `step_scope_id`
- `support_module_id`

Purpose:
- retrieval can remain generic while debug/persistence layers can explain why a resource was requested

---

## Required Parser Behavior

The instruction parser must be able to extract two different kinds of structures from application instructions:

1. Procedural scopes
- examples:
  - `Interaction Logic & Execution Flow`
  - phase/workflow sections
  - starter procedures

2. Support scopes
- examples:
  - `Knowledge Modules`
  - `Instruction Modules`
  - `Optimization Module`
  - `Tool Selection Module`

The parser must not force one structure to stand in for the other.

### Parser output requirements

The parsed runtime contract must be able to express:
- procedure scope candidates
- step records for procedures
- step-to-resource bindings
- step-to-primary-support-module binding
- direct support-module scope candidates

---

## Planner Behavior Changes

### 1. Pre-routing classification remains unchanged

Existing intent classification still decides whether a turn is:
- generation
- workflow/procedure
- app-scoped question
- out-of-scope

This design changes what happens after a procedure/module path is selected.

### 2. Procedure selection

If a procedure is selected:
- persist it as `primary_scope`
- select the current step
- derive `active_step_scope`
- derive step resource requests
- optionally derive one `primary_support_module_scope`
- merge step + module resource requests into the turn execution plan

### 3. Direct module selection

If no procedure is selected and a module is directly selected:
- persist module as `primary_scope`
- do not populate `active_step_scope`
- do not populate `primary_support_module_scope`
- load module resources directly

### 4. Continuation behavior

For follow-up turns in a procedure-driven session:
- preserve the procedure as the primary scope
- preserve or advance the step as appropriate
- allow the step-selected primary support module to change across turns without replacing the procedure as the primary scope

---

## Retrieval Behavior Changes

Retrieval should continue to operate on `resource_requests`, but with richer provenance.

Retrieval does not need to know:
- which app-specific procedure is active
- which app-specific module title was selected

Retrieval only needs:
- the merged request set
- app-scoped filters
- provenance fields for debugging and persistence

This preserves the repository boundary rule that retrieval logic stays in `rag_subsystem` and generic retrieval orchestration stays in `ragenius_app_skeleton/workflows/nodes/retrieve.py`.

---

## Persistence and Inspector Behavior

Persisted turn summaries and UI inspector views should expose:
- `primary_scope`
- `active_step_scope`
- `primary_support_module_scope`
- resource request provenance summary

This is required because a single string like `selected_instruction_block` is not enough once procedure and support activation are distinct layers.

---

## Backward Compatibility

The new contract should be additive first.

Requirements:
- existing direct module/resource flows must continue to work
- existing tests for binding/resource selection should continue to pass
- legacy fields like:
  - `selected_instruction_block`
  - `active_binding_ids`
  - `active_workflow`
  - `active_step_order`
  may remain during migration
- newer layered fields become the authoritative contract for future work

---

## Example: Church Ministry Prompt Designer

For a procedure-oriented turn, the desired shape is:

- `primary_scope`
  - `Interaction Logic & Execution Flow`
- `active_step_scope`
  - e.g. `Step 3: Routing`
- `primary_support_module_scope`
  - `Knowledge Modules` or `Instruction Modules`

Resources then merge from:
- the step itself
- the selected support module

This prevents `Knowledge Modules` from replacing the procedure as the apparent top-level scope.

---

## Non-Goals

This design does not attempt to support:
- multiple primary support modules per step
- arbitrary recursive module activation
- graph-based dependency execution
- a full workflow engine rewrite

Those are intentionally excluded to keep this change bounded and generic.

---

## Recommended Migration Strategy

1. Add the new runtime models and summary fields.
2. Extend the parser to extract procedure scopes and step/module activation links.
3. Update planner selection to populate layered scopes.
4. Update retrieval to consume enriched request provenance.
5. Update persistence and inspector output.
6. Add regression coverage across:
   - Church Ministry Prompt Designer
   - GPT Application Design Assistant
   - Vibe Story Director

---

## Decision

Approved direction:
- procedure remains the primary scope
- step is explicit runtime state
- at most one primary support module can be activated by a step
- resources merge from step + support module with provenance
