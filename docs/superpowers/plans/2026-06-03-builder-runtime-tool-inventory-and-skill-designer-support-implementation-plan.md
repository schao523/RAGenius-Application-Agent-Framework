# Builder Runtime Tool Inventory And Skill-Designer Support Implementation Plan

## Objective

Implement Builder and execution-subsystem enhancements so skill designers can understand:

- what integrations are available
- what tools are exposed
- what author aliases map to those tools
- which families Builder can infer automatically
- what sample input/output contracts Builder will generate

## Scope

This plan covers:

- runtime endpoints for integration and tool inventory
- Builder subsystem UI expansion beyond MCP-only status
- Builder skill-authoring coverage models
- skill test/review explanation surfaces

This plan does not include:

- `ragenius_app` end-user UI
- a full workflow editor
- long-term async execution lifecycle work

## Current Baseline

Already available:

- MCP provider status in Builder subsystem UI
- recent execution diagnostics and fallback summaries
- Builder normalization maps and family policy metadata
- runtime tool registry with provider-family metadata
- NotebookLM adapter-backed tools

Missing:

- non-MCP integration inventory
- runtime-wide tool inventory endpoint
- skill-designer-facing coverage matrix
- test-input explanation UI

## Workstreams

## Workstream 1: Runtime Integration Inventory

### Goal

Expose configured runtime integrations across all families, not just MCP.

### Changes

Add a runtime view model and endpoint:

- endpoint: `GET /v1/runtime/integrations`

Implementation areas:

- [app.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/app.ts:1)
- [health.routes.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/health.routes.ts:1) or a new `runtime.routes.ts`
- runtime config inspection helpers

### Response Shape

Return:

- `integrations`
  - `id`
  - `family`
  - `configured`
  - `enabled`
  - `auth_configured`
  - `tool_ids`
  - `health`
  - integration-specific metadata

Families:

- `mcp`
- `adapter`
- `api`
- `local`
- `rag_adapter`

### NotebookLM Requirements

Include:

- `allowed_operations`
- `bridge_script_configured`
- `auth_mode`
- `profile` or storage-path presence redacted appropriately

## Workstream 2: Runtime Tool Inventory

### Goal

Expose a normalized inventory of all registered tools across provider families.

### Changes

Add endpoint:

- `GET /v1/tools/inventory`

Implementation areas:

- [tool-registry.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/tool-registry.ts:1)
- [tools.routes.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/tools.routes.ts:1)

### Response Shape

Each item:

- `tool_id`
- `name`
- `family`
- `provider_id`
- `enabled`
- `side_effecting`
- `permission_scopes`
- `timeout_ms`
- `policy_class`
- `fallback_capable`
- `normalization_supported`

### Notes

`normalization_supported` should not be computed in runtime unless there is already a shared source of truth. If not, Builder can enrich this field after reading runtime tool inventory.

## Workstream 3: Builder Integration Inventory UI

### Goal

Replace MCP-only framing with a broader integration inventory.

### Changes

Update subsystem page:

- [subsystem_settings.html](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/templates/subsystem_settings.html:1)
- [app.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/app.py:1)
- [execution_client.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/execution_client.py:1)

### UI Changes

- rename `MCP Runtime Status` section to `Runtime Integration Inventory`
- split into:
  - integration overview
  - MCP integrations
  - adapter/API/local integrations

### Display Requirements

Surface NotebookLM explicitly as:

- integration id
- family `adapter`
- configured/enabled
- exposed tool count and tool ids

## Workstream 4: Builder Runtime Tool Inventory UI

### Goal

Give skill designers a searchable view of actual runtime tools.

### Changes

Add a new subsystem section:

- `Runtime Tool Inventory`

Show:

- tool id
- family
- provider/integration id
- enabled
- policy class
- side-effecting
- timeout
- fallback-capable

### Phase 1 Filtering

Simple filters:

- family
- provider/integration
- write-capable only

Server-side query params are acceptable for phase 1.

## Workstream 5: Builder Skill Authoring Coverage Model

### Goal

Show whether Builder can infer a contract automatically for a given alias/tool family.

### Changes

Create a Builder-side view model derived from:

- `AUTHOR_TOOL_ALIAS_MAP`
- normalization family mappings in [skill_normalization.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/skill_normalization.py:1)
- family policy metadata in [policy.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/policy.py:1)

### Output

For each alias:

- alias
- resolved tool(s)
- inferred family
- support level
  - `full_family_inference`
  - `partial_inference`
  - `explicit_schema_recommended`
  - `unsupported`
- default policy class
- notes

### UI

New subsystem section:

- `Skill Authoring Coverage`

This is the primary skill-designer-facing table.

## Workstream 6: Skill Test / Review Contract Explanation

### Goal

Explain why Builder generated a given sample input and contract.

### Changes

Extend the skill detail/test page to show:

- inferred family
- contract source
  - explicit schema
  - family default inference
  - mixed
- sample input source explanation

### Example NotebookLM Explanation

- `instructions`: required field
- `notebookTitle`: chosen from conditional `anyOf` notebook reference
- `language`: default
- `waitForCompletion`: default
- `persistArtifacts`: default

### Implementation Areas

- [app.py](D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/app.py:1)
- skill detail/test template(s)
- possibly helper functions adjacent to `_default_skill_test_input`

## Workstream 7: Supported-Family Contract Preview

### Goal

Show the inferred runtime contract before publish.

### Changes

Add read-only preview blocks to skill detail:

- input schema
- output schema
- workflow summary
- permissions
- policy class

Most of this data already exists in normalized metadata. The work is mainly presentation.

## Sequence

### Slice 1

Runtime inventory foundations:

1. add `GET /v1/runtime/integrations`
2. add `GET /v1/tools/inventory`
3. test runtime endpoint output

### Slice 2

Builder subsystem expansion:

1. integrate new runtime endpoints in `execution_client.py`
2. expand `subsystem_settings.html`
3. add Runtime Tool Inventory
4. add Skill Authoring Coverage

### Slice 3

Skill designer explanation surfaces:

1. add contract explanation model in Builder
2. show explanation on skill detail/test page
3. add supported-family contract preview

### Slice 4

Polish and diagnostics:

1. add filters/search
2. add better labels for unsupported cases
3. add regression tests for NotebookLM visibility and authoring coverage

## Testing Strategy

### Runtime Tests

- endpoint schema tests for integration inventory
- endpoint schema tests for tool inventory
- NotebookLM integration visibility tests
- mixed-family inventory tests

### Builder Tests

- subsystem view model tests
- coverage matrix tests
- skill detail/test explanation tests
- NotebookLM alias coverage tests

## Acceptance Criteria

- Builder subsystem page shows NotebookLM without requiring MCP knowledge.
- Builder subsystem page shows tools beyond MCP.
- Skill designers can see if `required_tools` alone is enough for a known family.
- Skill detail/test page explains generated input JSON fields.
- Unsupported/custom-tool skill authoring cases are labeled clearly.

## Risks

- duplicated support logic between runtime and Builder
- confusing labels if support levels are too optimistic
- inventory pages becoming too operator-focused again

## Mitigations

- derive support labels from Builder normalization maps
- use conservative wording
- keep a dedicated skill-designer section separate from raw runtime diagnostics

## Recommended Next Slice

Start with Slice 1 and Slice 2 together:

1. runtime integration inventory
2. runtime tool inventory
3. Builder subsystem UI expansion
4. skill authoring coverage matrix

That yields the highest immediate value for skill designers while keeping the implementation bounded.
