# Agent Execution Lifecycle And Evidence Contract

Date: 2026-08-03

## Status

Normative cross-subsystem addendum for Agent execution through `codex_cli` and
`openclaw_cli`.

This document extends:

- `docs/openclaw-agent-execution-integration-contract.md`
- `docs/agent-mode-artifact-creation-reuse-contract.md`
- `docs/superpowers/specs/2026-08-02-codex-agent-confirmation-artifact-execution-design.md`
- `ragenius_execution_subsystem/docs/openclaw-execution-contract.md`

Where an older document conflicts with this addendum, this addendum controls
Agent lifecycle, evidence, artifact projection, provider-state access, timeout,
and file-serving behavior.

## Implementation And Acceptance Status

Implementation date: 2026-08-03  
Platform: Windows host with the `OpenClawGateway` WSL distribution

- Automated execution-subsystem acceptance passed: build, lint, typecheck,
  Prisma schema validation, and 295 Node tests (293 passed, 2 Windows symlink
  tests skipped because symlink creation was unavailable).
- App backend acceptance passed: 59 scoped execution, chat routing, client, and
  artifact proxy tests.
- App frontend acceptance passed: 125 tests and the production Vite build.
- Live OpenClaw acceptance passed. Redacted executions `execution_3726...` and
  `execution_3f7e...` exposed `queued -> running -> completed`; the required WSL
  markdown output was independently verified, persisted as `artifact_2410...`,
  found in scoped inventory, and not duplicated by repeated confirmation.
- Live Codex/NotebookLM acceptance is blocked on local authentication. A
  one-shot Codex `gpt-5.5` override succeeded, but the configured NotebookLM
  `default` profile failed a subsequent read-only notebook listing with
  `Authentication expired or invalid`. The earlier mutation execution ended
  failed, and its partial external side-effect state is unknown, so no automatic
  mutation retry was performed.

The Codex/NotebookLM acceptance remains open until an administrator
re-authenticates the `default` profile and explicitly reruns the opt-in smoke.

## Purpose

Agent providers can produce conversational text, execute local commands, mutate
external systems, and create reusable files. RAGenius must not treat all four as
equivalent evidence of success. This contract defines the provider-neutral
behavior that both Codex CLI and OpenClaw CLI must implement while retaining
provider-specific adapters and process launchers.

## Scope

This contract applies to:

- Agent submission and confirmation from `ragenius_app_skeleton`
- execution lifecycle persistence in `ragenius_execution_subsystem`
- Codex and OpenClaw process supervision
- provider-state, workspace, and network policy metadata
- operation evidence and trusted post-run verification
- Agent-created artifact verification, persistence, and serving
- normalized diagnostics shown by the app

This contract does not redesign skill execution, Builder administration, RAG
retrieval, or cross-session artifact permissions.

## Responsibility Boundary

`ragenius_app_skeleton` owns authenticated user/session checks, Composer intent,
confirmation UX, polling, and user-facing rendering. It must not invoke provider
CLIs, infer success from raw output, or open arbitrary provider file paths.

`ragenius_execution_subsystem` owns policy, confirmation claims, queueing,
provider invocation, process termination, operation verification, artifact
persistence, and authoritative normalized status.

Codex and OpenClaw providers own only provider-specific prompt projection,
workspace translation, process invocation, and protocol parsing. A provider's
text or declared artifact identifier is untrusted until the execution subsystem
verifies it.

## Lifecycle Contract

### Statuses

The provider-neutral execution lifecycle is:

```text
pending_confirmation -> queued -> running -> completed | partial | failed
                         ^
submitted without confirmation
```

`blocked` is terminal and occurs before provider invocation.

Rules:

- `queued` is a persisted, non-terminal status.
- `running` means a worker has claimed the execution.
- `completed`, `partial`, `failed`, and `blocked` are terminal.
- Timeout maps to `failed` with `diagnostics.primary.code = "AGENT_TIMEOUT"` and
  `provider_metadata.timed_out = true`; it does not introduce a second terminal
  status vocabulary.
- A provider's nested status cannot override the authoritative top-level status.
- Status, result, logs, and confirmation remain scoped by `{app_id, session_id}`.

### Sync And Async Submission

The public request continues to use:

```ts
type AgentExecutionMode = "sync" | "async";
```

For `async`:

- submission and confirmation persist `queued` before returning;
- the HTTP response returns without waiting for provider completion;
- the app polls the existing scoped execution status endpoint;
- only the worker may transition `queued -> running`;
- duplicate submissions are distinct executions;
- duplicate confirmation cannot enqueue the same execution twice.

For `sync`, the execution may run in the request lifecycle for backward
compatibility. The implementation must still use the same status transition,
verification, artifact, and diagnostic rules.

The single-instance MVP may use an in-process worker backed by persisted
execution records. On startup, records left in `queued` or `running` by an
unclean shutdown must become `failed` with code `AGENT_EXECUTION_INTERRUPTED`.
Multi-instance claiming and lease recovery are out of scope until a distributed
worker is introduced.

## Process Supervision Contract

Each provider invocation must have one execution-owned process supervisor.

On timeout or cancellation, the supervisor must:

1. stop accepting provider output;
2. terminate the complete descendant process tree;
3. wait for termination or a bounded kill grace period;
4. force-kill remaining descendants where supported;
5. retain bounded, redacted stdout and stderr tails;
6. return only after cleanup has been attempted.

Calling `child.kill()` on only the direct process is insufficient.

Platform requirements:

- Windows Codex execution must terminate the process tree without `shell: true`.
- WSL OpenClaw execution must terminate the WSL-side process group or equivalent
  execution-owned process tree.
- A timeout must not leave NotebookLM login, Python, Codex, OpenClaw, or bridge
  descendants running.

## Policy Contract

Policy must distinguish user workspace access from provider-maintenance state:

```ts
type AgentAccessPolicy = {
  workspace_access: "none" | "read" | "scoped_write";
  provider_state_access: "none" | "read" | "scoped_write";
  provider_state_labels: string[];
  network_access: "deny" | "allowlisted";
};
```

`provider_state_labels` contains stable labels such as
`notebooklm_profile:default` or `openclaw_agent_state`; public results must not
expose credential paths, cookies, or tokens.

NotebookLM authentication refresh may require `provider_state_access =
"scoped_write"` even for a read-only user operation. This does not imply user
workspace write access. The policy snapshot and confirmation fingerprint must
include provider-state access.

Free-text keyword classification is a conservative fallback. Structured
Composer intent and server-generated operation plans take precedence, but the
execution subsystem remains authoritative and may raise risk. Negated text such
as `do not delete` must not alone create a destructive operation.

## Evidence Contract

### Evidence Levels

```ts
type AgentEvidenceLevel =
  | "none"
  | "agent_reported"
  | "process_observed"
  | "provider_reported"
  | "independently_verified";
```

- `agent_reported`: the Agent claimed an outcome in text or structured output.
- `process_observed`: the trusted bridge observed a relevant command complete
  successfully.
- `provider_reported`: a relevant successful command returned a stable external
  operation, source, artifact, or job identifier.
- `independently_verified`: the execution subsystem queried the external
  provider through a trusted adapter after the Agent turn and matched the
  expected operation and stable identifier.

Agent-issued follow-up commands and their stdout are not independent
verification. Existing transcript-derived `independently_verified` results must
be downgraded to `provider_reported` or `process_observed` unless a trusted
execution-subsystem verifier supplied the record.

### Read Operations

A local reasoning-only request may complete from a valid final response.

A provider-backed read, including NotebookLM listing or querying, requires at
least one relevant `process_observed` operation. Conversational text alone must
fail with `AGENT_PROVIDER_EVIDENCE_MISSING`.

### Mutation Operations

Every required mutation must map to a server-generated operation-plan item.
Completion requires that item's minimum evidence level. External mutations that
can be queried after execution should require `independently_verified`.

Accepted asynchronous external work may complete the RAGenius invocation with
`provider_reported` only when the operation plan permits it. Its summary must say
that generation started, not that the external artifact is ready.

### Trusted Verification Record

```ts
type TrustedOperationVerification = {
  operation_id: string;
  status: "completed" | "accepted" | "processing" | "failed" | "not_found";
  level: "independently_verified";
  verifier: "execution_subsystem_adapter";
  provider: string;
  external_id?: string;
  checked_at: string;
  evidence_summary: string;
};
```

The record must be generated outside the Agent transcript. Raw provider secrets
and unbounded responses must not be persisted in it.

## Artifact Contract

Provider output separates reports from persisted RAGenius artifacts:

```ts
type AgentProviderResult = {
  reported_outputs?: AgentReportedOutput[];
  artifacts: StoredAgentArtifactProjection[];
};
```

`reported_outputs` may contain provider claims, relative workspace paths, and
external IDs. It is diagnostic and cannot create an Open, Preview, Reuse, or
Delete action.

`artifacts` contains only records that:

1. match a declared expected output where required;
2. pass execution-owned path, file-type, size, and hash verification;
3. are persisted in the scoped RAGenius artifact store; and
4. are confirmed by inventory lookup under the same `{app_id, session_id}`.

The app must suppress artifact actions for unknown or non-inventory IDs.

## Artifact Byte Serving Contract

The app must not directly serve or delete an arbitrary filesystem path received
as artifact metadata.

The execution subsystem, as artifact-store owner, must provide scoped preview,
download, and delete operations by artifact ID. It must resolve bytes beneath an
approved artifact root and reject traversal, symlinks escaping the root, missing
scope, and non-ready records.

During migration, any app-local fallback must apply the same approved-root
containment before `FileResponse` or `unlink`. A resolved path existing on disk
is not sufficient authorization.

## Diagnostics Contract

Diagnostics preserve the task's primary failure and append secondary failures:

```ts
type AgentDiagnostics = {
  primary?: {
    code: string;
    message: string;
    error_class?: string;
  };
  secondary: Array<{
    stage: "verification" | "persistence" | "cleanup" | "transport";
    code: string;
    message: string;
  }>;
};
```

Compatibility fields `failure_code` and `failure_message` may mirror
`primary.code` and `primary.message`. Output persistence or cleanup failure must
not overwrite an earlier provider, policy, authentication, or timeout failure.

## App Transport Contract

The app-to-execution client must configure bounded connect and response
timeouts. Async submission endpoints must return before provider execution, so
their response timeout is an API timeout rather than an Agent timeout.

The app's async FastAPI endpoints must not perform blocking HTTP I/O on the event
loop. They may use an async HTTP client or explicitly offload a synchronous
client to a worker thread.

## Compatibility

- Existing tool and skill execution is unchanged.
- Existing synchronous Agent requests remain valid.
- Existing OpenClaw expected-output verification remains valid.
- Existing app clients may continue reading `failure_code` and
  `failure_message` during diagnostic migration.
- Provider-local output paths and provider-reported IDs never become stable
  artifact identity.

## Acceptance Criteria

1. Async submission returns a persisted execution ID before provider completion.
2. Duplicate confirmation cannot enqueue or invoke an Agent twice.
3. Timeout leaves no descendant process alive.
4. Provider-backed reads cannot complete from text alone.
5. Independent verification originates from a trusted subsystem adapter.
6. Only inventory-backed persisted artifacts receive user actions.
7. Primary diagnostics survive verification, persistence, and cleanup failures.
8. Policy reports provider-state access separately from workspace access.
9. Artifact bytes cannot be served or deleted outside approved storage roots.
10. Codex and OpenClaw return the same provider-neutral lifecycle and result
    semantics while retaining provider-specific invocation details.
