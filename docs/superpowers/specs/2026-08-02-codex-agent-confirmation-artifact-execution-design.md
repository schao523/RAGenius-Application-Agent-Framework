# Codex Agent Confirmation, Artifact, And Completion Addendum

## Shared Agent Design Reference

`docs/superpowers/specs/2026-08-03-agent-execution-lifecycle-evidence-design.md`
supersedes this document for shared lifecycle, independent-verification
authority, provider-state policy, process supervision, diagnostics, and artifact
byte serving. This document remains authoritative for Codex confirmation,
workspace staging, prompt projection, and JSONL protocol details.

## Status

Proposed normative addendum for Codex Agent-mode execution.

This document narrows and completes the Codex-specific behavior required by:

- `docs/agent-mode-artifact-creation-reuse-contract.md`
- `docs/agent-mode-artifact-creation-reuse-design.md`
- `docs/superpowers/plans/2026-07-15-execution-security-lifecycle-hardening.md`

If this addendum conflicts with older Codex-specific implementation notes, this
addendum takes precedence. It does not change the OpenClaw contract.

## Purpose

Codex Agent mode currently has three contract breaks:

1. A scoped single-use confirmation can be consumed by RAGenius without the
   confirmed state reaching the Codex provider.
2. Session-scoped `artifact_refs` can reach the execution subsystem but be
   dropped before the Codex bridge.
3. A Codex process exit code of zero can be normalized as `completed` even when
   Codex reports `pending_confirmation` and performs no requested side effect.

The result is a false-completion state: the UI reports `Completed`, while the
external operation never started. This addendum defines the internal execution
context, artifact staging, provider result, and verification behavior needed to
prevent that state.

## Scope

This addendum covers:

- `execute_agent` with `agent_backend = "codex_cli"`
- typed and Execution Composer Codex requests
- validated single-use confirmation propagation
- selected artifact resolution and Codex staging
- Codex JSONL parsing and semantic result normalization
- external-write evidence and asynchronous-operation reporting
- app-side rendering of normalized execution state

This addendum does not cover:

- Builder discovery or registration of Codex instruction skills
- installation or publication of Codex skills
- OpenClaw execution behavior
- redesign of the provider-neutral public `execute_agent` request
- direct execution of RAGenius workflow skills

## Architectural Decision

Use a trusted internal provider execution context constructed by the execution
engine after request validation and confirmation claim. Do not add public
client-controlled fields such as `confirmed`, `confirmation_granted`, or
`resolved_artifacts` to `execute_agent`.

The execution engine remains the sole authority for confirmation and artifact
ownership. The Codex provider adapts trusted internal context into a bounded
Codex workspace and system-authored prompt block. The Codex bridge parses
machine-readable CLI events and returns semantic task evidence. The result
normalizer, not the model and not the process exit code alone, determines the
top-level execution status.

Alternatives rejected:

- **Prompt-only confirmation wording:** insufficient because user text could
  imitate approval and artifact bytes would still be unavailable.
- **Pass original artifact paths directly:** violates path isolation and leaks
  storage layout into the provider.
- **Treat exit code zero as completion:** proves only that the CLI turn ended,
  not that the requested operation succeeded.

## Trust Boundaries

### Public Request

The public request remains provider-neutral:

```ts
type ExecuteAgentRequest = {
  request_type: "execute_agent";
  agent_backend: "codex_cli" | "openclaw_cli";
  app_id: string;
  session_id: string;
  agent_query: string;
  agent_skill_hint?: string;
  artifact_refs?: AgentArtifactRef[];
  expected_outputs?: AgentExpectedOutput[];
  context?: Record<string, unknown>;
};
```

No public request field can assert that confirmation has been granted or that
an artifact has been resolved.

### Internal Provider Context

After validation, policy classification, and any required confirmation claim,
the execution engine constructs:

```ts
type AgentProviderExecutionContext = {
  execution_id: string;
  authorization: {
    state: "not_required" | "confirmed";
    permission_scope: string;
    policy_fingerprint: string;
    confirmed_at?: string;
  };
  operation_plan: AgentOperationPlanItem[];
  resolved_artifacts: ResolvedAgentArtifact[];
  expected_outputs: AgentExpectedOutput[];
};
```

```ts
type AgentOperationPlanItem = {
  operation_id: string;
  kind: "read" | "workspace_write" | "external_write";
  description: string;
  required: boolean;
  target_hint?: string;
  minimum_verification:
    | "process_observed"
    | "provider_reported"
    | "independently_verified";
};
```

Rules:

- `authorization.state = "confirmed"` is set only after an atomic, scoped,
  single-use confirmation claim succeeds.
- `policy_fingerprint` is the SHA-256 digest of the stable serialized policy
  snapshot, including the operation plan, that was issued and later claimed.
- The engine must compare the claimed fingerprint with the current policy before
  provider invocation.
- `confirmed_at` is server-generated. Confirmation identifiers and tokens are
  retained in execution diagnostics but are not included in the model prompt.
- `operation_plan` is server-generated before confirmation and is immutable for
  the confirmed execution. It is derived from the normalized agent request,
  selected skill hint, expected outputs, and provider-specific deterministic
  planning rules. It cannot be supplied or rewritten by the model.
- `resolved_artifacts` is server-generated through `AgentArtifactResolver`.
- Client `context` cannot override any internal provider context field.

For known NotebookLM tasks, deterministic planning recognizes source-add and
artifact-generation operations separately. For an unrecognized mutation task,
the planner creates one required generic mutation operation; that operation
cannot complete without at least provider-reported evidence. Planning failure
before a required external write returns `AGENT_OPERATION_PLAN_REQUIRED`
instead of invoking Codex with unverifiable completion criteria.

## Confirmation Propagation

### Engine Behavior

For policy mode `require_confirmation`:

1. Initial submission issues a confirmation resource and returns top-level
   `pending_confirmation` without resolving artifact bytes or invoking Codex.
2. The confirmation endpoint atomically claims the confirmation for the exact
   `{app_id, session_id, execution_id, confirmation_id}` scope.
3. The engine compares the stored and current policy snapshots.
4. The engine confirms that the operation plan is unchanged.
5. Only then does it construct internal authorization state `confirmed` and
   invoke the provider once.

For policy modes that do not require confirmation, authorization state is
`not_required`.

### Codex Prompt Projection

The Codex provider adds a system-authored block separate from user content:

```text
RAGenius authorization:
- State: confirmed
- Permission scope: agent.external_write
- Policy fingerprint: <sha256>
- Approved operations:
  - source_add: Add the selected source to notebook Testing
  - report_generate: Start study-report generation in notebook Testing
- The user already approved the exact operations represented by this policy.
- Do not request a second confirmation for those operations.
- Do not extend the approval to additional destructive or external-write work.
```

The provider must not represent `confirmed` when internal context says
`not_required`, and user prompt text must never influence this block.

If Codex requests confirmation again after RAGenius has supplied confirmed
authorization, the provider result is not a new valid RAGenius confirmation.
It is normalized as `failed` with code
`CODEX_UNEXPECTED_CONFIRMATION_REQUEST`. A provider cannot issue or renew a
RAGenius confirmation resource.

## Artifact Resolution And Staging

### Resolution

After authorization and before provider invocation, the engine resolves every
`artifact_ref` using the existing provider-neutral resolver.

Resolution must enforce:

- exact `app_id` and `session_id` ownership
- artifact readiness and reusability
- requested reuse-mode compatibility with Codex
- size limits
- content hash and byte-count validation
- rejection of missing, cross-session, cross-app, or unsafe artifacts

Failure to resolve any required input fails the execution before Codex starts.

### Codex Run Workspace

Each real Codex execution receives a unique workspace:

```text
<CODEX_RUN_ROOT>/<execution_id>/
  inputs/
  outputs/
```

`CODEX_RUN_ROOT` defaults to
`ragenius_execution_subsystem/storage/codex-runs`. A run workspace is temporary
provider state, not a reusable RAGenius artifact.

Staging rules:

- Never give Codex the original artifact-store path.
- Copy file-backed and binary artifacts byte-for-byte into `inputs/`.
- Write inline text as UTF-8 into `inputs/`.
- Metadata-only artifacts receive no staged bytes.
- Use execution-scoped generated filenames; never trust a user filename as a
  path component.
- Reject symlinks, traversal, absolute requested paths, and destination escape.
- Verify staged size and SHA-256 against resolved metadata.
- Set the Codex working directory to the run workspace.
- Remove the run workspace according to bounded retention policy after terminal
  execution; never remove persisted RAGenius artifacts during cleanup.

### Staged Artifact Contract

```ts
type CodexStagedArtifact = {
  artifact_id: string;
  role: "source" | "reference" | "attachment" | "context";
  reuse_mode: "file_backed" | "inline_text" | "binary_payload" | "metadata_only";
  display_name: string;
  media_type?: string;
  size_bytes?: number;
  sha256?: string;
  workspace_relative_path?: string;
};
```

The prompt includes only workspace-relative paths and verified metadata:

```text
Selected RAGenius artifacts:
- artifact_id: artifact_123
  role: source
  path: inputs/artifact_123.md
  media_type: text/markdown
  sha256: <digest>
```

When `artifact_refs` is non-empty, the prompt must not claim that no artifact was
selected. Codex skill hints do not replace artifact staging.

## Codex Invocation

The bridge must:

- invoke the configured current Codex CLI
- use the per-execution workspace as `--cd`
- read the task prompt from stdin
- request JSONL events
- use ephemeral CLI state for subsystem runs unless replay is explicitly
  designed later
- isolate Python/NotebookLM certificate variables from the Codex process
- preserve only environment values allowed by execution policy
- apply an explicit Codex sandbox instead of
  `--dangerously-bypass-approvals-and-sandbox` before production exposure

The NotebookLM Python wrapper may configure Python certificate variables for its
own process. Those variables must not be globally injected into Codex.

## Provider Result Contract

### JSONL Parsing

The bridge must parse Codex JSONL line-by-line. It must not parse the complete
JSONL stream as one JSON document or use the entire stream as `final_message`.

It extracts:

- thread and turn identifiers
- terminal turn state
- final agent-message text
- command execution start/completion events
- command exit codes and bounded output summaries
- explicit CLI error events
- token usage when present

Secrets and authorization headers must be redacted before persistence.

### Required Final Response

The prompt requires the final agent message to conform to:

```ts
type CodexAgentTaskResult = {
  task_status: "completed" | "partial" | "failed" | "pending_confirmation";
  summary: string;
  activated_skills: string[];
  operations: Array<{
    operation_id: string;
    operation: string;
    target?: string;
    status: "completed" | "accepted" | "processing" | "failed" | "not_run";
    external_id?: string;
    evidence?: string;
  }>;
  artifacts: CodexCliArtifactSummary[];
  errors: Array<{
    code: string;
    message: string;
  }>;
};
```

Malformed final JSON does not automatically fail a read-only conversational
request, but it cannot prove an external mutation.

Every required `operation_id` in the server-generated plan must appear exactly
once in the final result. Unknown operation ids do not inherit authorization and
cannot contribute completion evidence. Missing required operation ids are
treated as `not_run`.

### Evidence Levels

```ts
type OperationVerification = {
  operation_id: string;
  operation: string;
  level:
    | "none"
    | "process_observed"
    | "provider_reported"
    | "independently_verified";
  status: "completed" | "accepted" | "processing" | "failed" | "not_run";
  external_id?: string;
  evidence?: string;
};
```

- `process_observed`: the bridge observed a relevant command exit successfully.
- `provider_reported`: structured provider output includes a stable source,
  artifact, job, or operation identifier.
- `independently_verified`: a follow-up read confirms the external state.

For NotebookLM:

- source creation should return a source identifier and should be verified by a
  source-list or source-status read when available;
- report generation should return an artifact or job identifier;
- `accepted` or `processing` means generation started, not that the report is
  ready;
- report readiness requires a later artifact-status or wait result.

## Top-Level Status Mapping

Top-level execution status is authoritative and follows these rules in order:

1. CLI launch failure, timeout, non-zero exit, `turn.failed`, or explicit fatal
   event -> `failed`.
2. Final `task_status = failed` -> `failed`.
3. Final `task_status = pending_confirmation` after confirmed authorization ->
   `failed` with `CODEX_UNEXPECTED_CONFIRMATION_REQUEST`.
4. Mutation-classified request with no observed mutation command and no
   operation evidence -> `failed` with `CODEX_REQUIRED_OPERATION_NOT_RUN`.
5. A required planned operation is missing from the final result -> `failed` if
   no required operation succeeded, otherwise `partial`.
6. Some required operations succeeded and others failed or were not run ->
   `partial`.
7. Every required operation meets its planned `minimum_verification`, with no
   required failure -> `completed`.
8. An asynchronous operation with a stable external identifier and status
   `accepted` or `processing` may be top-level `completed`, but its summary must
   say that generation started and remains in progress. It must not say the
   external artifact is ready.
9. A read-only request may be `completed` from a valid final agent message even
   when no command executes.

A zero process exit is necessary but not sufficient for mutation completion.

The normalized result includes:

```ts
type CodexNormalizedResult = {
  backend: "codex_cli";
  status: "completed" | "partial" | "failed";
  summary: string;
  activated_skills: string[];
  staged_inputs: CodexStagedArtifact[];
  operation_verification: OperationVerification[];
  artifacts: CodexCliArtifactSummary[];
  provider_metadata: {
    thread_id?: string;
    turn_status: "completed" | "failed" | "unknown";
    raw_exit_code: number;
    confirmation_state: "not_required" | "confirmed";
    policy_fingerprint: string;
    command_count: number;
    successful_command_count: number;
    final_json_status: "parsed" | "invalid" | "missing";
  };
  diagnostics?: {
    failure_code?: string;
    failure_message?: string;
    stdout_tail?: string;
    stderr_tail?: string;
  };
};
```

## App And Composer Behavior

Execution Composer continues to send separate fields for:

- backend
- Codex skill hint
- task prompt
- selected artifact refs
- expected outputs

The app must not encode artifact identifiers or confirmation state into user
prompt text.

The app renders only normalized top-level state:

- `pending_confirmation`: show `Confirm Execution`
- `failed`: show failure summary and retry/inspector actions
- `partial`: show completed and incomplete operations
- `completed` with asynchronous `processing`: show `Generation started`
- `completed` with independent verification: show `Completed`

The app must not display `Completed` solely because Codex exited zero.

## Error Codes

The Codex provider adds these normalized errors:

- `CODEX_ARTIFACT_RESOLUTION_FAILED`
- `CODEX_ARTIFACT_STAGING_FAILED`
- `CODEX_STAGED_ARTIFACT_VERIFICATION_FAILED`
- `CODEX_FINAL_RESULT_INVALID`
- `AGENT_OPERATION_PLAN_REQUIRED`
- `CODEX_UNEXPECTED_CONFIRMATION_REQUEST`
- `CODEX_REQUIRED_OPERATION_NOT_RUN`
- `CODEX_OPERATION_PARTIAL`
- `CODEX_OPERATION_VERIFICATION_FAILED`

Existing launch, timeout, non-zero exit, policy, and scope errors remain valid.

## Observability

Execution Inspector must show:

- confirmation state without exposing the confirmation token
- policy scope and fingerprint
- selected artifact ids and staged relative paths
- stage verification status
- activated skill ids
- bounded command summaries and exit codes
- operation evidence and verification levels
- external source/artifact/job identifiers
- distinction between `accepted`, `processing`, and ready completion
- failure code and suggested action

Provider raw output remains diagnostic data and is never the app rendering
contract.

## Testing Contract

### Unit Tests

- Public requests cannot set trusted confirmation state.
- Confirmed internal context is created only after a valid claim.
- Policy fingerprint mismatch prevents provider invocation.
- The confirmed operation plan cannot change before provider invocation.
- Codex provider receives resolved artifacts and not raw refs alone.
- Staging rejects cross-scope artifacts, traversal, symlinks, hash mismatch, and
  size mismatch.
- Prompt receives confirmed authorization only from internal context.
- JSONL parser extracts final agent JSON and command events.
- Exit zero plus `pending_confirmation` does not complete.
- Exit zero plus no mutation evidence does not complete a mutation request.
- Missing required operation ids cannot complete a mutation request.
- Read-only text completion remains backward compatible.
- Python certificate variables do not reach the Codex child.

### Integration Tests

- Initial external-write request returns one scoped confirmation.
- Valid confirmation invokes Codex exactly once.
- Duplicate confirmation cannot repeat side effects.
- One selected artifact reaches the Codex run workspace with matching hash.
- Codex receives the workspace-relative staged path.
- A mixed-operation result maps to `partial`.
- App rendering uses normalized status instead of raw CLI success.

### Live Tests

1. Read-only Codex request completes without confirmation.
2. Confirmed Codex request does not ask for duplicate confirmation.
3. `notebooklm` skill activation is recorded.
4. Selected session artifact is readable from the Codex run workspace.
5. NotebookLM source add returns an identifier and appears in source listing.
6. NotebookLM report generation returns an artifact/job identifier.
7. A processing report is displayed as started, not ready.
8. Final artifact status is independently checked before claiming readiness.

## Migration And Compatibility

- No public request migration is required.
- Existing callers without `artifact_refs` remain valid.
- Existing read-only Codex requests remain valid.
- `AgentProvider.execute` gains the trusted internal execution-context argument.
- Codex provider and bridge response types gain staged-input, operation, and
  provider-metadata fields.
- Existing records remain readable; new records add metadata without rewriting
  historical results.
- OpenClaw retains its current provider-specific implementation while sharing
  the provider-neutral resolver and internal authorization concepts where
  appropriate.

## Acceptance Criteria

- A confirmed Codex execution cannot pause for the same confirmation again.
- A selected artifact cannot disappear between execution request and Codex
  prompt.
- Codex never receives an original artifact-store path.
- A mutation request with no mutation evidence cannot return top-level
  `completed`.
- Codex cannot omit a required planned operation and still return top-level
  `completed`.
- Asynchronous NotebookLM generation is reported as started until readiness is
  verified.
- App UI status is derived from normalized execution semantics, not CLI exit
  status.
- Confirmation, artifact scope, and result retrieval remain bound to the same
  app/session execution scope.
