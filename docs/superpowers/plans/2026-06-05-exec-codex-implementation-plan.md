# `@exec codex` Implementation Plan

Date: 2026-06-05

Related contract:
- [2026-06-05-exec-codex-contract.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-05-exec-codex-contract.md:1)

## Objective

Implement a first-class agent execution mode in RAGenius:

- user-facing textual form:
  - `@exec codex "<natural language request>"`
  - `@exec codex use <skill> "<natural language request>"`
- UI-facing mode:
  - `Agent`
- backend:
  - `codex_cli`

This mode should let RAGenius run natural-language agent tasks in application context while reusing Codex CLI installed skills from `.agents/skills`, such as `notebooklm`.

## Scope

In scope:
- `ragenius_execution_subsystem`
- `ragenius_app_skeleton`
- optional Builder/runtime metadata support only where it improves presentation or policy

Out of scope for the first implementation:
- full Builder authoring UI for Codex-backed skills
- arbitrary unrestricted Codex shell delegation
- destructive agent actions
- generalized long-running background orchestration beyond the existing execution lane model

## Non-Negotiable Constraints

1. App isolation must be preserved
- all executions remain app-scoped and session-scoped
- no cross-app artifact or context leakage

2. `@exec codex` must not bypass execution governance
- approval policy
- audit trail
- result persistence
- lane-state updates

3. Codex runtime must not be exposed as a raw unrestricted shell
- RAGenius submits a constrained execution envelope
- policy and workspace boundaries remain explicit

4. Existing `@exec tool`, `@exec skill`, and normal chat behavior must remain backward compatible

## Target End State

### User-facing

Supported execution modes:
- `Tool`
- `Skill`
- `Agent`

`Agent` mode supports:
- natural-language request
- optional skill hint
- app/session/approved-content-aware execution
- compact transcript summary
- side-panel inspection of structured result/provenance

### Execution model

- `@exec tool` = deterministic runtime tool execution
- `@exec skill` = Builder-bound app skill execution
- `@exec codex` = Codex-backed natural-language agent execution

### Backend model

- `codex_cli` becomes a new execution backend/provider family in `ragenius_execution_subsystem`

## Phase Breakdown

## Phase 1: Core Execution Contract

Goal:
- add first-class `execute_agent` support without UI work yet

### `ragenius_execution_subsystem`

Tasks:
1. Add `execute_agent` request type to execution request schema
2. Add `codex_cli` backend/provider contract types
3. Add normalized `AgentExecutionResult` result model
4. Extend execution persistence to store:
   - backend = `codex_cli`
   - agent query
   - optional skill hint
   - normalized provenance
5. Add execution-engine dispatch for:
   - `execute_skill`
   - `execute_agent`

Files likely affected:
- [ragenius_execution_subsystem/src/core/execution/execution-engine.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/execution/execution-engine.ts:1)
- [ragenius_execution_subsystem/src/api/routes/executions.routes.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/executions.routes.ts:1)
- request schema file(s) used by execution routes
- execution store types / persistence layer

### `ragenius_app_skeleton`

Tasks:
1. Extend `exec_router.py` to parse:
   - `@exec codex "<request>"`
   - `@exec codex use <skill> "<request>"`
2. Add normalized app-side execution-intent builder for agent mode
3. Add backend client call:
   - `submit_agent(...)`
4. Persist execution-lane state for agent requests in the same structure used by other `@exec` flows

Files likely affected:
- [ragenius_app_skeleton/backend/app/exec_router.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/exec_router.py:1)
- [ragenius_app_skeleton/backend/app/main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)
- [ragenius_app_skeleton/backend/app/execution_subsystem_client.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/execution_subsystem_client.py:1)
- optional app-side intent/policy helpers

### Tests

Add:
- parser tests for `@exec codex`
- backend route tests for `execute_agent`
- app routing tests that prove:
  - normal chat is unaffected
  - `@exec codex` enters execution lane
  - skill hint form is parsed correctly

Exit criteria:
- text command path works end to end through the app and execution subsystem
- no UI yet required

## Phase 2: Codex Runtime Adapter

Goal:
- actually invoke Codex in a constrained way

### `ragenius_execution_subsystem`

Tasks:
1. Implement `codex_cli` adapter/provider
2. Build a constrained invocation envelope containing:
   - app id
   - session id
   - approved content context
   - policy constraints
   - optional skill hint
   - natural-language request
3. Capture:
   - final message
   - activated skills
   - tool summary
   - artifacts
   - raw output / error
4. Normalize into `AgentExecutionResult`

Design requirement:
- do not invoke Codex as unrestricted arbitrary shell text
- always construct a structured execution input

Files likely added:
- `src/core/agents/codex-cli-provider.ts` or equivalent
- backend-specific type definitions for agent execution

Operational assumptions:
- Codex runtime can see installed skills in:
  - `~/.agents/skills`

Open decision:
- whether Codex invocation is:
  - direct local CLI
  - local wrapper script
  - dedicated service shim

Recommendation:
- start with a local wrapper/shim boundary if needed for safer structured I/O

### Tests

Add:
- adapter unit tests with mocked Codex responses
- error mapping tests
- provenance/result normalization tests

Exit criteria:
- `execute_agent` returns structured results from mocked Codex runtime
- errors do not leak as plain internal failures

## Phase 3: Policy and Approval

Goal:
- make `@exec codex` safe enough for real use

### Policy model

Implement classes:
- `agent_read_only`
- `agent_external_write`
- `agent_workspace_write`
- `agent_destructive`

Tasks:
1. Add agent risk classification
2. Add approval gating rules
3. Add workspace access policy:
   - none
   - read_only
   - scoped_write
4. Add network policy:
   - deny
   - allowlisted
5. Block or admin-gate destructive agent requests

### `ragenius_app_skeleton`

Tasks:
1. Present approval-needed responses clearly in transcript
2. Preserve retryable last-agent request in lane state
3. Surface login/auth or environment repair needs similarly to current NotebookLM login requirement behavior where applicable

### Tests

Add:
- approval-required agent request tests
- blocked destructive request tests
- workspace policy enforcement tests

Exit criteria:
- agent runs respect policy
- unsafe operations do not silently proceed

## Phase 4: Agent Mode in Execution Composer

Goal:
- make `Agent` a first-class UI mode

### `ragenius_app_skeleton` frontend

Tasks:
1. Add `Agent` mode to [ExecutionComposer.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx:1)
2. Fields:
   - request text
   - optional skill hint
   - execution mode
   - approval/risk badge
   - selected approved revision summary
3. Build the same internal execution payload used by textual `@exec codex`
4. Keep side panel for inspection after submission

### UX details

Recommended labels:
- Mode: `Agent`
- Skill hint: `Auto` / explicit installed skill names when available

Recommended transcript summaries:
- `Codex agent completed the NotebookLM task.`
- `Codex agent requires confirmation before generating a video.`

Tests:
- composer mode switching
- payload generation
- conditional skill-hint behavior

Exit criteria:
- no raw command syntax required for agent mode in UI

## Phase 5: Result Presentation and Inspector Support

Goal:
- make agent runs understandable to users

### Transcript

Tasks:
1. Add compact inline previews for agent runs:
   - activated skills
   - result summary
   - artifact count

### Inspector

Tasks:
1. Add Codex-agent-specific execution inspector sections:
   - Summary
   - Request
   - Activated Skills
   - Tool Summary
   - Artifacts
   - Raw

Files likely affected:
- [ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx:1)
- [ragenius_app_skeleton/frontend/src/App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)
- [ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)

Exit criteria:
- successful and failed agent runs are inspectable without reading raw JSON only

## Phase 6: Optional Builder Metadata Support

Goal:
- improve app-level configuration without making Builder mandatory for agent mode

Optional metadata additions:
- agent-capable skill hint definitions
- app-level allowlist of Codex skill hints
- default policy class for agent executions
- app-level workspace roots for agent mode

This phase is optional because:
- `@exec codex` can work before Builder owns agent configuration
- Builder support is enhancement, not a prerequisite

## Recommended Delivery Order

1. Phase 1: core request/route plumbing
2. Phase 2: Codex runtime adapter
3. Phase 3: policy and approval
4. Phase 4: Agent mode in composer
5. Phase 5: agent result presentation
6. Phase 6: optional Builder metadata

## Concrete File-Level Plan

### `ragenius_execution_subsystem`

Expected changes:
- add `execute_agent` request schema
- add `codex_cli` backend/provider
- extend execution engine dispatch
- extend execution persistence and result normalization
- add tests for:
  - parsing
  - adapter behavior
  - approval
  - normalized results

Likely files:
- [src/api/routes/executions.routes.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/executions.routes.ts:1)
- [src/core/execution/execution-engine.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/execution/execution-engine.ts:1)
- execution request/result schema files
- execution store / Prisma persistence files
- new `codex_cli` provider/adapter file(s)

### `ragenius_app_skeleton` backend

Expected changes:
- parse `@exec codex`
- build agent execution requests
- submit to execution subsystem
- persist lane state
- summarize approval and result states

Likely files:
- [backend/app/exec_router.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/exec_router.py:1)
- [backend/app/main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)
- [backend/app/execution_subsystem_client.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/execution_subsystem_client.py:1)

### `ragenius_app_skeleton` frontend

Expected changes:
- `Agent` mode in composer
- transcript summary for agent runs
- agent-specific inspector sections

Likely files:
- [frontend/src/components/ExecutionComposer.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx:1)
- [frontend/src/App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)
- [frontend/src/components/ExecutionInspector.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)
- [frontend/src/components/ChatMessageCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)

## Risks

1. Codex runtime invocation boundary is underspecified
- mitigation:
  - isolate behind a dedicated adapter
  - start with mocked/testable structured responses

2. Agent mode can become a policy bypass
- mitigation:
  - explicit approval classes
  - no unrestricted shell passthrough

3. Result normalization may become too provider-specific
- mitigation:
  - require a stable normalized result envelope
  - keep raw data available in provenance/raw fields

4. Overlap with `@exec skill`
- mitigation:
  - keep `@exec skill` Builder-bound
  - keep `@exec codex` clearly presented as agent mode

## Verification Checklist

Before calling the feature complete:

1. Text command path
- `@exec codex "..."` works
- `@exec codex use notebooklm "..."` works

2. Policy path
- read-only agent task auto-allows
- write-capable agent task requires confirmation
- destructive task is blocked

3. UI path
- composer `Agent` mode works
- transcript summary appears
- inspector shows structured agent details

4. Result persistence
- execution id/status stored
- provenance stored
- artifacts linked if created

5. Backward compatibility
- `@exec tool` unchanged
- `@exec skill` unchanged
- normal non-`@exec` turns unchanged

## Recommendation

Implement Phase 1 through Phase 3 first before any Builder metadata work.

That gives:
- a usable text command path
- a real Codex backend boundary
- policy safety

Then add the `Agent` composer mode and richer UI once the backend contract is stable.
