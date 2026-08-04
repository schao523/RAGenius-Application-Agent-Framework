# Agent Mode Artifact Creation And Reuse Implementation Plan

## Purpose

This plan implements:

- `docs/agent-mode-artifact-creation-reuse-contract.md`
- `docs/agent-mode-artifact-creation-reuse-design.md`

The implementation spans:

- `ragenius_execution_subsystem`
- `ragenius_app_skeleton`

Builder and `rag_subsystem` are out of scope.

## Sequencing Rules

- Start in `ragenius_execution_subsystem`; app UX should not submit fields the execution subsystem cannot validate.
- Keep existing `@exec codex` and `@exec openclaw` behavior backward compatible.
- Do not expose provider-local paths in the app UI.
- Treat existing approved-content flow as compatibility plumbing, not the target user-facing reuse path.
- Add tests phase by phase; do not rely only on manual GUI checks.

## Phase 1: Execution Request Schema

### Goal

Make `execute_agent` accept structured artifact inputs and provider-neutral expected outputs.

### Files

- `ragenius_execution_subsystem/src/api/schemas/execution-request.schema.ts`
- `ragenius_execution_subsystem/src/core/agents/agent-provider.ts`
- `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`
- `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

### Changes

- Add `artifact_refs?: AgentArtifactRef[]`.
- Add `expected_outputs?: AgentExpectedOutput[]`.
- Validate `artifact_id`, `role`, and `reuse_mode`.
- Validate `output_id`, `required`, `persist_as_artifact`, `media_type`, and optional hash/size fields.
- Preserve existing request shape for agent calls without artifacts.

### Tests

- Accept Codex agent request without artifacts.
- Accept OpenClaw agent request without artifacts.
- Accept agent request with `artifact_refs`.
- Accept agent request with `expected_outputs`.
- Reject invalid reuse mode.
- Reject invalid expected output id.
- Reject raw path-like fields if accidentally included in refs.

### Acceptance

- Existing agent tests still pass.
- New schema tests prove request shape is supported.

## Phase 2: Agent Artifact Resolver

### Goal

Resolve session-scoped artifact refs into provider-usable internal payloads.

### Files

- `ragenius_execution_subsystem/src/core/agents/agent-artifact-resolver.ts`
- `ragenius_execution_subsystem/src/core/artifacts/*` or existing artifact store modules
- `ragenius_execution_subsystem/tests/agents/agent-artifact-resolver.test.ts`

### Changes

- Add resolver input:

```ts
{
  appId: string;
  sessionId: string;
  refs: AgentArtifactRef[];
  backend: "codex_cli" | "openclaw_cli";
}
```

- Enforce current `{app_id, session_id}` only.
- Validate artifact exists and is ready.
- Validate artifact is reusable.
- Validate requested reuse mode is supported.
- Validate backend supports the selected reuse mode.
- Return `ResolvedAgentArtifact[]`.
- Apply inline text size/truncation limits.
- Resolve server-side file path only after ownership validation.

### Tests

- Resolves session-owned text artifact.
- Rejects cross-session artifact.
- Rejects cross-app artifact.
- Rejects missing artifact.
- Rejects unsupported reuse mode.
- Truncates inline text and marks it as truncated.
- Does not read bytes for `metadata_only`.

### Acceptance

- Resolver never trusts frontend paths.
- Resolver returns deterministic payload shape for providers.

## Phase 3: Provider-Neutral Expected Output Planner

### Goal

Normalize desired reusable outputs before provider-specific handling.

### Files

- `ragenius_execution_subsystem/src/core/agents/agent-expected-output-planner.ts`
- `ragenius_execution_subsystem/src/core/agents/openclaw-options.ts`
- `ragenius_execution_subsystem/tests/agents/agent-expected-output-planner.test.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-options.test.ts`

### Changes

- Add `AgentExpectedOutputPlanner`.
- Normalize defaults:
  - `required` defaults to `false` unless generated because output is required.
  - `persist_as_artifact` defaults to `true` for required user-visible output.
  - `artifact_type` defaults to `agent_output`.
  - markdown output gets `text/markdown`.
- Move persistence decision out of `context.openclaw`.
- Keep `context.openclaw.execution_mode` as runtime hint only.
- For OpenClaw `output_required` with no expected output, create one markdown expected output.

### Tests

- Preserves explicit expected outputs.
- Generates default OpenClaw output when required.
- Does not generate output for read-only request.
- Does not place persistence flags in provider-specific context.

### Acceptance

- Provider-neutral outputs are normalized before OpenClaw path planning.

## Phase 4: OpenClaw Input Staging

### Goal

Stage resolved artifacts into OpenClaw workspace safely.

### Files

- `ragenius_execution_subsystem/src/core/agents/openclaw-workspace.ts`
- `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- `ragenius_execution_subsystem/src/core/agents/openclaw-prompt-builder.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`

### Changes

- Stage text artifacts as UTF-8 files under `inputs/`.
- Stage file-backed and binary artifacts with verified transfer.
- Verify staged file size and SHA-256.
- Support metadata-only artifacts through prompt context only.
- Add staged input paths to OpenClaw prompt.
- Prevent shell interpolation.

### Tests

- Stages text input and verifies hash.
- Stages binary input using safe chunk transfer.
- Rejects unsafe workspace-relative path.
- Prompt includes staged input path.
- Metadata-only input does not call binary staging.

### Acceptance

- OpenClaw receives only workspace-safe paths.
- Staged data is verified before provider invocation.

## Phase 5: OpenClaw Execution Result Semantics

### Goal

Correctly classify provider completion/failure before persistence.

### Files

- `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`

### Changes

- Treat non-zero OpenClaw exit code as `failed`.
- Preserve timeout failure behavior.
- Preserve required-output verification failure behavior.
- Keep stdout/stderr in diagnostics only.
- Return concise summary.

### Tests

- Non-zero exit code fails read-only run.
- Timeout fails run.
- Missing required output fails run.
- Optional output failure completes with diagnostics.

### Acceptance

- No failed OpenClaw process is reported as completed.

## Phase 6: Output Persistence

### Goal

Persist verified agent outputs into the RAGenius artifact store.

### Files

- `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- artifact store modules used by `save_artifact`
- `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`
- `ragenius_execution_subsystem/tests/agents/codex-cli-provider.test.ts` if present or new

### Changes

- Add artifact persistence dependency to agent providers or execution engine.
- Persist required verified outputs.
- Persist outputs with `persist_as_artifact = true`.
- Map persisted record:
  - `artifact_type = "agent_output"`
  - `provider_origin = agent_backend`
  - `created_by_execution_id = execution_id`
  - provenance and verification stored in metadata/content
- Return normalized artifact view in provider result.

### Failure Semantics

- Required output persistence failure makes execution `failed`.
- Optional output persistence failure remains `completed` with diagnostics.

### Tests

- Persists required OpenClaw output.
- Required persistence failure fails execution.
- Optional persistence failure records diagnostics only.
- Persisted artifact includes provider origin and execution provenance.

### Acceptance

- Verified OpenClaw output appears as a stable RAGenius artifact.

## Phase 7: App Backend Pass-Through

### Goal

Pass Agent-mode artifact refs and expected outputs from app backend to execution subsystem.

### Files

- `ragenius_app_skeleton/backend/app/main.py`
- `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- `ragenius_app_skeleton/backend/app/exec_router.py` if needed
- `ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`
- `ragenius_app_skeleton/backend/tests/test_exec_router.py`

### Changes

- Extend chat execution metadata or add a dedicated structured execution request path.
- Submit `artifact_refs` and `expected_outputs` to execution subsystem.
- Keep visible transcript command clean.
- Preserve direct typed `@exec openclaw "..."` and `@exec codex "..."`.
- Preserve approved-content compatibility path.

### Tests

- OpenClaw Composer-originated request submits `agent_backend=openclaw_cli`.
- Codex Composer-originated request submits `agent_backend=codex_cli`.
- Artifact refs are passed through.
- Expected outputs are passed through.
- Direct typed `@exec` without metadata still works.

### Acceptance

- App backend does not embed artifact ids into prompt text.

## Phase 8: Execution Composer Agent Artifact Selector

### Goal

Let users select reusable artifacts in Agent mode.

### Files

- `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`
- `ragenius_app_skeleton/frontend/src/App.jsx`
- `ragenius_app_skeleton/frontend/src/App.test.jsx`

### Changes

- Add Agent-mode artifact selector.
- Use checkboxes for multi-select.
- Show selected artifact rows/chips with `Remove`.
- Show compatibility reason for incompatible artifacts.
- Show OpenClaw staging hint.
- Hide Codex skill hint when backend is OpenClaw.
- Add `Save agent output as reusable artifact` option.
- Generate `expectedOutputs` when output persistence is requested.

### Tests

- Agent mode shows artifact selector.
- User can select multiple artifacts.
- User can remove selected artifacts.
- OpenClaw backend hides Codex skill hint.
- OpenClaw backend shows staging hint.
- Submit includes `artifactRefs`.
- Submit includes `expectedOutputs` when save output is selected.

### Acceptance

- User can run Agent mode with selected artifacts without copying ids.

## Phase 9: Execution Turn Result UX

### Goal

Display execution turns as runtime/artifact outputs, not normal answer turns.

### Files

- `ragenius_app_skeleton/frontend/src/App.jsx`
- `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx` if present
- `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx`
- related tests

### Changes

- Execution turns show runtime controls:
  - `Execution Details`
  - `Refresh Status`
  - `Retry`
  - `Confirm Execution` for pending confirmation
- Execution turns show artifact actions for persisted outputs:
  - `Preview`
  - `Open Saved File`
  - `Reuse In Composer`
  - `View In Artifact Library`
- Execution turns do not show `Mark Reviewed` as primary action.
- Execution turns show fallback `Create Reuse Artifact` only when plain text output exists and no persisted artifact exists.
- Add empty states for no artifact, failed before output, and persistence failure.

### Tests

- Execution turn does not show `Mark Reviewed`.
- Pending confirmation shows `Confirm Execution`.
- Persisted output artifact shows artifact actions.
- Failed execution shows details/retry but no artifact actions.
- Raw provider trace is inspector-only.

### Acceptance

- Execution cards are artifact-first and runtime-aware.

## Phase 10: Reuse In Composer

### Goal

Make artifact reuse from execution turns and Artifact Library open Composer with the correct preselected artifacts.

### Files

- `ragenius_app_skeleton/frontend/src/App.jsx`
- `ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.jsx`
- `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- related tests

### Changes

- `Reuse In Composer` opens Composer with clicked artifact preselected.
- Preserve Agent backend when launched from Agent execution turn.
- Default mode:
  - recommended compatible tool if available
  - recommended compatible skill if available
  - Agent mode for agent outputs when no stronger recommendation exists
- Add multi-artifact `Use Selected In Composer` from Artifact Library.
- Keep incompatible selected artifacts visible with warnings.

### Tests

- Single execution artifact opens Composer preselected.
- Agent backend is preserved from agent execution turn.
- Artifact Library multi-select opens Composer with all selected artifacts.
- Incompatible artifact is not silently dropped.
- Remove button clears selected artifact.

### Acceptance

- Reuse path is clear and reversible.

## Phase 11: Integration And Smoke Checks

### Goal

Verify the full flow across app and execution subsystem.

### Checks

- Run execution subsystem tests:

```powershell
npm test -- execute-agent.test.ts
npm test -- openclaw-cli-provider.test.ts openclaw-workspace.test.ts
```

- Run app frontend tests:

```powershell
npm test -- ExecutionComposer.test.jsx ArtifactLibrary.test.jsx App.test.jsx
```

- Manual smoke:
  - Create or select a chat export artifact.
  - Open Agent mode Composer.
  - Select OpenClaw.
  - Select the artifact.
  - Request a markdown output.
  - Confirm if required.
  - Verify output artifact appears on execution turn.
  - Click `Reuse In Composer`.
  - Verify Composer opens with the output artifact selected.

### Acceptance

- End-to-end agent artifact reuse works for OpenClaw.
- Codex path remains backward compatible.
- Existing tool/skill artifact reuse remains functional.

## Risk Controls

- Keep OpenClaw disabled by default via `OPENCLAW_CLI_ENABLED=false`.
- Do not implement cross-session artifact refs in this plan.
- Do not expose provider workspace paths in primary UI.
- Keep raw provider traces in inspector only.
- Prefer additive schema changes to avoid breaking existing `execute_agent` calls.

## Definition Of Done

- Contract and design are implemented for the MVP flow.
- Tests cover schema, resolver, staging, persistence, Composer selection, and reuse.
- OpenClaw required output persistence failure fails execution.
- Optional output failure appears in diagnostics.
- Execution turn GUI follows button rules.
- Artifact Library and Composer support reuse of agent output artifacts.

