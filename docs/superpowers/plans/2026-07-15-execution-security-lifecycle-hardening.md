# Execution Security And Lifecycle Hardening Plan

Date: 2026-07-15

## Goal

Fix the execution subsystem's high-risk authorization, confirmation, lifecycle,
dry-run, workspace-isolation, and artifact-persistence gaps without changing the
RAGenius skill execution contract or weakening Codex/OpenClaw compatibility.

## Normative References

- `docs/agent-mode-artifact-creation-reuse-contract.md`
- `docs/openclaw-agent-execution-integration-contract.md`
- `ragenius_execution_subsystem/docs/openclaw-execution-contract.md`
- `ragenius_execution_subsystem/docs/openclaw-provider-design.md`
- `ragenius_app_skeleton/docs/openclaw-execution-composer-design.md`

## Implementation Constraints

- Keep `artifact_refs` session-scoped.
- Keep `expected_outputs` provider-neutral.
- Do not add OpenClaw tests to `tests/execution/execute-skill.test.ts` unless an
  existing compatibility assertion must change.
- Do not modify unrelated dirty files.
- Preserve existing execution ids and normalized response fields where possible.
- Treat scope mismatch as `404`, not `403`, to avoid tenant existence disclosure.
- Real OpenClaw tests remain opt-in.

## Verified Session Invariant And Gap

Repository inspection confirms:

- the runtime session table uses `sessions.id` as its primary key
- each session stores its app (`collection_id`) and `user_id`
- `SessionRepo.get_or_create` rejects reuse of an existing id with a different
  app or user
- session-list and most session mutation routes compare the stored app/user

The current frontend generates ids with `session-${Date.now()}`. Replace this with
`crypto.randomUUID()` before relying on global uniqueness operationally.

The current skeleton also accepts `user_id` from request payload/query data; that
is an identity claim, not authentication. It is acceptable only for local MVP
operation where the app backend is not exposed to untrusted clients. Production
release requires authenticated user identity and centralized session-ownership
middleware. This production gap does not require duplicating `user_id` in the
execution subsystem.

## Milestone 0: Baseline And Compatibility Fixtures

### Work

1. Record `git status --short` and isolate the files owned by this plan.
2. Run the execution subsystem build and test suite.
3. Add response fixtures for `pending_confirmation`, `running`, `completed`,
   `partial`, `failed`, and `blocked` to app tests.
4. Add contract tests that preserve current Codex, OpenClaw, tool, and skill
   request parsing.
5. Preserve the verified session invariant: `sessions.id` is the primary key and
   an existing id cannot be rebound to a different app or user.
6. Replace frontend `session-${Date.now()}` generation with UUID-based session
   ids and test collision handling.
7. Centralize app route session validation so missing sessions and app/user
   mismatches fail before any execution-subsystem call.

### Exit Criteria

- Baseline failures are documented before implementation.
- Existing OpenClaw and Codex live-smoke behavior has a repeatable test case.

## Milestone 1: Trusted Principal And Scoped Execution Store

### Execution Subsystem Files

- `prisma/schema.prisma`
- new Prisma migration under `prisma/migrations/`
- `src/api/schemas/execution-request.schema.ts`
- new or existing Fastify authentication middleware/plugin
- `src/core/execution/execution-store.ts`
- `src/core/execution/prisma-execution-store.ts`
- `src/core/execution/execution-status-service.ts`
- `src/api/routes/executions.routes.ts`
- `src/config/env.ts` and runtime config files

### Work

1. Add a trusted execution principal containing app-service identity.
2. Validate the configured app-service bearer credential before accepting an
   execution scope.
3. Add a composite execution index for `(app_id, session_id)`; do not add an
   execution-table user identity column in the MVP.
4. Replace `get(executionId)`, `getLogs(executionId)`, and
   `getRequest(executionId)` with scoped equivalents.
5. Scope recent diagnostics or restrict them to an authenticated admin service.
6. Return `404` for unknown and mismatched scopes.

### Required Tests

- Valid app/session scope can retrieve status and logs.
- Wrong app or session receives the same `404` shape as an unknown id.
- Unauthenticated and invalid-service-token requests are rejected.
- In-memory and Prisma stores enforce identical scope behavior.

### Exit Criteria

- No user-facing execution lookup uses execution id alone.
- Production configuration fails closed when required service auth is missing.

## Milestone 2: Single-Use Confirmation State Machine

### Execution Subsystem Files

- `prisma/schema.prisma` and migration
- new confirmation repository/service under `src/core/execution/`
- `src/core/execution/execution-engine.ts`
- `src/api/routes/executions.routes.ts`
- `src/api/schemas/execution-request.schema.ts`

### Work

1. Remove `require_confirmation` from the public execution options schema.
2. Persist confirmation id, app/session scope, policy snapshot, expiry, decision, and
   consumption timestamp.
3. Return confirmation metadata with `pending_confirmation` without invoking a
   provider or workflow.
4. Confirm through an atomic `pending_confirmation -> running` claim.
5. Invoke execution through an internal trusted approval context rather than
   replaying a mutated public request.
6. Make repeated confirmation idempotent and prevent duplicate side effects.

### Required Tests

- A public approval boolean is rejected or ignored and cannot bypass policy.
- Invalid, expired, consumed, or scope-mismatched confirmation does not execute.
- Two concurrent confirmations invoke the provider exactly once.
- Reconfirming a terminal execution returns its existing state.

### Exit Criteria

- The only executable approval path is a scoped, server-issued, single-use
  confirmation transition.

## Milestone 3: Lifecycle And Dry-Run Correctness

### Execution Subsystem Files

- `src/api/schemas/common-response.schema.ts`
- `src/core/execution/execution-engine.ts`
- `src/core/execution/result-normalizer.ts`
- `tests/execution/dry-run.test.ts`
- `tests/execution/execute-agent.test.ts`

### Work

1. Add `running` to normalized lifecycle state if required by persisted/API state.
2. Map provider `completed`, `partial`, and `failed` directly to top-level status.
3. Preserve normalized provider diagnostics on terminal failure.
4. Move dry-run handling before skill workflow and agent provider invocation.
5. Return a metadata-only dry-run plan including policy, backend, artifacts,
   expected outputs, and confirmation requirement.

### Required Tests

- OpenClaw/Codex provider failure produces top-level `failed`.
- Optional output or persistence failure produces `partial`.
- Agent dry run never invokes provider, bridge, staging, or persistence.
- Skill dry-run behavior remains compatible.

### Exit Criteria

- Top-level execution status is authoritative and dry-run has no side effects.

## Milestone 4: Per-Execution OpenClaw Workspace

### Execution Subsystem Files

- `src/core/agents/openclaw-options.ts`
- `src/core/agents/openclaw-workspace.ts`
- `src/core/agents/openclaw-prompt-builder.ts`
- `src/core/agents/openclaw-cli-provider.ts`
- dedicated OpenClaw tests under `tests/agents/`

### Work

1. Derive `runs/<execution_id>/inputs` and `runs/<execution_id>/outputs`.
2. Rebase generated and legacy caller-relative paths under the current run root.
3. Validate containment after normalization and before prompt construction.
4. Verify only files beneath the current execution's output root.
5. Define bounded cleanup/retention without deleting persisted RAGenius artifacts.

### Required Tests

- A stale output from another execution cannot satisfy verification.
- Traversal, absolute, sibling-run, and symlink escape attempts fail.
- Concurrent runs with the same output id do not overwrite each other.
- Prompt paths and verification paths resolve to the same run root.

### Exit Criteria

- Every OpenClaw input and output is execution-isolated and current-run verifiable.

## Milestone 5: Artifact Identity And Persistence Semantics

### Execution Subsystem Files

- `src/core/tools/providers/artifact-store.ts`
- `src/core/agents/agent-output-artifact-persister.ts`
- `src/core/agents/openclaw-cli-provider.ts`
- `tests/agents/agent-output-artifact-persister.test.ts`
- `tests/agents/openclaw-cli-provider.test.ts`

### Work

1. Replace timestamp artifact ids with UUID/ULID identifiers.
2. Add byte-preserving file storage for binary agent outputs.
3. Keep verification and persistence statuses independent.
4. Map required persistence failure to `failed` and optional requested
   persistence failure to `partial`.
5. Keep `provider_origin` as backend identity; do not add redundant
   `created_by_agent_backend`.

### Required Tests

- Concurrent saves always generate distinct artifact ids.
- Binary persisted output is file-backed and byte/hash identical.
- Persistence failure does not change successful verification to false.
- Stored agent output maps cleanly to `StoredArtifactRecord` and UI projection.

### Exit Criteria

- Agent outputs are reusable artifacts with truthful verification and persistence
  state for text and binary content.

## Milestone 6: App Backend And Composer Integration

### App Responsibilities

1. Resolve the stored session and validate its app/user binding before every
   execution operation.
2. Configure service authentication for execution-subsystem calls.
3. Include app/session scope on submit, status, logs, and confirmation calls.
4. Store server-issued confirmation metadata in backend session lane state.
5. Confirm through the app backend; never replay with an approval boolean.
6. Render top-level `running`, `partial`, and `failed` states.
7. Keep dry-run results out of Artifact Library actions.

### Required Tests

- A browser request cannot operate on a session bound to another app/user.
- Status/log/confirmation client calls include complete scope.
- Confirmation retry does not create duplicate execution effects.
- Execution cards render partial results and warnings without raw output parsing.
- Existing Codex, OpenClaw, tool, and skill composer flows remain compatible.

### Exit Criteria

- The app is the authenticated user-facing boundary and the execution subsystem
  remains the sole runtime/provider boundary.

## Milestone 7: Validation And Live Regression

### Automated Validation

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm run build
npm test
```

Run targeted app backend and frontend suites discovered in the current app tree.
Do not rely on historical paths in the original OpenClaw plan when those files no
longer exist.

### Live Validation

With explicit opt-in environment flags, verify:

1. Read-only OpenClaw response completes.
2. Required markdown output is isolated, verified, and persisted.
3. Optional persistence failure produces `partial`.
4. Provider-reported task failure produces top-level `failed`.
5. Confirmation executes once and status/logs are app/session-scoped.
6. Dry run produces no WSL files or persisted artifacts.

### Completion Criteria

- Security tests prove no approval or cross-scope bypass.
- Unit/integration suites pass.
- Codex and OpenClaw live smoke tests pass.
- Contract examples and implemented schemas match.
- Any deferred low-risk fixes are recorded separately and do not weaken these
  guarantees.

## Implementation Status

Updated: 2026-07-25

- Milestones 0-6 are implemented.
- The execution-subsystem automated suite passes with 216 tests.
- The app backend suite passes with 78 tests.
- The focused Composer/UI suite passes with 87 tests.
- Real OpenClaw regression was run with explicit opt-in on 2026-07-25 against
  OpenClaw `2026.6.8`. The read-only run returned exactly `OK`. The
  confirmation-gated output run created, independently verified, and persisted
  the required markdown output beneath its isolated execution run root.
- The first live attempt exposed WSL default-shell interpolation of backticks in
  the prompt. The bridge now invokes OpenClaw through `wsl --exec`; the repeated
  live runs preserved the complete prompt and returned empty stderr.
- The two new Prisma migrations are generated and schema-valid but are not
  automatically applied because the local database migration history is not
  baselined against the repository's existing migrations.
