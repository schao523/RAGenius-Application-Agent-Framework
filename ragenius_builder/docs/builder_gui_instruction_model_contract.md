# Builder GUI Instruction Model Contract

Date: 2026-06-15

## Purpose

This contract defines how `ragenius_builder` should display compiled application instruction models in the Builder GUI.

The target user is a GPT designer editing application instructions in Builder.

The goal is to let the designer inspect the runtime instruction model produced and used by `ragenius_app_skeleton`, so they can compare:

- what they wrote in Builder instructions
- what the runtime compiler understood
- what the app runtime will actually use

## Scope

This contract applies to the Builder application instruction configuration UI, especially:

- `ragenius_builder/flask_scaffold/templates/config.html`
- the `Instructions` tab
- any future `Runtime Model`, `Compiled Understanding`, or `Instruction Understanding` panel

This contract does not move chat behavior into Builder.

This contract does not make Builder the runtime orchestrator.

## Source Of Truth

The runtime instruction model source of truth is the same compiled understanding artifact used by `ragenius_app_skeleton`.

Current artifact shape:

```text
understanding.json
```

Current app-skeleton snapshot export location:

```text
ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/{app_id}/understanding.json
```

Current app-skeleton runtime DB table:

```text
runtime_state.db: app_instruction_understanding
```

Builder GUI must not invent a separate interpretation of instructions for display.

Builder GUI may present a friendly projection, but that projection must be derived from the same compiled model fields that `ragenius_app_skeleton` produces and uses.

## Required Consistency Rule

Any Builder GUI Instruction Model view must remain consistent with `ragenius_app_skeleton` runtime semantics.

Allowed:

- read and display an existing compiled `understanding.json`
- call a shared compiler/API that returns the same artifact shape
- render curated summaries from `understanding.json`
- expose raw `understanding.json` for audit

Not allowed:

- parse Builder Markdown independently and call that the runtime model
- infer workflows, resources, or policies using Builder-only heuristics
- show a model that differs from the artifact consumed by `ragenius_app_skeleton`
- silently compile on page load if the runtime contract requires explicit compile/refresh

## UI Semantics

The existing Markdown preview answers:

```text
What did the designer write?
```

The Instruction Model view must answer:

```text
What did runtime compile and use?
```

Therefore, Builder should not treat rendered Markdown preview and compiled runtime model as the same view.

Recommended UI layout:

- `Markdown Preview`
- `Runtime Model`
- `Raw JSON`

If screen space is limited, `Runtime Model` should become the primary preview once a compiled understanding exists, with Markdown preview still available as a secondary mode.

## Required Display Sections

The friendly Instruction Model view should display these sections when available.

### Compile Status

Show:

- `compiled_status`
- `compiled_at`
- `compile_duration_ms`
- `compile_errors`
- `instruction_source_hash`
- `instruction_source_version`
- `instruction_uri`
- `parser_contract_version`
- `binding_logic_version`
- `resource_catalog_hash`

### Runtime Mode

Show from `compiled_contract.instruction_runtime_model` and/or `compiled_contract.hybrid_instruction_runtime_model`:

- `primary_service_mode`
- `default_workflow_id`
- semantic compile attached/valid state
- active/fallback status if exposed

### Service Blocks

Show:

- `instruction_service_blocks`
- primary workflows
- support modules
- follow-up modules
- default flags
- trigger conditions
- required inputs

### Procedures And Steps

Show:

- `instruction_procedures`
- `procedure_steps`
- step order
- step title
- step execution mode
- wait/stop behavior
- advance conditions
- linked support modules/resources

### Resources And Bindings

Show:

- `instruction_resources`
- `dependency_groups`
- `phase_resource_bindings`
- filenames
- document IDs
- resource roles
- missing/stale resource warnings if available

### Policies And Constraints

Show:

- `global_policies`
- `progression_rules`
- `turn_constraints`
- `response_policies`
- `clarification_gate_rules`

### Validation

Show:

- validation status
- validation errors
- validation warnings
- semantic warnings
- review findings if the lifecycle payload includes them

### Raw Artifact

Expose a collapsible raw JSON panel containing the exact `understanding.json` payload or exact compiled DB payload.

Raw JSON is required for debugging and designer trust.

## Staleness Semantics

Builder must make staleness visible.

The GUI should compare, when possible:

- current instruction content hash/version
- compiled `instruction_source_hash`
- compiled `instruction_source_version`
- compiled `instruction_uri`
- `compiled_at`

If the compiled model does not match the current Builder instructions, show a clear stale state.

Examples:

- `No compiled understanding exists for this app.`
- `Compiled model is older than the current instructions.`
- `Compiled model source hash does not match current instructions.`
- `Compiled model exists but semantic compile is invalid.`

## Refresh And Compile Semantics

Builder must preserve explicit compile semantics.

Opening the instruction page should not implicitly mutate runtime state.

Recommended actions:

- `Refresh`: reload the latest compiled model
- `Compile`: explicitly request a new compile through the shared app-skeleton compiler/API when available
- `Review`: explicitly request review if the lifecycle supports it

The first Builder GUI slice may be read-only:

- display latest compiled model
- show missing/stale state
- expose raw JSON
- no compile mutation

## Runtime Boundary

Builder may display runtime instruction models.

Builder must not execute end-user chat workflows.

Builder must not become the planner or runtime orchestrator.

Builder must not own a divergent instruction compiler unless that compiler is the shared compiler used by `ragenius_app_skeleton`.

## Data Ownership

Current app-skeleton `.state` files are runtime/generated artifacts.

They are useful for inspection and compatibility, but Builder should not treat that filesystem path as a long-term hard dependency.

Preferred long-term source:

- shared compiler service/API
- shared repository/service layer
- builder-owned pointer to the exact compiled artifact produced by the shared compiler

Until that exists, any file-based integration must be marked as an adapter to the app-skeleton artifact layout, not as an independent Builder storage contract.

## Acceptance Criteria

A Builder Instruction Model GUI implementation satisfies this contract when:

- the designer can edit instructions in the existing Instructions tab
- the designer can see the compiled runtime model derived from the same `understanding.json` shape used by `ragenius_app_skeleton`
- the view shows compile status, runtime mode, service blocks, procedures, resources, policies, validation, and raw JSON
- stale or missing compiled model states are visible
- Builder does not silently recompile on page load
- Builder does not invent a separate runtime model
- Builder does not move chat/runtime orchestration into Builder

## Out Of Scope

Do not include in the first implementation unless explicitly requested:

- end-user chat execution
- planner behavior changes
- semantic compiler redesign
- instruction storage redesign
- automatic compile on every keystroke
- direct mutation of `ragenius_app_skeleton` runtime state from passive preview rendering
