# Phase 1 Design: Safe Tool Contracts And Builder Normalization

## Purpose

This spec defines the first production-oriented phase for Builder-authored, execution-ready skills in RAGenius.

The goal is to let users upload natural `SKILL.md` files for safe app administration and content workflows, while keeping runtime execution explicit, policy-controlled, and reusable.

Phase 1 does **not** attempt arbitrary local automation. It focuses on:

- Builder-side normalization from natural skills to explicit contracts
- a small safe core tool registry
- execution-subsystem support for read-safe and artifact-safe tools
- deterministic publish behavior through auto-finalization rules

## Problem Statement

The current system can execute explicit published contracts, but authoring remains too implementation-aware:

- natural `SKILL.md` files are descriptive, not directly executable
- execution requires explicit machine-readable contracts
- runtime capability is concentrated in one-off providers instead of reusable primitives

This leads to two gaps:

1. poor authoring UX, because users should not have to hand-write runtime metadata for ordinary safe skills
2. weak generalization, because each new skill tends to imply custom runtime code

Phase 1 addresses both by introducing a normalization pipeline in Builder and a reusable safe core tool layer in `ragenius_execution_subsystem`.

## Goals

- Allow natural `SKILL.md` uploads for safe admin/content workflows
- Infer draft execution contracts in Builder
- Auto-finalize high-confidence safe-read skills
- Publish only explicit finalized contracts to `ragenius_execution_subsystem`
- Execute those contracts using a reusable safe tool set
- Preserve app isolation and `rag_subsystem` ownership boundaries

## Non-Goals

- No arbitrary shell execution
- No arbitrary Python execution
- No MCP-based filesystem/browser integration in Phase 1
- No broad write-capable local automation
- No replacement of explicit runtime contracts with freeform runtime inference

## Architectural Position

Builder remains the authoring and contract-normalization control plane.

`ragenius_execution_subsystem` remains the runtime executor.

`rag_subsystem` remains the only home for retrieval/indexing logic.

The runtime must never infer execution plans from freeform skill prose at request time. All inference happens in Builder before publish. Runtime executes only finalized explicit contracts.

## Phase 1 Tool Registry

Phase 1 introduces six safe core tools.

### `read_file`

Purpose:
- Read a single text file from an allowed root

Inputs:
- `path: string`
- `encoding?: string`
- `max_bytes?: integer`

Outputs:
- `path: string`
- `content: string`
- `truncated: boolean`
- `size_bytes: integer`

Policy:
- allowed roots only
- text-oriented formats only in Phase 1
- bounded file size
- no write behavior

### `list_files`

Purpose:
- Enumerate files and directories under an allowed root

Inputs:
- `path: string`
- `recursive?: boolean`
- `depth?: integer`
- `glob?: string`
- `include_dirs?: boolean`

Outputs:
- `path: string`
- `entries: array`
  - `path: string`
  - `name: string`
  - `type: "file" | "directory"`
  - `size_bytes?: integer`
  - `modified_at?: string`

Policy:
- allowed roots only
- bounded recursion depth
- bounded result count

### `retrieve_documents`

Purpose:
- Retrieve app-scoped knowledge results via `rag_subsystem`

Inputs:
- `query: string`
- `top_k?: integer`
- `filters?: object`

Outputs:
- `items: array`
  - retrieval result shape owned by `rag_subsystem`

Policy:
- always `app_id` scoped
- must call retrieval through `rag_subsystem`
- no duplicated retrieval logic in execution subsystem

### `search_metadata`

Purpose:
- Query document/app metadata without document full-content retrieval

Inputs:
- `query: string`
- `filters?: object`
- `limit?: integer`

Outputs:
- `items: array`
  - metadata rows only

Policy:
- app scoped
- metadata only
- no raw document content unless another tool is used

### `save_artifact`

Purpose:
- Persist generated outputs for later steps, UI retrieval, or operator inspection

Inputs:
- `artifact_type: string`
- `name: string`
- `content: object | string`
- `format?: string`

Outputs:
- `artifact_id: string`
- `path: string`
- `artifact_type: string`

Policy:
- app-scoped artifact storage only
- no arbitrary destination paths

### `load_artifact`

Purpose:
- Load previously saved artifacts

Inputs:
- `artifact_id: string`

Outputs:
- artifact content and metadata

Policy:
- app scoped
- artifact store only

## Policy Model

Phase 1 policy is deliberately narrow.

### Allowed Root Policy

Filesystem tools operate only within configured allowed roots. These roots must be explicit runtime configuration, not inferred from user input.

### App Scope Policy

Knowledge and artifact tools are always scoped by `app_id`. Cross-app lookup is forbidden.

### Read-Safe Classification

Phase 1 tools are either:

- read-only
- artifact-safe

No tool in Phase 1 may mutate arbitrary local files.

### Bounded Execution Policy

All tools must enforce:

- max bytes or result counts
- timeout limits
- schema validation on input/output

## Builder Normalization Pipeline

Builder gains a new normalization pipeline between upload and publish.

### Step 1: Parse Natural Skill

Builder parses uploaded `SKILL.md` into an internal `SkillIntentDraft`.

Extract:
- `name`
- `description`
- section headings
- ordered workflow bullets/steps
- declared inputs
- output expectations
- references to commands, paths, or external systems

### Step 2: Intent Classification

Builder classifies the skill into a supported template family.

Phase 1 template families:
- file inspection/report
- retrieval/report
- metadata search/report
- artifact transform/report

If no supported family matches, the skill remains descriptive-only and is not auto-finalizable.

### Step 3: Tool Candidate Resolution

Builder matches the classified intent against the safe core tool registry.

Output:
- candidate tool ids
- confidence score
- policy class

Policy classes:
- `safe_read`
- `review_required`
- `unsupported`

### Step 4: Draft Schema Synthesis

Builder synthesizes:
- draft input schema
- draft output schema

Sources:
- explicit "Inputs" sections
- parameter placeholders in workflow prose
- output contract prose

### Step 5: Draft Workflow Synthesis

Builder maps the intent family to a known workflow template.

Examples:

#### Retrieval Report

- `retrieve_documents`
- optional `save_artifact`
- `end`

#### File Inspection Report

- `list_files` or `read_file`
- optional `save_artifact`
- `end`

#### Metadata Search Report

- `search_metadata`
- optional `save_artifact`
- `end`

### Step 6: Contract Validation

Builder validates the generated draft contract:

- all tool ids exist in runtime registry
- schemas are structurally complete
- workflow uses supported step types only
- permissions align with policy class

### Step 7: Finalization Decision

Builder applies auto-finalization rules.

Outcomes:
- auto-finalized explicit contract
- review-required draft
- descriptive-only unsupported skill

## Auto-Finalization Rules

Auto-finalization is permitted only when all of the following are true:

- all inferred tools are in the Phase 1 safe core set
- workflow matches a supported template
- confidence is high
- no mutation semantics are implied
- no shell, Python, browser, MCP, or arbitrary external command execution is implied
- target resources can be safely scoped

### Review Required If

Any of the following makes the skill review-required:

- write-capable semantics are implied
- workflow has multiple plausible interpretations
- required inputs are underspecified
- output contract is ambiguous
- skill references scripts, commands, or local executables
- filesystem target semantics are unclear

### Unsupported If

Any of the following makes the skill unsupported for executable publish:

- arbitrary shell execution required
- arbitrary Python execution required
- missing runtime tool/provider
- conflict with app isolation rules
- requires capabilities outside supported template families

## Contract Shape Published To Runtime

Phase 1 finalized contracts must include explicit:

- `id`
- `version`
- `required_tools`
- `required_permissions`
- `workflow_ref`
- `input_schema_ref`
- `output_schema_ref`

The runtime never executes a draft. It executes only finalized explicit contracts.

## Runtime Execution Requirements

`ragenius_execution_subsystem` must support these additional behaviors for Phase 1:

- safe core tool definitions in tool registry
- provider implementations for Phase 1 tools
- policy enforcement for allowed roots and app scope
- persisted execution records and artifacts
- explicit rejection for unsupported tool references

No Phase 1 runtime path may silently infer a missing workflow or tool call from prose.

## Example Supported Skills

### Example 1: File Inventory Report

Natural skill intent:
- inspect a workspace path
- summarize contents
- save the report as an artifact

Likely finalized contract:
- `required_tools = [list_files, save_artifact]`
- workflow:
  - `tool_call(list_files)`
  - `tool_call(save_artifact)`
  - `end`

### Example 2: Retrieval Summary Report

Natural skill intent:
- retrieve relevant app documents
- produce a structured summary
- save the summary artifact

Likely finalized contract:
- `required_tools = [retrieve_documents, save_artifact]`
- workflow:
  - `tool_call(retrieve_documents)`
  - `tool_call(save_artifact)`
  - `end`

## Phase 1 Acceptance Criteria

Builder:
- can ingest a natural `SKILL.md`
- can produce a draft normalized contract
- can auto-finalize a safe supported skill with no manual runtime metadata authoring
- can mark ambiguous or unsafe skills as review-required or unsupported

Execution subsystem:
- supports the Phase 1 safe core tools
- enforces allowed roots, app scope, and bounded execution
- can execute finalized contracts using only supported step types
- persists execution record and artifact outputs

System:
- at least two end-to-end Phase 1 sample skills execute successfully
- no retrieval logic is duplicated outside `rag_subsystem`
- no cross-app leakage is possible through knowledge or artifact tools

## Implementation Notes

Phase 1 should prefer:

- small explicit tool contracts
- template-driven workflow synthesis
- deterministic publish outcomes
- review-required fallback rather than unsafe inference

Phase 1 should avoid:

- premature generic agent execution
- arbitrary local process execution
- runtime-time interpretation of prose skill bodies

## Open Questions Deferred To Later Phases

- mutation-capable tool rollout (`write_file`, `patch_file`)
- MCP-backed execution tools
- controlled shell adapters
- richer workflow semantics beyond current bounded templates
- Builder review UI for contract editing

## Recommendation

Implement Phase 1 in this order:

1. define the safe core tool contracts
2. add Builder normalization data model and pipeline
3. add workflow template library for supported families
4. implement auto-finalization policy evaluation
5. implement Phase 1 runtime providers and policy enforcement
6. validate with two end-to-end sample skills
