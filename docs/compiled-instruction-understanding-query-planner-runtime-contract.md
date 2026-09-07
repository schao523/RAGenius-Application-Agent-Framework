# Compiled Instruction Understanding and Query Planner Runtime Contract

**Status:** Normative

**Date:** 2026-09-06

**Scope:** `ragenius_app_skeleton` normal user-query compilation, planning, workflow-state persistence, resource selection, and GUI projection.

## 1. Purpose

This contract defines the boundary between Builder-authored application instructions and the active `ragenius_app_skeleton` runtime. It consolidates the runtime invariants established by compiler, planner, persistence, and resource-selection fixes completed through 2026-09-05.

Historical dated designs and implementation plans remain useful records. When they conflict with this document, this contract is authoritative.

## 2. System Boundaries

- `ragenius_app_skeleton` is the active end-user runtime.
- `ragenius_app` is legacy/specification reference and must not receive integrated runtime behavior.
- `ragenius_builder` owns authoring and administrative workflows.
- `rag_subsystem` exclusively owns retrieval and indexing internals.
- Every compiled snapshot, session, resource request, and retrieval request must remain scoped to its `app_id`.

## 3. Canonical Runtime Authority

The published `compiled_contract.hybrid_instruction_runtime_model` is the canonical semantic source for normal user-query execution.

The following are projections or consumers of that source and must not independently broaden or reinterpret it:

- `instruction_runtime_model`
- `template_registry` compatibility structures
- planner candidate packets
- `session_execution_state`
- `turn_execution_plan`
- GUI workflow/module/step status

Legacy structures may be used only when no valid compiled semantic target is available.

## 4. Compiler Contract

### 4.1 Structural classification

The compiler must distinguish:

- global interaction or routing policy
- primary and supplementary workflows
- support and follow-up modules
- executable procedures
- executable procedure steps
- resource catalogs and output contracts

A section title that owns multiple numbered actions is a module or workflow title when its authored semantics define a service boundary. Its numbered child actions are procedure steps and must not replace the parent module identity.

Within a support-module section, an explicitly labeled procedural list such as
`互動流程`, `執行流程`, `核心任務`, `使用原則`, `使用步驟`, or `操作規則`
is authoritative for executable step extraction. Preceding numbered taxonomies,
reference categories, trigger examples, or other explanatory lists remain module
guidance and must not be merged into that procedure's `step_sequence`.

### 4.2 Module orchestration

Module orchestration is compiled only when the current application's authored instructions explicitly define orchestration semantics. A normalized bilingual heading such as `模組調度規則_module_orchestration` may identify that section.

Orchestration recognition is app-local and content-grounded. Recognition in one application must not introduce orchestration behavior into another application.

Compiled orchestration may define:

- semantic module selection
- assistant-suggested module activation
- multi-module composition
- ordered module sequences
- task-to-module mappings

### 4.3 Canonical identity

Each executable concept must resolve to one canonical identifier across:

- routing rules
- service blocks
- procedures and steps
- support/follow-up modules
- hybrid planner candidates and decisions
- persisted session state
- GUI projections

Aliases may be accepted at compile and rehydration boundaries, but persisted active state must use canonical identifiers.

### 4.4 Procedure and resource ownership

Each procedure step may declare `resource_refs` and `bundled_resource_refs`.

- Non-empty refs are authoritative for that step.
- Empty refs are valid and mean that the step needs no step-owned file when any step in the same procedure has an explicit resource mapping.
- If no step in a procedure has any resource mapping, module-level resource bindings remain a compatibility fallback.
- Bundled execution loads the bundle's declared resources as one execution unit.

Compatibility projection must preserve these distinctions and must not convert a resource-free mapped step into a module-wide resource load.

### 4.5 Publication and rehydration

Only a validated compiled snapshot may become active. Rehydration must preserve canonical target identity, active step ownership, module index, and compatibility fields required by existing sessions.

Invalid or absent semantic snapshots may use documented legacy fallback behavior. Fallback must be observable and must not mutate another application's snapshot.

## 5. Graph State Contract

`GraphState` and its serialization mirror must explicitly preserve planner fields used between graph nodes, including:

- `_llm_planner_hybrid`
- `hybrid_planner_decision_packet`
- `hybrid_planner_shadow_output`
- `session_execution_state`
- `turn_execution_plan`
- resource load plans and resource contexts

Fields used for graph-node communication must not rely solely on undeclared extra-state behavior.

## 6. Query Planner Contract

### 6.1 Decision precedence

Planner decisions follow this order:

1. hard deterministic safety, command, artifact-gate, and explicit stop rules
2. a valid explicit compiled hybrid target step and its owning service block
3. valid continuation of the persisted active compiled scope
4. bounded semantic selection among compiled candidates
5. compatibility or legacy fallback when compiled selection is unavailable or invalid

A valid explicit hybrid target must not be overwritten by stale module state, legacy keyword matching, or a module index reset.

### 6.2 Step progression

- The active step is the step executed for the current turn.
- A next-step candidate is not GUI-visible active state until the transition is validated and persisted.
- A target step must belong to the selected service block's procedure.
- Cross-module transitions must update service block, support-module identity, active step, and `current_module_index` coherently.
- Content progression and GUI progression must derive from the same persisted turn state.

### 6.3 Module queues

`active_module_queue` and hybrid `module_sequence` describe ordered present/future orchestration. They do not make every queued module an active binding or resource scope.

Only the current queue item identified by `current_module_index`, or an explicitly activated follow-up module, may supply current-turn module resources.

### 6.4 Resource-selection precedence

For normal compiled execution, resource authority follows this order:

1. active step `resource_refs` or `bundled_resource_refs`
2. active executable follow-up module resources
3. explicitly activated current support-module resources
4. module-level compatibility fallback when the owning procedure has no step resource mappings
5. broad phase fallback only when no narrower executable resource scope exists

Future queued modules and unrelated selected candidates must not activate resource bindings.

### 6.5 Resource-request identity

Within one turn, requests with the same resource role and canonical resource identity represent one load request even when declared through both a dependency group and a direct resource id.

Deduplication must:

- preserve separate roles for the same physical file when the roles differ
- retain required/progression flags
- retain available binding, dependency-group, step, and support-module provenance
- avoid duplicate context injection and duplicate raw-plan rows

### 6.6 Compatibility behavior

The planner must preserve:

- modules whose resources exist only at module level
- artifact-gate and command-trigger bindings
- session-upload analysis
- follow-up module activation rules
- existing persisted sessions that can be canonically repaired

Compatibility behavior must not override a valid narrower compiled scope.

### 6.7 Semantic scope decision

The existing hybrid-planner call may return a `semantic_scope` decision with:

- `classification`: `in_scope`, `out_of_scope`, or `ambiguous`
- `confidence`: a value from `0.0` through `1.0`
- a concise reason and optional matched application signals

This decision must not add another LLM call. Only a coherent `out_of_scope`
decision with confidence of at least `0.85` may activate the existing
`general_out_of_scope_question` route. That route may answer from general model
knowledge and must not perform application retrieval or claim application
citations.

The runtime must reject route activation for continuation-dependent turns,
step advancement, refinements, option selection, uploads or attachments, or a
hybrid decision that also selects an application workflow, module, role, step,
or continuation target. Missing, malformed, ambiguous, in-scope, or
low-confidence decisions preserve existing planner behavior.

The validated decision and activation reason must be persisted as turn
diagnostics. Older hybrid outputs without `semantic_scope` remain valid.

Semantic Scope Decision is active in the hybrid-planner path. Representative
manual testing was accepted on 2026-09-06.

## 7. Persistence and GUI Contract

Each persisted assistant turn must retain an immutable summary of the workflow/module/step and relevant diagnostics for that turn. Session-level state may advance later, but inspecting an older turn must not display the latest turn's state in its place.

GUI status must derive from the selected turn snapshot when inspecting a turn and from current session state only for the live composer/session header.

## 8. Validation Requirements

Before persistence, validate that:

- active service block resolves in the current app snapshot
- active step belongs to the active service block's procedure
- primary support module agrees with step activation
- module index identifies the active module in the queue when a queue exists
- resource requests are compatible with the active step/module authority
- no queued inactive module contributes current-turn resources

## 9. Required Regression Coverage

Coverage must include:

- explicit hybrid target preservation through LangGraph state
- module heading versus procedure-step classification
- app-local module-orchestration recognition
- same-module and cross-module step advancement
- resource-free mapped steps
- resource-bearing mapped steps
- module-only resource fallback
- duplicate dependency/direct resource declarations
- queued follow-up behavior
- turn-specific GUI state inspection
- cross-application non-regression for Bible Tutor, Church Ministry Prompt Designer, GPT Application Design Assistant, and 與孩子一起成長

## 10. Change Control

Broad compiler or planner refactors require failing contract tests first. App-name-specific runtime branches are prohibited unless an explicit application contract cannot be represented generically and the exception is documented and isolated.
