# Agent Execution Lifecycle And Evidence Design

## Status

Approved design addendum, 2026-08-03.

Normative behavior is defined by
`docs/agent-execution-lifecycle-evidence-contract.md`.

## Goal

Give Codex CLI and OpenClaw CLI one authoritative execution lifecycle, evidence
model, artifact projection, and diagnostics model while isolating their process
and provider-specific behavior.

## Architectural Decision

Use a shared Agent execution pipeline with adapter boundaries:

```text
RAGenius App
  -> submission and confirmation API
  -> persisted Agent job
  -> AgentExecutionQueue
  -> ExecutionEngine
  -> CodexCliProvider | OpenClawCliProvider
  -> AgentOperationVerifierRegistry
  -> AgentResultFinalizer
  -> AgentArtifactService
  -> normalized scoped result
```

The queue, finalizer, verification registry, and artifact service are
provider-neutral. Process launchers, prompt builders, protocol parsers, workspace
translation, and provider runtime state remain provider-specific.

This is preferred over fixing Codex in isolation because OpenClaw has the same
timeout, evidence, artifact, and diagnostic obligations. It is preferred over a
single generic provider implementation because Windows Codex and WSL OpenClaw
have materially different process and path semantics.

## Component Design

### AgentExecutionQueue

Introduce a bounded single-instance queue in the execution subsystem. The API
persists the request and a `queued` normalized result before enqueueing. A worker
claims one job, persists `running`, invokes the existing `ExecutionEngine`, and
persists the terminal result.

```ts
interface AgentExecutionQueue {
  enqueue(job: AgentExecutionJob): Promise<void>;
  start(): void;
  stop(): Promise<void>;
}

type AgentExecutionJob = {
  execution_id: string;
  request: ExecuteAgentRequest;
  confirmed_authorization?: ConfirmedAgentAuthorization;
};
```

The MVP runs one worker with configurable bounded concurrency. It is not a
distributed queue. Startup reconciliation marks persisted `queued` and `running`
records failed with `AGENT_EXECUTION_INTERRUPTED`, preventing permanently
running records after a restart.

The confirmation route atomically claims confirmation before enqueueing. It
must not call a provider inline for async requests. Synchronous requests retain
the current API behavior but pass through the same finalizer.

### Execution Store Evolution

The store needs explicit transition support rather than treating every save as
an unrelated replacement:

```ts
interface ExecutionStore {
  transition(input: {
    scope: ExecutionScope;
    from: ExecutionStatus[];
    to: NormalizedExecutionResult;
  }): Promise<"updated" | "state_mismatch" | "not_found">;
  listInterruptedAgentExecutions(): Promise<ExecutionRecord[]>;
}
```

Prisma transitions use a conditional update on execution ID, app ID, session ID,
and current status. In-memory behavior must match. This prevents duplicate
workers and duplicate confirmations from running the same execution.

### AgentProcessSupervisor

Process termination becomes a provider dependency rather than ad hoc bridge
logic:

```ts
interface AgentProcessSupervisor {
  run(spec: SupervisedProcessSpec): Promise<SupervisedProcessResult>;
}
```

The supervisor owns timeout, output bounds, redaction hooks, graceful shutdown,
force termination, and descendant cleanup.

For Windows, termination invokes `taskkill.exe /PID <pid> /T /F` through
`spawnFile` or `spawn` with `shell: false`, then waits for the original child
close event with a bounded grace period. For non-Windows native processes, start
an execution-owned process group and signal the group. For WSL, the OpenClaw
bridge must start a WSL-side process group and terminate that group rather than
only the Windows `wsl.exe` wrapper.

Codex and OpenClaw bridges retain protocol parsing but delegate lifecycle to
their supervisor implementation.

### Agent Access Policy

Extend `AgentPolicyDecision` with:

```ts
providerStateAccess: "none" | "read" | "scoped_write";
providerStateLabels: string[];
```

The Codex NotebookLM projection maps its approved profile to
`notebooklm_profile:<profile>`. OpenClaw maps its internal Agent state to
`openclaw_agent_state`. Absolute state paths remain internal provider metadata.

The operation planner supplies structured operation risk. Keyword matching is
used only when structured intent is absent. A small negation window prevents
`do not delete`, `without deleting`, and equivalent phrases from creating a
destructive operation by themselves.

### AgentOperationVerifierRegistry

Create a provider-neutral registry keyed by an operation verifier ID, not by CLI
backend. This allows Codex and OpenClaw to share NotebookLM verification.

```ts
interface AgentOperationVerifier {
  readonly id: string;
  supports(input: AgentVerificationInput): boolean;
  verify(input: AgentVerificationInput): Promise<TrustedOperationVerification[]>;
}
```

The initial `NotebookLmOperationVerifier` uses the existing `NotebookLmAdapter`.
It receives server-generated operation-plan items and validated provider-reported
external IDs. It performs bounded checks:

- source addition: call `list_sources` for the resolved notebook and match the
  stable source ID;
- generated report: call `poll_artifact_task` when a stable task ID exists;
- list/read operations: require a relevant successful bridge command, because a
  second list query would add cost without improving identity evidence.

The verifier stores a bounded summary, never full provider payloads. Transcript
commands can establish `process_observed` or `provider_reported`, but only a
registry verifier can emit `independently_verified`.

### AgentResultFinalizer

Move shared post-provider behavior out of provider implementations:

```ts
type AgentResultFinalizerInput = {
  request: ExecuteAgentRequest;
  context: AgentProviderExecutionContext;
  provider_result: AgentProviderResult;
  trusted_verifications: TrustedOperationVerification[];
};
```

The finalizer:

1. reconciles operation evidence against the operation plan;
2. enforces minimum evidence for reads and mutations;
3. verifies and persists expected outputs;
4. projects only persisted inventory-backed artifacts;
5. preserves primary diagnostics and appends secondary diagnostics;
6. computes the authoritative terminal status.

Provider-specific evaluators may parse Codex or OpenClaw output into
`reported_operations` and `reported_outputs`, but they do not issue stable
RAGenius artifact identity or final authority.

### Artifact Projection And Serving

Rename provider-declared `artifacts` to `reported_outputs` internally. Keep the
public `result.artifacts` field, but populate it only from persisted
`StoredArtifactRecord` projections returned by the artifact store.

Add scoped execution-subsystem endpoints for preview, download, and delete. The
artifact store resolves the record and enforces containment under its configured
storage root before touching bytes. The app proxies these operations after
checking authenticated session ownership; it does not use `file_path` from
inventory metadata.

Migration proceeds in two stages:

1. suppress actions for IDs absent from scoped inventory and add containment to
   existing app-local file handlers;
2. switch app handlers to proxy execution-subsystem artifact byte endpoints and
   stop returning absolute file paths to the app.

### App Transport

Add bounded connect and response timeouts to the execution client. Use an async
HTTP client from FastAPI routes, or run the existing synchronous client in a
thread pool during migration. Async Agent submission should return quickly with
`queued`; Agent runtime timeout remains entirely execution-subsystem owned.

Composer `sync` and `async` labels must describe actual behavior. Status cards
must render `queued` separately from `running` and continue polling both.

## Result Shape

```ts
type NormalizedAgentResult = {
  status: "completed" | "partial" | "failed";
  summary: string;
  output_text?: string;
  reported_outputs: AgentReportedOutput[];
  artifacts: StoredAgentArtifactProjection[];
  operation_verification: OperationVerification[];
  provider_metadata: {
    backend: "codex_cli" | "openclaw_cli";
    timed_out: boolean;
    provider_state_access: "none" | "read" | "scoped_write";
    provider_state_labels: string[];
  };
  diagnostics: {
    primary?: AgentDiagnostic;
    secondary: AgentSecondaryDiagnostic[];
    failure_code?: string;
    failure_message?: string;
  };
};
```

Absolute provider, workspace, credential, and artifact-store paths are excluded
from the public shape.

## Error Handling

- Queue failure after persistence transitions the execution to `failed` with
  `AGENT_QUEUE_FAILED`.
- Restart reconciliation uses `AGENT_EXECUTION_INTERRUPTED`.
- Timeout uses `AGENT_TIMEOUT` and preserves bounded provider tails.
- Missing read evidence uses `AGENT_PROVIDER_EVIDENCE_MISSING`.
- Trusted verifier failure uses `AGENT_OPERATION_VERIFICATION_FAILED` when the
  required minimum cannot be met.
- Artifact persistence is secondary unless the artifact is required and the
  provider task otherwise succeeded.
- Cleanup failures are always secondary unless cleanup proves containment was
  violated, in which case the result fails closed.

## Testing Strategy

Unit tests cover state transitions, duplicate enqueue protection, restart
reconciliation, process-tree termination through fake descendant processes,
policy metadata, evidence ranking, diagnostics merging, artifact projection,
and path containment.

Provider tests inject fake supervisors and verifiers. No unit test launches real
Codex, OpenClaw, WSL, NotebookLM, or `taskkill.exe`.

Integration tests cover app submission, confirmation, queued/running polling,
terminal rendering, and artifact proxy authorization.

Opt-in live tests cover:

- Codex read-only NotebookLM listing;
- Codex NotebookLM source addition and report-generation acceptance;
- Codex timeout with no surviving Python descendants;
- OpenClaw read-only completion;
- OpenClaw required output creation and artifact persistence.

## Rollout

1. Land low-risk correctness and compatibility fixes.
2. Add process supervision before increasing Agent timeouts.
3. Add trusted verification while preserving legacy evidence fields.
4. Enable actual async mode behind `AGENT_ASYNC_EXECUTION_ENABLED`.
5. Move artifact bytes behind execution-subsystem scoped endpoints.
6. Enable the shared behavior for OpenClaw after Codex and OpenClaw regression
   suites pass.

## Non-Goals

- distributed workers or multi-instance leasing
- cross-session artifacts
- automatic cancellation UI
- arbitrary provider plugin loading
- Builder skill discovery or publication
- replacing the existing NotebookLM adapter

## Acceptance Criteria

- Contract acceptance criteria are automated where feasible.
- Existing synchronous Codex and OpenClaw behavior remains compatible.
- Async mode is not advertised as available until the queue is enabled.
- Only trusted verifiers emit `independently_verified`.
- Only persisted scoped inventory records produce artifact actions.
- Timeout tests prove descendant cleanup on supported platforms.
- App artifact handlers cannot serve or delete paths outside approved storage.
