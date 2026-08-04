# Builder GUI Instruction Model Design

Date: 2026-06-15

## Purpose

This document defines the user experience for showing compiled application instruction models in `ragenius_builder`.

The target user is a GPT designer who edits application instructions in Builder and needs to verify how `ragenius_app_skeleton` compiled and interpreted those instructions at runtime.

The Builder GUI must make the compiled model correct, logical, and easy to read without losing the original runtime interpretation produced by `ragenius_app_skeleton`.

Authoritative contract:

- `ragenius_builder/docs/builder_gui_instruction_model_contract.md`

## Core UX Principle

The instruction configuration page must clearly separate three different questions:

| Question | View | Source |
| --- | --- | --- |
| What did the designer write? | Markdown editor / Markdown preview | Builder file-backed instructions |
| What did runtime understand? | Runtime Model | `understanding.json` or equivalent compiled payload |
| What exact payload did runtime produce/use? | Raw JSON | Exact runtime artifact |

The Runtime Model view is not a new compiler, a paraphrase, or a Builder-only interpretation. It is a deterministic display projection over the same compiled model shape produced and used by `ragenius_app_skeleton`.

## UX Goals

The design should let a designer:

- Confirm whether a compiled model exists for the current app.
- Confirm whether the compiled model is current or stale relative to the Builder instruction file.
- See the runtime service mode, workflow structure, procedures, resources, policies, and validation status without reading raw JSON first.
- Drill from friendly display sections back to exact raw model fields.
- Inspect the exact raw JSON artifact when troubleshooting or validating compiler behavior.
- Understand compile failures, semantic warnings, missing resources, and review states without guessing.

## Non-Goals

Do not include these in the Builder instruction model UX:

- End-user chat execution.
- Runtime orchestration.
- Builder-local instruction parsing that diverges from `ragenius_app_skeleton`.
- Silent compile on page load.
- Automatic compile on every editor change.
- Instruction storage redesign.
- Direct mutation of app-skeleton runtime state from passive preview rendering.

## Page Placement

The first target is the existing Builder application configuration page:

- `ragenius_builder/flask_scaffold/templates/config.html`

The current page already has an `Instructions` tab with an editor and a simple Markdown preview. The design should evolve that preview area into an inspection area with display modes.

Recommended display modes:

- `Runtime Model`
- `Markdown Preview`
- `Raw JSON`

When a compiled model exists, `Runtime Model` should be the default preview mode because it provides the most differentiated designer value. `Markdown Preview` should remain available because it answers a different question.

## Recommended Layout

Use a two-pane layout on the `Instructions` tab.

Left pane:

- Existing instruction markdown editor.
- Existing save controls.
- Optional explicit `Compile` action when a shared compile API exists.
- Optional `Refresh model` action to reload the latest compiled artifact.

Right pane:

- Status strip.
- Display mode tabs.
- Friendly Runtime Model projection.
- Markdown Preview.
- Raw JSON viewer.

The right pane must not hide stale, failed, or missing states behind collapsed panels. Those states should appear at the top.

## Status Strip

The Runtime Model area should always start with a compact status strip.

Show these fields when available:

- App ID.
- Compile status.
- Semantic compile status.
- Compiled timestamp.
- Parser contract version.
- Binding logic version.
- Instruction source version.
- Instruction source hash.
- Resource catalog hash.
- Freshness state.

Freshness states:

- `Current`: compiled source hash/version matches current Builder instructions.
- `Stale`: compiled source hash/version differs from current Builder instructions.
- `Missing`: no compiled model exists.
- `Failed`: compiled artifact exists but compile status or validation failed.
- `Semantic invalid`: syntax compiled but semantic validation is invalid.
- `Unknown`: freshness cannot be computed from available metadata.

The status strip should use short badges and exact values. Do not replace exact IDs, versions, or hashes with prose-only descriptions.

## Runtime Model Information Architecture

The friendly Runtime Model view should be ordered by how a designer reasons about an application.

### 1. Overview

Purpose:

- Show the high-level runtime interpretation before details.

Display:

- Primary service mode.
- Default workflow ID.
- Number of service blocks.
- Number of procedures.
- Number of procedure steps.
- Number of resources.
- Number of validation warnings/errors.
- Semantic compile attached/valid state.
- Review state if available.

UX:

- Use a compact summary card grid.
- Use exact runtime field names in small monospace labels or detail tooltips.
- Link each summary count to the relevant section.

### 2. Service Blocks And Workflows

Purpose:

- Show how runtime decomposed the instruction set into service blocks, primary workflows, support modules, and follow-up modules.

Display:

- Block ID.
- Block title/name.
- Block type or role.
- Default flag.
- Trigger conditions.
- Required inputs.
- Linked procedure IDs.
- Linked resource IDs.

UX:

- Render as grouped cards or a tree.
- Put primary workflows first.
- Put support/follow-up modules after primary workflows.
- Keep runtime IDs visible.
- Provide a `Raw path` or expandable source detail for each block.

### 3. Procedure Map

Purpose:

- Show what runtime will do step by step.

Display:

- Procedure ID.
- Procedure title/name.
- Procedure role.
- Ordered procedure steps.
- Step ID.
- Step title.
- Step execution mode.
- Wait/stop behavior.
- Advance conditions.
- Linked support modules.
- Linked resources.
- Output or response expectations if present.

UX:

- Render procedures as collapsible timelines.
- Preserve runtime order exactly.
- Do not reorder steps for readability if that changes execution meaning.
- Use warnings inline on the affected procedure or step.
- For large procedures, provide a `Collapse all` and `Expand all` control.

### 4. Resources And Bindings

Purpose:

- Show what runtime believes the instruction model depends on.

Display:

- Instruction resources.
- Dependency groups.
- Phase resource bindings.
- Resource IDs.
- Resource roles.
- Filenames or labels.
- Document IDs.
- Missing/stale indicators when available.
- Binding target procedure, phase, or step.

UX:

- Render a resource table with filters by role/status.
- Link resources back to procedures or service blocks that use them.
- Show missing or stale resources as high-priority validation signals.

### 5. Policies And Constraints

Purpose:

- Show runtime behavior rules that affect how the app responds.

Display:

- Global policies.
- Progression rules.
- Turn constraints.
- Response policies.
- Clarification gate rules.
- Any safety, refusal, or escalation rules present in the compiled model.

UX:

- Group policies by category.
- Preserve exact policy text when the compiled model carries exact text.
- Show runtime field names for each policy group.
- Avoid summarizing policy text in a way that changes constraints.

### 6. Validation And Review

Purpose:

- Make compile quality and review status visible.

Display:

- Compile errors.
- Validation errors.
- Validation warnings.
- Semantic warnings.
- Review findings.
- Approval or revision status if present.

UX:

- Put errors before warnings.
- Link each issue to the affected model path when available.
- Use exact compiler messages.
- Do not suppress low-level messages; make them collapsible if noisy.

### 7. Raw Artifact

Purpose:

- Preserve designer trust and runtime fidelity.

Display:

- Exact `understanding.json` payload or exact compiled DB payload.

UX:

- Provide formatted JSON with search.
- Provide copy support.
- Preserve field names and values exactly.
- Do not pretty-print in a way that drops null, empty, unknown, or vendor-specific fields.

## Friendly Projection Rules

The Runtime Model view may make the compiled model easier to read, but every friendly element must trace back to the raw artifact.

Required rules:

- Every displayed section must be derived from the compiled payload, not from Markdown parsing.
- Every friendly card/table row should retain the source JSON path internally.
- Friendly labels may be added, but exact runtime IDs and field names must remain inspectable.
- Unknown fields must not be discarded from Raw JSON.
- Missing optional fields should render as unavailable, not inferred.
- Derived counts are allowed if they are computed directly from runtime arrays/objects.
- Derived warnings are allowed only for display mechanics, such as stale hash mismatch, and must be labeled as Builder display diagnostics.

## Field Mapping Strategy

The display adapter should read the compiled model defensively.

Primary runtime model locations:

- `compiled_contract.instruction_runtime_model`
- `compiled_contract.hybrid_instruction_runtime_model`

Compiler and lifecycle metadata:

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
- `semantic_compile`

Common runtime model collections:

- `instruction_service_blocks`
- `instruction_procedures`
- `procedure_steps`
- `instruction_resources`
- `dependency_groups`
- `phase_resource_bindings`
- `global_policies`
- `progression_rules`
- `turn_constraints`
- `response_policies`
- `clarification_gate_rules`

If both `instruction_runtime_model` and `hybrid_instruction_runtime_model` exist, the UI should show which one is active or primary according to runtime metadata. If the active model cannot be determined, show both with a clear label and mark the active source as unknown.

## Staleness Design

Staleness is a first-class UX concern because the designer may edit instructions after the last compile.

Builder should compute freshness when possible by comparing:

- Current Builder instruction file content hash.
- Current Builder instruction metadata/version.
- Compiled `instruction_source_hash`.
- Compiled `instruction_source_version`.
- Compiled `instruction_uri`.
- Compiled timestamp.

Recommended messages:

- `No compiled runtime model exists for this app.`
- `Compiled runtime model is current.`
- `Compiled runtime model is older than the current Builder instructions.`
- `Compiled source hash does not match the current instruction file.`
- `Compiled model exists, but semantic compile is invalid.`
- `Freshness cannot be verified because source hash/version metadata is unavailable.`

The UI should allow viewing stale models, but it must label them clearly.

## Empty And Error States

Missing compiled model:

- Show a short explanation that Builder has instructions but no runtime understanding artifact.
- Show `Markdown Preview` as available.
- Show `Raw JSON` as unavailable.
- If compile API exists, show explicit `Compile runtime model`.

Invalid JSON:

- Show parse error.
- Preserve access to raw text if available.
- Do not attempt to render a partial friendly model as authoritative.

Compile failed:

- Show compile status and errors first.
- Show any partial compiled payload only as partial or failed.
- Keep Raw JSON available.

Runtime source unavailable:

- Show adapter/source error.
- Do not silently fall back to Builder Markdown interpretation.

## First Implementation Slice

The first Builder implementation should be read-only.

Must-have:

- Load latest compiled model for the selected app from the current app-skeleton artifact source or an adapter over that source.
- Display status strip.
- Display Runtime Model overview.
- Display service blocks/workflows.
- Display procedures and steps.
- Display resources and bindings.
- Display policies and constraints.
- Display validation/review messages.
- Display Raw JSON.
- Preserve Markdown Preview as a separate mode.
- Show missing/stale/failed states.

Defer:

- Compile action.
- Review action.
- Approval workflow.
- Diff view between two compiled models.
- Historical compile timeline.
- Editing model fields from Builder.
- Runtime testing from the instruction model page.

## Implementation Areas

Likely Builder areas affected when implementation begins:

- `ragenius_builder/flask_scaffold/app.py`
- `ragenius_builder/flask_scaffold/storage.py`
- `ragenius_builder/flask_scaffold/templates/config.html`
- Builder static JavaScript or inline page script used by the configuration page.
- New instruction model adapter/service module.
- New tests under `ragenius_builder/flask_scaffold/tests/`.

Likely app-skeleton source areas to inspect, but not casually modify:

- `ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/`
- `ragenius_app_skeleton/backend/.state/runtime_state.db`
- Any existing app-skeleton compiler or understanding persistence module.

## Adapter Boundary

The Builder should use an adapter boundary for loading compiled instruction models.

Recommended interface:

```text
get_latest_instruction_model(app_id) -> InstructionModelSnapshot
```

Recommended snapshot fields:

- `app_id`
- `source_kind`
- `source_path` or `source_record_id`
- `loaded_at`
- `compiled_at`
- `status`
- `freshness`
- `payload`
- `errors`

The first adapter may read app-skeleton snapshot files. That should be treated as a compatibility adapter, not as the permanent Builder storage contract.

Longer term, Builder should depend on a shared compiler/read API or a shared repository layer that returns the exact compiled artifact shape.

## Acceptance Criteria

The design is satisfied when:

- A designer can edit application instructions and separately inspect the runtime-compiled model.
- The Runtime Model view is derived from the exact `understanding.json` shape or equivalent compiled runtime payload.
- The UI makes compile status and freshness visible.
- The UI presents workflows, procedures, resources, policies, and validation in a readable order.
- The UI preserves raw JSON access.
- The UI does not silently compile or mutate runtime state on page load.
- The UI never presents Builder Markdown parsing as the runtime model.

## Risks

- The current `.state` directory is runtime/generated state, not a stable long-term Builder API.
- App IDs in Builder and app-skeleton snapshots may not always align without an explicit mapping.
- Large instruction models can make a single expanded page hard to use.
- Friendly summaries can accidentally change meaning if they omit exact runtime fields.
- Stale compiled models can mislead designers if freshness is not visually prominent.

## Open Questions

- Should the first adapter read snapshot files, `runtime_state.db`, or both?
- What is the authoritative app ID mapping between Builder apps and app-skeleton compiled snapshots?
- Is there already a shared compile function that Builder can call later, or should that be exposed as a new app-skeleton API?
- Which runtime model field marks `instruction_runtime_model` versus `hybrid_instruction_runtime_model` as active?
- Should compiled model history be shown in Builder after the read-only MVP?
