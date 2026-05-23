# Semantic Runtime Mixed-Mode Design

> Scope: instruction-understanding compile/publish/restore behavior, semantic planner/runtime activation, and admin/chat UX for hybrid apps in `ragenius_app_skeleton`.

## Problem Statement

The current semantic instruction-understanding stack is partially working, but it still treats materially different app shapes too uniformly.

The main failure modes observed in live testing are:

1. Church Ministry can generate and optimize prompts, but optimization follow-up does not reliably become the active runtime scope and does not consistently bind `Optimization Strategy Library.md`.
2. `與孩子一起成長` can now produce a valid compiled model, but the model remains behaviorally thin and not yet strong enough as an execution contract.
3. Bible Tutor is a mixed-mode app:
   - `Bible Study` is procedural and has deterministic executable steps.
   - `Theology Discussion`, `Life Application`, and `General Q&A` are guided conversational modes without definitive fixed step sequences.
   - The current validator incorrectly treats all routed modes as requiring executable `procedure_steps`.
4. Frontend compile gating is too weak. A compiled id can suppress the "no valid model" warning even when the semantic model is invalid.
5. Backend publish policy is too permissive. An invalid semantic model can still become the active compiled model when no prior valid semantic model exists.

These are not isolated bugs. They point to one design gap: the runtime needs an explicit contract for different hybrid app families, and the UI/publish logic must align with that contract.

## Goals

1. Distinguish procedural, executable intent-routed, conversational intent-routed, and mixed-mode hybrid apps at compile/validation time.
2. Allow mixed-mode apps such as Bible Tutor to be valid when only some routed modes are step-driven.
3. Prevent invalid semantic models from being treated as ready-to-chat active models.
4. Preserve the last valid active model and make failed attempts visible as diagnostics.
5. Ensure the planner activates and surfaces the correct semantic runtime scope, including follow-up modules and their dependency resources.
6. Keep fixes generic. No app-id-specific runtime logic.

## Non-Goals

1. Rewriting `rag_subsystem`.
2. Redesigning Builder storage.
3. Replacing the current deterministic parse pipeline.
4. Solving every semantic quality issue in one pass. The first pass should establish the correct contract and protection boundaries.

## App Family Model

The validator and runtime must distinguish the following semantic app families:

### 1. Procedural Workflow

Characteristics:

- A primary workflow is executed through defined procedures and ordered executable steps.
- Step-level scope progression matters.

Examples:

- Church Ministry bundled generation path

Validation expectation:

- Routed procedural workflow targets must have executable procedures and steps.

### 2. Intent-Routed Executable

Characteristics:

- Multiple routes exist.
- Route targets must ground to concrete workflows/modules.
- Executable procedural behavior is required for the selected target.

Examples:

- `與孩子一起成長` when route targets are intended to map to concrete service workflows

Validation expectation:

- Routed executable targets must ground to concrete service blocks.
- Required procedures and executable steps must exist for those targets.

### 3. Intent-Routed Conversational

Characteristics:

- Multiple routes or modes exist.
- A routed mode is governed by trigger rules, entry response behavior, interaction logic, and resource bindings rather than fixed procedural steps.

Examples:

- Bible Tutor `Theology Discussion`
- Bible Tutor `Life Application`
- Bible Tutor `General Q&A`

Validation expectation:

- Conversational routed modes do not require definitive `procedure_steps`.
- They must still ground to a concrete semantic block with explicit interaction logic, entry behavior, or module/resource bindings.

### 4. Mixed-Mode Hybrid

Characteristics:

- Some routed targets are procedural.
- Some routed targets are conversational.

Examples:

- Bible Tutor as a whole

Validation expectation:

- Procedural routes must satisfy executable-step requirements.
- Conversational routes must satisfy conversational-mode requirements.
- The model must declare enough structure for the planner to activate the route-specific scope and bindings.

## Design Decisions

### Decision A: Introduce route capability semantics

Each semantic route target must be classifiable as one of:

- `procedural`
- `conversational`
- `module_only`

This can be stored explicitly in normalized semantic structures, or derived during grounding from deterministic sections.

Why:

- Current validation only knows "workflow with steps" versus "invalid".
- Mixed-mode apps require "workflow without steps, but still valid because it is a conversational mode".

### Decision B: Split active model and latest attempt semantics completely

The system already separates active snapshots from diagnostic attempts at the file level. The same distinction must apply to the publish contract and UI semantics:

- `active compiled model` = safe to restore and safe to use for chat
- `latest compile attempt` = may be invalid and diagnostic-only

Why:

- A failed compile should never silently become the model that gates chat readiness.

### Decision C: Strengthen chat readiness contract

For hybrid apps, chat readiness requires a valid semantic runtime model, not merely a compiled record id.

Why:

- The current frontend suppresses warnings too early and allows a misleading "ready" state.

### Decision D: Planner consumes capabilities, not app names

Runtime activation should be based on the selected target's semantic capability:

- procedural workflow step
- conversational mode block
- follow-up module
- support module

Why:

- Church Ministry and Bible Tutor differ in behavior style, but the planner gap is the same: the runtime must activate the right semantic scope and binding set.

## Backend Design

### 1. Mixed-Mode Validation

File:

- `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

Behavior:

- Extend normalization/grounding so route targets carry or derive a target capability.
- Validation rules become target-type aware:
  - procedural targets require executable procedures/steps
  - conversational targets require grounded target blocks plus interaction/entry semantics
  - module-only targets require valid module grounding and bindings

Bible Tutor implication:

- `Bible Study` remains procedural and must carry executable steps.
- `Theology Discussion`, `Life Application`, and `General Q&A` become valid conversational routed targets without mandatory step lists.

### 2. Publish Policy Tightening

File:

- `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

Behavior:

- Invalid semantic models do not become `active`.
- If there is no prior valid active model:
  - keep the attempt as diagnostic-only
  - surface explicit preview state such as `compile_required=true` or `invalid_active_model=false but no_valid_semantic_model=true`

### 3. Active/Attempt Preview Semantics

Files:

- `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- `ragenius_app_skeleton/backend/app/main.py`

Behavior:

- Admin detail responses should distinguish:
  - active compiled model summary
  - latest attempt summary
  - latest attempt validation errors
- Frontend should not have to infer active-vs-attempt state from a single compiled id.

### 4. Planner Follow-Up Activation Completion

File:

- `ragenius_app_skeleton/workflows/nodes/planner.py`

Behavior:

- If a follow-up module is semantically selected or queued after bundled completion, it must become the active runtime scope when its conditions are met.
- Active scope projection must match resource binding scope.
- Dependency resources for the active follow-up module must be included in selected/loaded resource planning.

Church Ministry implication:

- `Optimization Module` should surface as active runtime scope.
- `Optimization Strategy Library.md` should bind/load when optimization is active.

### 5. `與孩子一起成長` Quality Hardening

File:

- `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`

Behavior:

- Keep the current grounding improvements.
- Add a second-pass quality rule for executable routed workflows:
  - route target grounding is not enough
  - each executable route should have enough structured step or interaction behavior to be meaningfully runnable

This is not a rejection of conversational routes. It is a quality requirement for routes that claim to be executable workflows.

## Frontend Design

### 1. Compile Gating

File:

- `ragenius_app_skeleton/frontend/src/App.jsx`

Behavior:

- `compileRequired` must consider semantic validity for hybrid apps.
- A hybrid app with `semantic_compile_valid = false` is not chat-ready.

### 2. Status Presentation

Files:

- `ragenius_app_skeleton/frontend/src/App.jsx`
- `ragenius_app_skeleton/frontend/src/components/InstructionsPanel.jsx`

Behavior:

- Surface:
  - active model validity
  - latest failed attempt exists
  - latest failed attempt reason summary
- Do not collapse those states into a single `Compiled` pill.

## Testing Strategy

### Backend Tests

1. Bible Tutor mixed-mode validator tests
- procedural route with steps remains required
- conversational routed modes without steps are accepted when interaction semantics exist

2. Publish policy tests
- invalid semantic compile does not become active
- latest attempt is preserved diagnostically
- no valid active model remains compile-required

3. Planner tests
- queued follow-up module becomes active scope
- follow-up dependency resource is loaded

4. Integration tests
- admin detail response distinguishes active and latest failed attempt
- chat readiness payload reflects semantic validity

### Frontend Tests

1. `compileRequired` remains true when:
- hybrid app has compiled id
- semantic compile is attached
- semantic validity is false

2. Instructions panel renders:
- active valid/invalid state
- latest failed attempt summary when available

## Rollout Order

1. Frontend compile gating fix
2. Backend publish policy tightening
3. Mixed-mode validator update for Bible Tutor shape
4. Planner follow-up activation completion for Church Ministry
5. `與孩子一起成長` quality hardening

## Risks

1. Over-relaxing validation could reintroduce pseudo-workflow acceptance for `與孩子一起成長`.
2. Over-tightening publish policy without good UI feedback could make apps appear broken without clear explanation.
3. Planner scope/binding changes can regress already-working bundled flows if status projection and binding resolution diverge again.

## Mitigations

1. Relax validation only for explicitly conversational routed targets.
2. Keep executable-route requirements strict.
3. Add regression tests from all three real apps:
   - Church Ministry
   - `與孩子一起成長`
   - Bible Tutor

## Acceptance Criteria

1. Bible Tutor:
- `Bible Study` remains procedural and valid with executable steps
- `Theology Discussion`, `Life Application`, `General Q&A` compile as valid conversational routes without forced step lists
- invalid semantic model does not masquerade as chat-ready

2. Church Ministry:
- optimization follow-up becomes the active scope
- `Optimization Strategy Library.md` is loaded when optimization is active

3. `與孩子一起成長`:
- compiled model remains valid
- executable routes are better grounded and more behaviorally concrete

4. Frontend:
- no-valid-model warning remains visible when semantic model is invalid
- admin panel distinguishes active model from failed latest attempt
