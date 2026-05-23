# Snapshot-First Compiler and Planner Hardening Design

## Scope

This design is scoped to fixing the recurring runtime-contract failures in:

- Bible Tutor
- Church Ministry Prompt Designer

`與孩子一起成長` is a protected non-regression target. Its current live behavior is treated as correct and must not be degraded by this work.

## Problem Statement

The recurring failures are not primarily frontend bugs and not primarily planner bugs. They are contract failures between:

1. instruction understanding compile output
2. active snapshot runtime projection
3. planner resource selection and persistence
4. GUI workflow-status projection

The most visible symptom is broad resource loading:

- all `.md` files are loaded for Bible Tutor steps instead of the current step file
- all Church Ministry module files are loaded during clarification/core/optimization turns instead of the current execution scope

This recurrence happens because active snapshots are still underspecified at the step and follow-up execution level, so the planner falls back to broad module-phase bindings and legacy compatibility structures.

## Current Live Failure Shapes

### Bible Tutor

Observed in live sessions:

- the session routes to the correct module and step
- the active step title is usually correct
- but resource selection still expands to the full `查經互動模組` file set

Active-snapshot defect pattern:

- canonical hybrid `procedure_steps` for Bible-study steps still have empty or incomplete `resource_refs`
- compatibility/runtime projections still preserve broad module-wide semantics
- planner then widens from `phase:查經互動模組`

### Church Ministry Prompt Designer

Observed in live sessions:

- chat content broadly follows clarification, core workflow, and optimization behavior
- persisted runtime state can remain stuck on `Clarification`
- GUI therefore does not show `核心流程` or `Optimization Module`
- all `.md` files from broad module-phase bindings are loaded on all turns

Active-snapshot defect pattern:

- `Clarification` and `Core Workflow Execution` lack concrete step-owned resource refs
- `Optimization Module` is not consistently projected as a runtime-bindable executable block
- support-module phase bindings remain broader and stronger than step scope

### `與孩子一起成長`

Current status:

- live behavior is currently correct enough to treat as baseline
- the design must preserve its route-to-workflow visibility and execution behavior

## Goals

1. Make active snapshots authoritative for step-scoped and follow-up-scoped resource loading.
2. Ensure planner can load only the resources owned by the active step or active executable follow-up module.
3. Ensure GUI-visible workflow/module/step state is a direct projection of persisted execution state.
4. Protect `與孩子一起成長` as a non-regression target.

## Non-Goals

1. No redesign of `rag_subsystem`.
2. No broad rewrite of all apps' runtime contracts in one pass.
3. No frontend-only workaround for backend contract defects.
4. No app-name-specific planner heuristics as the primary fix.

## Root Cause Analysis

### Primary Defect: Weak Active Snapshot Contract

The active snapshot is currently too weak in three places:

1. executable steps do not consistently own their resource files
2. executable follow-up paths do not consistently exist as runtime-facing blocks
3. compatibility runtime preserves broader resource semantics than canonical active step scope

When these defects exist, planner cannot deterministically narrow the resource set.

### Secondary Defect: Planner Fallback and Persistence

Because the snapshot is weak, planner falls back to:

- broad `phase:*` bindings
- broad support-module notes
- stale clarification/module state

Planner should not be the first line of repair for missing contract data. It should only enforce precedence and persistence consistency once the snapshot contract is correct.

## Design Principles

1. Snapshot contract first.
2. Planner second.
3. One active execution path, one persisted execution path.
4. One active execution path, one resource scope.
5. Compatibility runtime is projection only.
6. Protected non-regression for `與孩子一起成長`.

## Target Contract

### 1. Canonical Runtime Authority

The canonical source of runtime truth is:

- `compiled_contract.hybrid_instruction_runtime_model`

All later layers must derive from it:

- `instruction_runtime_model`
- planner execution context
- session execution state
- GUI workflow-status payload

No later layer may broaden or reinterpret active step resource ownership independently.

### 2. Step-Owned Resource Contract

Every executable step that can become active in conversation must explicitly own its resource files.

Examples:

- Bible Tutor:
  - `Observation` -> `observation_guide.md`
  - `Identify Relationships` -> `identify_relationships_guide.md`
- Church Ministry:
  - `Clarification` -> clarification-specific resources
  - `Core Workflow Execution` -> core-step resources
  - `Optimization Module` and any executable sub-step -> optimization-specific resources

If a step has concrete resource refs, broad phase/module bindings must not widen that scope.

### 3. Executable Follow-Up Contract

Any flow that can become visibly active in chat must exist as a runtime-bindable executable target.

For Church Ministry this includes:

- `Optimization Module`

That executable target must:

- appear in runtime-facing service blocks
- have a canonical id
- own its narrow `.md` resource set
- be persistable as active session state

It cannot exist only as descriptive metadata or a compatibility-only structure.

### 4. Compatibility Runtime Projection Contract

`instruction_runtime_model` remains for backward compatibility, but it must be a strict projection of canonical hybrid runtime.

Required behavior:

- if hybrid runtime gives a narrow step scope, compatibility runtime must not preserve broader contradictory module scope as authoritative
- compatibility projection may support older reader code, but it may not broaden the active resource contract

### 5. Canonical Identity Contract

The same execution concept must have one canonical identity across:

- routing target
- instruction service block
- procedure owner
- follow-up module
- session execution state inputs
- GUI workflow payload inputs

Alias tolerance may still exist at validation boundaries, but the active persisted path must resolve to one canonical id.

## Planner Responsibilities After Snapshot Hardening

Planner remains responsible for execution-state selection and persistence, but only against the strengthened snapshot contract.

### 1. Resource-Precedence Rules

Planner must apply resource precedence in this order:

1. active step `resource_refs` / `bundled_resource_refs`
2. active executable follow-up module resources
3. explicitly invoked support-module resources
4. broad `phase:*` bindings only as fallback

Rule:

- if active step or active follow-up module has concrete resource refs, broad phase expansion must not widen the selected file set

### 2. Executable Persistence Rules

Planner must persist one coherent active execution path:

- active workflow or active executable module/follow-up module
- active step if applicable
- compatible primary scope and service block ids
- resource scope aligned with that active path

The system must not allow:

- content behaving as optimization while persisted state still says clarification
- content behaving as observation while selected resources still come from the full module pack

### 3. Validation Before Save

Before session state is saved, runtime validation must ensure:

1. active workflow/module/follow-up resolves to a known executable target
2. active step belongs to that target
3. primary scope is compatible with the active executable target
4. selected resource scope is compatible with the active step/module
5. broad phase bindings are not stored as dominant scope when a narrower explicit scope exists

## Protected Non-Regression Strategy

`與孩子一起成長` is protected throughout this work.

Protection rules:

1. no shared change may reinterpret its route-to-workflow behavior unless covered by explicit regression tests
2. no planner change may broaden its currently working resource scope
3. no compile change may remove runtime-facing behavior that current live sessions rely on

## Verification Standard

A recurring issue is not considered fixed unless all four gates pass.

### Gate 1: Compile Contract Tests

Required assertions:

- Bible Tutor hybrid steps own step-specific `resource_refs`
- Church Ministry clarification/core/optimization execution scopes own narrow resources
- Church Ministry optimization exists as an executable runtime-facing block
- compatibility runtime does not broaden a canonical narrow step contract

### Gate 2: Planner/Runtime Persistence Tests

Required assertions:

- Bible Tutor active study step persists with only its owned resources selected
- Church Ministry clarification persists correctly, then core persists correctly, then optimization persists correctly
- persisted active path and selected resources remain internally consistent

### Gate 3: GUI Payload Tests

Required assertions:

- Bible Tutor GUI shows the persisted active step and does not imply broader module execution
- Church Ministry GUI shows `核心流程` when core is active
- Church Ministry GUI shows `Optimization Module` when optimization is active

### Gate 4: Cross-App Non-Regression

Required assertions:

- `與孩子一起成長` retains its current working behavior
- existing unaffected runtime/LLM compatibility tests remain green

## Implementation Phases

### Phase A: Snapshot Contract Hardening

Target:

- `instruction_understanding_service.py`

Work:

1. backfill or generate explicit step-owned resource refs for Bible Tutor hybrid procedure steps
2. backfill or generate explicit clarification/core resource refs for Church Ministry executable workflow steps
3. project Church Ministry `Optimization Module` into runtime-facing executable blocks with canonical ids and owned resources
4. tighten compatibility-runtime projection so it cannot broaden canonical active-step ownership

This phase should be enough to make active snapshots authoritative for narrow resource loading.

### Phase B: Compile Contract Tests

Targets:

- `test_instruction_understanding_service.py`

Work:

1. encode the expected hybrid snapshot contract for Bible Tutor
2. encode the expected hybrid snapshot contract for Church Ministry
3. encode compatibility-projection non-broadening rules
4. encode protected non-regression checks for `與孩子一起成長`

### Phase C: Planner Precedence and Persistence Cleanup

Target:

- `planner.py`

Work:

1. make planner prefer step-owned resources over phase bindings without app-specific heuristics
2. persist Church Ministry core and optimization execution state from canonical executable targets
3. validate persisted state before save

This phase is intentionally narrow. It is not a replacement for missing snapshot contract data.

### Phase D: Planner and GUI Tests

Targets:

- `test_planner_node.py`
- `test_builder_chat_integration.py`

Work:

1. verify narrow resource loading for Bible Tutor active steps
2. verify Church Ministry clarification -> core -> optimization visible state progression
3. verify GUI payload matches persisted runtime state
4. verify `與孩子一起成長` remains correct

## Risks and Mitigations

### Risk 1: Accidental regression in `與孩子一起成長`

Mitigation:

- treat it as explicit non-regression in all phases
- avoid broad shared runtime rewrites
- prefer compile-contract strengthening over planner reinterpretation

### Risk 2: Fixing planner before snapshot contract is complete

Mitigation:

- do not claim resolution until compile-contract gates pass first
- planner changes must be justified as precedence/persistence enforcement only

### Risk 3: Compatibility-runtime readers still depending on broad phase behavior

Mitigation:

- preserve compatibility structures
- narrow only the active-step ownership semantics
- verify GUI and existing app flows after the change

## Recommended Execution Order

1. write failing compile-contract tests for Bible Tutor and Church Ministry
2. harden active snapshot generation
3. write failing planner persistence tests against the hardened contract
4. narrow planner resource precedence and persistence behavior
5. run GUI payload tests
6. run cross-app non-regression tests
7. perform live verification for:
   - Bible Tutor
   - Church Ministry
   - `與孩子一起成長` as non-regression only

## Decision

The recurring broad-resource-loading issue should be treated as a snapshot-first compiler/runtime-model defect. Planner should be repaired only after the active snapshot contract is strong enough to be authoritative.
