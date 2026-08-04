# Intent-Routed Interaction Logic Design

> Scope: instruction-understanding compile, normalization, validation, publish semantics, and runtime/UI implications for rule-routed applications in `ragenius_app_skeleton`.

## Problem Statement

The current semantic contract treats rule-routed applications as `intent_routed_multi_workflow`.

That mode assumes:

1. at least one executable `primary_workflow`
2. routed targets that resolve to executable workflows or modules
3. executable `procedure_steps`

This is the wrong abstraction for apps such as:

1. `與孩子一起成長`
2. `Bible Tutor`

Those apps are primarily driven by:

1. role/routing rules
2. interaction logic
3. conditional mode switching

They may contain executable workflows or modules, but top-level routing policy is not itself a workflow contract.

Recent fixes made this mismatch visible instead of silently passing:

1. orchestration blocks are no longer preserved as fake workflows
2. explicit route target resolution is stricter
3. validation now fails because the top-level mode still demands workflow execution shape

This is not a regression in the core normalization logic. It is a top-level service-mode contract error.

## Goals

1. Introduce a service mode that accurately models rule-routed interaction apps.
2. Stop forcing orchestration/routing policy into workflow execution semantics.
3. Preserve executable workflows/modules when they are explicitly authored.
4. Keep `single_default_workflow` unchanged.
5. Keep `intent_routed_multi_workflow` available only for true executable multi-workflow apps.
6. Make GUI step rendering consistent with the new contract.

## Non-Goals

1. Rewriting `rag_subsystem`
2. Redesigning Builder storage
3. Replacing the current parser pipeline
4. Removing executable workflows/modules from apps that explicitly define them

## Proposed Mode

Add a new `primary_service_mode`:

- `intent_routed_interaction_logic`

This mode represents applications where:

1. top-level behavior is governed by routing policy and interaction logic
2. routes may activate roles, workflows, or modules
3. executable procedures/steps are optional and only required for targets that explicitly define them

## Contract

### 1. Allowed top-level structures

An `intent_routed_interaction_logic` model may contain:

1. `interaction_logic_blocks`
2. `routing_rules`
3. `role_profiles`
4. optional executable `service_blocks`
5. optional `procedures`
6. optional `procedure_steps`

### 2. Required top-level structures

An `intent_routed_interaction_logic` model must contain at least one of:

1. non-empty `routing_rules`
2. non-empty `interaction_logic_blocks`

### 3. Non-executable routing/orchestration policy

Blocks representing:

1. role/routing policy
2. mode-switching logic
3. layered response rules

must remain in `interaction_logic_blocks` and must not be required to own:

1. `primary_workflow`
2. `procedure_id`
3. `procedure_steps`

Examples for `與孩子一起成長`:

1. `五重角色模式`
2. `模式切換邏輯`
3. `多重需求分層規則`

### 4. Executable targets remain explicit

A route may still resolve to:

1. an explicit workflow target
2. an explicit module target

If a route resolves to one of those targets, the existing executable semantics still apply to that target.

### 5. Step requirements are target-specific, not mode-wide

Under `intent_routed_interaction_logic`:

1. executable workflows/modules with defined procedures may own steps
2. logic-only routes are valid without steps
3. the mode itself does not require global `primary_workflow` or `procedure_steps`

## Compiler Contract

### Existing incorrect prompt behavior

The compile prompt currently says:

1. if single default app -> `single_default_workflow`
2. if intent-routed across workflows or roles -> `intent_routed_multi_workflow`

This is too coarse.

### New prompt behavior

The compiler must choose among:

1. `single_default_workflow`
2. `intent_routed_multi_workflow`
3. `intent_routed_interaction_logic`

Selection rule:

1. use `single_default_workflow` only when one default workflow is the app contract
2. use `intent_routed_multi_workflow` only when the app is genuinely modeled as multiple executable workflows
3. use `intent_routed_interaction_logic` when routing policy and interaction logic are primary, and execution is optional or partial

## Validation Contract

### `single_default_workflow`

No change.

### `intent_routed_multi_workflow`

Keep strict workflow-execution requirements.

This mode remains valid only for true executable multi-workflow apps.

### `intent_routed_interaction_logic`

Validation rules:

1. require `routing_rules` or `interaction_logic_blocks`
2. do not require `primary_workflow`
3. do not require global `procedure_steps`
4. validate executable targets only when those targets are present
5. preserve module/workflow target validation for explicitly grounded targets

## Normalization Rules

Keep these existing fixes:

1. title-marker contract
2. orchestration stripping from executable artifacts
3. explicit target resolution
4. module alias canonicalization
5. interaction-logic title leak prevention

Change their top-level interpretation:

1. do not use missing executable workflows as a reason to fail the whole app when mode is `intent_routed_interaction_logic`
2. unresolved interaction-logic policy blocks stay valid if they are represented as logic rather than executable targets

## Runtime and UI Implications

### Chat runtime

The active model may be valid even when no executable step sequence exists for the current route.

That is expected under `intent_routed_interaction_logic`.

### GUI executed-step panel

The GUI must not assume:

1. every route has executable steps

For this mode:

1. if the active route target has executable steps, show them
2. if the active route target is logic-only, show no executed steps without treating that as failure

This likely explains the current observation:

1. chat behaves correctly under the active model
2. GUI shows no executed step

## App Impact

### `與孩子一起成長`

Expected mode:

- `intent_routed_interaction_logic`

Reason:

1. `五重角色模式`, `模式切換邏輯`, and `多重需求分層規則` are primary contract elements
2. child workflows/modules are subordinate optional executable targets

### `Bible Tutor`

Expected mode:

- likely `intent_routed_interaction_logic`

Reason:

1. top-level routing is mode/rule driven
2. not every route is a workflow-step execution path

This should be validated against the current authored instructions, not hardcoded by app id.

## Backward Compatibility

1. Existing active snapshots remain readable.
2. Existing `intent_routed_multi_workflow` snapshots do not need migration to stay loadable.
3. Recompiles may produce the new mode when appropriate.
4. The validator must continue accepting legacy valid snapshots for old modes.

## Risks

1. Over-broad mode selection could downgrade true executable apps into the new logic mode.
2. GUI assumptions around executed steps may still cause misleading “empty step” displays after backend fixes.
3. Mixed-mode apps with both logic and execution will need careful preview/runtime state handling.

## Mitigations

1. make mode selection explicit in compiler prompt and validated by deterministic signals
2. keep executable-target validation intact for explicit workflow/module targets
3. add regression coverage for:
   - `與孩子一起成長`
   - `Bible Tutor`
   - true `single_default_workflow`
   - true `intent_routed_multi_workflow`

## Acceptance Criteria

1. `與孩子一起成長` recompiles successfully without `intent_routed_multi_workflow` errors
2. `Bible Tutor` recompiles successfully under the correct mode
3. routing/orchestration policy no longer needs to masquerade as workflows
4. executable modules/workflows continue to validate when explicitly present
5. GUI step display no longer treats “no steps for logic-only route” as failure
