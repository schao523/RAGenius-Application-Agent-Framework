# Phase 3 Design: MCP-Backed Tools And Controlled Adapter Execution

## Purpose

This spec defines Phase 3 of the Builder-authored skill runtime for RAGenius.

Phase 1 established safe read/artifact tools and Builder normalization for simple contracts.

Phase 2 added bounded local mutation tools with review-required contracts and runtime confirmation.

Phase 3 extends the system toward reusable integration-backed workflows without breaking the same architectural boundaries:

- `ragenius_builder` remains the authoring and contract-normalization control plane
- `ragenius_execution_subsystem` remains the only runtime executor
- `rag_subsystem` remains the only owner of retrieval/indexing logic

The focus of Phase 3 is not arbitrary agent execution. It is controlled expansion into:

- real MCP-backed tool use
- approved adapter execution instead of arbitrary shell
- slightly richer workflow composition for multi-step admin/content workflows

## Problem Statement

After Phase 2, the system can:

- inspect files
- retrieve/search metadata
- persist artifacts
- apply bounded file updates
- gate mutation behind review and confirmation

But it still lacks a practical integration model for broader workflows such as:

- controlled browser/content-platform operations through MCP
- invoking trusted utility adapters that are not worth hardcoding as local providers
- composing more than simple linear or one-branch workflows

Current gaps:

- MCP is discovery-only and mock-backed
- there is no runtime invocation path for real MCP tools
- there is no approved adapter model between “built-in local tool” and “arbitrary shell”
- workflow semantics are still narrow: `validation`, `local_decision`, `tool_call`, `end`

## Goals

- Add real MCP-backed tool execution to `ragenius_execution_subsystem`
- Add controlled adapter execution for approved commands only
- Preserve Builder-authored explicit contracts and runtime policy enforcement
- Expand workflow composition modestly with one additional safe step family
- Keep all new execution paths reviewable, scoped, and auditable

## Non-Goals

- No arbitrary shell execution
- No arbitrary Python execution
- No general-purpose terminal agent
- No freeform remote code execution over MCP
- No runtime inference from natural language
- No duplication of retrieval logic outside `rag_subsystem`

## Architectural Position

Phase 3 introduces two new runtime capability classes.

### 1. MCP-backed tools

These are dynamic tools surfaced by configured MCP providers, but they are still normalized into explicit runtime contracts before execution.

### 2. Approved adapter tools

These are fixed, allowlisted command-backed tools exposed through the tool registry as named capabilities, not raw command execution.

Example:

- acceptable: `site_build_adapter`
- not acceptable: arbitrary user-specified `run_shell`

The execution subsystem must remain capability-oriented, not command-oriented.

## Capability Model

Phase 3 adds two new provider patterns.

### MCP Provider Pattern

The runtime already has:

- `MCP_SERVERS_JSON`
- `MockMcpToolProvider`
- `POST /v1/tools/discover/mcp`

Phase 3 upgrades that into real runtime use:

- provider discovery stays explicit
- discovered tools are registered into the tool registry
- runtime can invoke those discovered tools
- permission scope, side-effecting metadata, and provider identity remain explicit

### Adapter Provider Pattern

The adapter provider is a new provider type for approved local executables.

It should not accept arbitrary user commands. It should expose only named adapters with static command templates and validated inputs.

Example candidates:

- `site_build_adapter`
- `markdown_lint_adapter`
- `content_transform_adapter`

Each adapter tool contract must define:

- fixed executable
- fixed argument template
- input schema
- output schema
- timeout
- permission scopes

## Phase 3 Tool Classes

### Real MCP Tools

Examples:

- `mcp.<provider>.search_pages`
- `mcp.<provider>.create_page`
- `mcp.<provider>.list_records`

Requirements:

- explicit tool registration after discovery
- provider-scoped ids
- runtime invocation support
- explicit permission scopes

### Approved Adapter Tools

Examples:

- `site_build_adapter`
- `content_transform_adapter`

Requirements:

- no raw command text in skill contracts
- fixed allowlisted executable and args pattern
- explicit structured input/output
- runtime confirmation for side-effecting adapters

## Policy Model

Phase 3 adds policy by capability class, not by raw execution primitive.

### MCP Policy

- only configured MCP providers may be used
- discovered tool ids must include provider identity
- side-effecting MCP tools are review-required and confirmation-gated
- unavailable/unconfigured providers must fail closed

### Adapter Policy

- only allowlisted adapters may execute
- adapters may not accept arbitrary executable paths or arbitrary argument strings
- adapters must run only within configured allowed roots or app-scoped work directories where applicable
- side-effecting adapters are review-required and confirmation-gated

### Builder Policy

Builder may infer MCP-backed or adapter-backed draft contracts, but they are never auto-finalized in Phase 3.

Phase 3 contracts are at minimum:

- `review_required`

and may be:

- `unsupported`

if the target provider or adapter is unavailable.

## Builder Inference Rules

Phase 3 extends normalization but remains template-driven.

Supported new template families:

- `mcp_read_operation`
- `mcp_write_operation`
- `adapter_transform`
- `adapter_build`

Rules:

- read-like MCP flows may infer candidate tools when provider identity is clear
- write-like MCP flows always require review
- adapter-backed contracts always require review
- Builder must validate that the referenced adapter/tool id exists in the runtime registry contract

Builder does not invent arbitrary MCP operations from prose. It selects from known discovered tool ids or known adapter ids.

## Workflow Expansion

Phase 3 adds one additional workflow step family:

### `service_call`

Purpose:

- call a named internal service boundary with structured input/output

This is intended for:

- MCP invocation wrapper steps
- approved adapter invocation wrappers

It should not be a general HTTP client step.

Scope:

- named internal runtime service only
- explicit schema validation
- no arbitrary URLs

Why this is useful:

- keeps MCP/adapter orchestration explicit
- avoids overloading every integration path into local provider branching
- opens the door to cleaner workflow composition without making workflows unbounded

## MCP Runtime Requirements

Phase 3 MCP runtime must support:

- provider discovery from runtime config
- tool registration from discovery
- invocation of a discovered tool by provider-scoped tool id
- propagation of auth token config
- structured success/failure output

Minimum requirement:

- one real MCP provider path must work end to end

The current `MockMcpToolProvider` should become the seam for a real provider implementation rather than a final design.

## Adapter Runtime Requirements

Phase 3 adapter runtime must support:

- adapter registry in config or code
- fixed executable/arg template mapping
- structured stdout/stderr parsing or wrapper output
- timeout handling
- explicit failure classification

It must not support:

- arbitrary user-supplied commands
- arbitrary user-supplied arguments beyond validated structured input

## Persistence And Observability

Phase 3 uses the existing execution persistence model but must capture additional integration details:

- provider id for MCP executions
- adapter id for adapter executions
- confirmation state
- execution status and summary logs

Detailed step-event persistence is still not required for Phase 3 completion, but the summary records must make integration execution understandable.

## Configuration Requirements

Phase 3 adds two configuration families.

### MCP

Continue using:

- `MCP_SERVERS_JSON`

but extend runtime behavior from discovery-only to execution-capable.

### Adapters

Add a dedicated adapter config source such as:

- `ADAPTERS_JSON`

or a code-backed registry if kept intentionally small.

The config must describe:

- adapter id
- executable
- fixed args template
- allowed roots/workdir policy
- timeout
- enabled flag

## Acceptance Criteria

Phase 3 is complete when:

- runtime can discover and invoke at least one real MCP-backed tool
- discovered MCP tools are explicitly registered and permission-scoped
- runtime can invoke at least one approved adapter tool without exposing arbitrary shell
- Builder can normalize supported MCP/adapter skill drafts into explicit review-required contracts
- side-effecting MCP/adapter flows require review and runtime confirmation
- workflow composition supports the additional `service_call` path safely
- tests cover:
  - MCP discovery and invocation
  - disabled/unconfigured MCP provider failure
  - approved adapter success
  - non-allowlisted adapter rejection
  - pending-confirmation for side-effecting Phase 3 contracts
  - confirmed execution path

## Recommended Implementation Order

1. Replace MCP discovery-only mock behavior with an invocation-capable provider seam
2. Add the approved adapter provider and registry
3. Extend Builder normalization for MCP/adapter review-required draft contracts
4. Add `service_call` workflow support for named internal integration execution
5. Add end-to-end tests and docs
