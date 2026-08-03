# Agent Execution Lifecycle And Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Codex and OpenClaw Agent execution with authoritative evidence, complete process cleanup, truthful artifacts, real asynchronous execution, and scoped artifact byte access.

**Architecture:** Keep provider invocation in Codex and OpenClaw adapters, but move lifecycle, evidence authority, result finalization, and artifact serving into provider-neutral execution-subsystem components. Add a persisted single-instance Agent queue for the MVP and make the app poll normalized scoped status rather than hold long provider requests open.

**Tech Stack:** TypeScript, Fastify, Zod, Prisma/PostgreSQL, Node child processes, Python/FastAPI, React/Vitest, Node test runner, pytest.

## Global Constraints

- Normative contract: `docs/agent-execution-lifecycle-evidence-contract.md`.
- Design: `docs/superpowers/specs/2026-08-03-agent-execution-lifecycle-evidence-design.md`.
- Preserve `{app_id, session_id}` scope on execution, confirmation, logs, result, and artifacts.
- Keep `artifact_refs` session-scoped.
- Do not change `execute_skill` behavior.
- Do not expose provider, credential, workspace, or artifact-store absolute paths.
- Do not use provider text, provider-declared artifact IDs, or process exit zero as sufficient mutation evidence.
- Keep service authentication backward compatible and enable it in production configuration.
- Add no distributed queue dependency in this plan.
- Preserve the completed OpenClaw staging fix: use `wsl --exec`, direct
  argument-array commands, TypeScript canonical-path containment, Python byte
  writing, and `OPENCLAW_ARTIFACT_STAGING_FAILED`; do not restore dynamic
  staging through `bash -c`.

## Execution Status (2026-08-03)

- Milestones 1-5 are implemented and pass automated acceptance.
- Milestone 6 automated gates and live OpenClaw acceptance pass.
- Live Codex/NotebookLM acceptance is blocked by an expired or invalid local
  NotebookLM `default` profile. The failed mutation run was not automatically
  repeated because its partial external side-effect state is unknown.
- The corrected OpenClaw supervision wrapper retains the `openclaw` executable,
  uses `setsid --wait`, and writes the inner session leader PGID. Future process
  supervision changes must preserve both this wrapper and the corrected direct
  WSL staging path.

---

## Milestone 1: Result And Policy Correctness

### Task 1: Fix Shared Result Trust And Diagnostics

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-result-evaluator.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- Create: `ragenius_execution_subsystem/src/core/agents/agent-diagnostics.ts`
- Create: `ragenius_execution_subsystem/tests/agents/agent-diagnostics.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-cli-provider.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-result-evaluator.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`
- Modify: `ragenius_execution_subsystem/.agents/skills/ragenius-execution/SKILL.md`

**Interfaces:**
- Produces: `mergeAgentDiagnostics(primary, secondary): AgentDiagnostics`.
- Produces: `AgentProviderResult.reported_outputs` for untrusted provider claims.
- Guarantees: `AgentProviderResult.artifacts` contains only persisted artifact projections.

- [ ] **Step 1: Add failing diagnostics tests**

Cover these cases in `agent-diagnostics.test.ts`:

```ts
test("persistence failure does not replace provider authentication failure", () => {
  const result = mergeAgentDiagnostics(
    { code: "NOTEBOOKLM_AUTH_FAILED", message: "Authentication failed." },
    [{ stage: "persistence", code: "CODEX_OUTPUT_PERSIST_FAILED", message: "save failed" }]
  );
  assert.equal(result.primary?.code, "NOTEBOOKLM_AUTH_FAILED");
  assert.equal(result.secondary[0]?.code, "CODEX_OUTPUT_PERSIST_FAILED");
  assert.equal(result.failure_code, "NOTEBOOKLM_AUTH_FAILED");
});
```

Add provider tests proving a provider-declared `artifact_id` is returned under
`reported_outputs`, not `artifacts`, unless `persistOutput` returned the record.

- [ ] **Step 2: Run focused tests and verify failure**

```powershell
cd ragenius_execution_subsystem
npm test -- agent-diagnostics.test.ts codex-cli-provider.test.ts openclaw-cli-provider.test.ts
```

Expected: failures because diagnostics are overwritten and reported artifact IDs
are currently projected as stored artifacts.

- [ ] **Step 3: Add diagnostic types and merge function**

Implement:

```ts
export type AgentDiagnostic = { code: string; message: string; error_class?: string };
export type AgentSecondaryDiagnostic = {
  stage: "verification" | "persistence" | "cleanup" | "transport";
  code: string;
  message: string;
};
export function mergeAgentDiagnostics(
  primary: AgentDiagnostic | undefined,
  secondary: AgentSecondaryDiagnostic[]
): AgentDiagnostics;
```

Mirror the primary code/message to compatibility fields. Never promote a
secondary failure when a primary already exists.

- [ ] **Step 4: Separate reported outputs from stored artifacts**

Replace `stableReportedArtifacts()` with a projection that emits
`reported_outputs`. Append to `artifacts` only values returned by the configured
artifact persister. Apply the same rule to OpenClaw.

- [ ] **Step 5: Require process evidence for provider-backed reads**

Add evaluator tests where `agent_skill_hint = "notebooklm"`, turn status is
complete, final text is non-empty, and no relevant command succeeded. Require:

```ts
assert.equal(result.status, "failed");
assert.equal(result.diagnostics.primary?.code, "AGENT_PROVIDER_EVIDENCE_MISSING");
```

Keep local reasoning-only Codex prompts backward compatible.

- [ ] **Step 6: Repair the repository execution skill**

Make `SKILL.md` begin at byte zero with valid YAML frontmatter:

```markdown
---
name: ragenius-execution
description: Execute RAGenius Agent tasks using scoped inputs and declared outputs.
---
```

Keep its existing instruction body below the frontmatter.

- [ ] **Step 7: Run the milestone regression suite**

```powershell
npm test -- agent-diagnostics.test.ts codex-result-evaluator.test.ts codex-cli-provider.test.ts openclaw-cli-provider.test.ts execute-agent.test.ts
npm run typecheck
```

Expected: all focused tests pass and `execute-skill.test.ts` remains untouched.

- [ ] **Step 8: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents ragenius_execution_subsystem/tests/agents ragenius_execution_subsystem/.agents/skills/ragenius-execution/SKILL.md
git commit -m "fix(agent): preserve diagnostics and trust persisted artifacts"
```

### Task 2: Represent Provider State In Policy

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-policy.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/agent-policy.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

**Interfaces:**
- Extends: `AgentPolicyDecision.providerStateAccess` and `providerStateLabels`.
- Guarantees: provider-state metadata participates in the confirmation fingerprint.

- [ ] **Step 1: Add failing policy tests**

Test exact outcomes:

```ts
assert.equal(notebookRead.workspaceAccess, "none");
assert.equal(notebookRead.providerStateAccess, "scoped_write");
assert.deepEqual(notebookRead.providerStateLabels, ["notebooklm_profile:default"]);
assert.equal(plainCodex.providerStateAccess, "none");
```

Also test that `do not delete files` does not become destructive without a
structured delete operation, while `delete the file` remains destructive.

- [ ] **Step 2: Run tests and verify failure**

```powershell
npm test -- agent-policy.test.ts execute-agent.test.ts
```

- [ ] **Step 3: Extend policy and stable fingerprint serialization**

Add provider-state fields to the policy decision and the policy snapshot used by
confirmation. Emit labels, not absolute paths. Add bounded negation handling to
fallback keyword classification.

- [ ] **Step 4: Project provider-state metadata**

Codex NotebookLM emits `notebooklm_profile:<configured-profile>`. OpenClaw emits
`openclaw_agent_state`. Do not expose the resolved profile or WSL path.

- [ ] **Step 5: Run policy and confirmation tests**

```powershell
npm test -- agent-policy.test.ts confirmation-state-machine.test.ts execute-agent.test.ts codex-cli-provider.test.ts openclaw-cli-provider.test.ts
npm run typecheck
```

- [ ] **Step 6: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents ragenius_execution_subsystem/src/core/execution/execution-engine.ts ragenius_execution_subsystem/tests
git commit -m "feat(agent): classify scoped provider state access"
```

---

## Milestone 2: Complete Process Termination

### Completed Prerequisite: Argument-Safe OpenClaw Staging

Status: completed and verified before this milestone.

The OpenClaw staging regression was fixed in:

- `ragenius_execution_subsystem/src/core/agents/openclaw-workspace.ts`
- `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`

The fixed path uses `wsl --exec`, invokes `mkdir` and `readlink` with direct
argument arrays, validates the canonical parent in TypeScript, and writes
base64-decoded bytes through Python without shell redirection. Staging failures
are classified as `OPENCLAW_ARTIFACT_STAGING_FAILED` and prevent bridge
invocation.

Milestone 2 may replace process supervision underneath this path, but must not
replace its staging command construction, move containment back into a dynamic
shell script, or weaken its error classification. The verified staging behavior
is a regression constraint, not work to reimplement.

### Task 3: Add Cross-Platform Agent Process Supervision

**Files:**
- Create: `ragenius_execution_subsystem/scripts/agent_process_supervisor.js`
- Create: `ragenius_execution_subsystem/scripts/agent_process_supervisor.d.ts`
- Create: `ragenius_execution_subsystem/tests/agents/agent-process-supervisor.test.ts`
- Modify: `ragenius_execution_subsystem/scripts/codex_cli_bridge.js`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-cli-bridge.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-workspace.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-cli-protocol.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/openclaw-cli-bridge.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts`

**Interfaces:**
- Produces: `runSupervisedProcess(spec): Promise<SupervisedProcessResult>`.
- Consumes: executable, argument array, cwd, environment, timeout, output limit, and optional termination strategy.
- Preserves: `buildOpenClawWslExecArgs()` and direct argument-safe staging through
  `transferOpenClawInputViaWsl()`.

- [ ] **Step 1: Add fake descendant fixtures and failing tests**

Create test fixtures using `process.execPath` that spawn a long-lived child and
write parent/child PIDs to a temporary file. Assert timeout returns
`timed_out: true` and both PIDs cease to exist within the configured grace
period. Skip only the platform-specific assertion on unsupported CI platforms.

Extend the OpenClaw workspace regression test to assert that supervisor
integration still passes `--exec`, never routes staging through `bash -c`,
retains TypeScript canonical containment, and preserves
`OPENCLAW_ARTIFACT_STAGING_FAILED` before provider invocation.

- [ ] **Step 2: Run supervisor tests and verify failure**

```powershell
npm test -- agent-process-supervisor.test.ts
```

Expected: failure because no process supervisor exists.

- [ ] **Step 3: Implement bounded process supervision**

Use `spawn` with `shell: false`. On Windows, invoke:

```ts
spawn("taskkill.exe", ["/PID", String(pid), "/T", "/F"], { shell: false });
```

On native non-Windows execution, create a detached process group and signal
`-pid`. Keep stdout/stderr byte limits and a kill grace timeout. Resolve only
after close or the bounded grace period.

- [ ] **Step 4: Integrate Codex bridge**

Replace direct `spawn` timeout handling and `child.kill()` with
`runSupervisedProcess`. Preserve JSONL parsing and environment isolation.

- [ ] **Step 5: Integrate OpenClaw WSL termination**

Give each OpenClaw invocation a unique WSL-side process-group marker. On timeout,
terminate that group through an argument-safe WSL command, then terminate the
Windows `wsl.exe` tree. Preserve `buildOpenClawWslExecArgs()` and `--exec` for
all direct WSL commands. Do not build a shell command from user text, and do not
route artifact staging through the process-group shell wrapper.

- [ ] **Step 6: Run bridge and supervisor suites**

```powershell
npm test -- agent-process-supervisor.test.ts codex-cli-protocol.test.ts openclaw-cli-bridge.test.ts openclaw-workspace.test.ts openclaw-cli-provider.test.ts
npm run typecheck
```

Expected: process-tree tests pass and the real staging regression remains green:
contained paths stage successfully, canonical escapes fail before byte writing,
and staging failures do not invoke OpenClaw.

- [ ] **Step 7: Run an opt-in local timeout smoke**

Add a fake supervised command, not real NotebookLM, that spawns a Python child.
After timeout, verify no recorded PID survives. This smoke must not enumerate or
kill unrelated Python processes.

- [ ] **Step 8: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/scripts/agent_process_supervisor.* ragenius_execution_subsystem/scripts/codex_cli_bridge.js ragenius_execution_subsystem/src/core/agents/openclaw-cli-bridge.ts ragenius_execution_subsystem/tests/agents
git commit -m "fix(agent): terminate provider process trees on timeout"
```

---

## Milestone 3: Trusted Provider Verification

### Task 4: Move Independent Verification Outside Agent Transcripts

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agents/agent-operation-verifier.ts`
- Create: `ragenius_execution_subsystem/src/core/agents/notebooklm-operation-verifier.ts`
- Create: `ragenius_execution_subsystem/src/core/agents/agent-result-finalizer.ts`
- Create: `ragenius_execution_subsystem/tests/agents/notebooklm-operation-verifier.test.ts`
- Create: `ragenius_execution_subsystem/tests/agents/agent-result-finalizer.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-result-evaluator.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-result-evaluator.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-cli-provider.test.ts`

**Interfaces:**
- Produces: `AgentOperationVerifierRegistry.verify(input)`.
- Produces: `finalizeAgentResult(input): Promise<AgentProviderResult>`.
- Consumes: existing `NotebookLmAdapter` through dependency injection.

- [ ] **Step 1: Add failing evidence-authority tests**

Prove that a Codex transcript containing `list_sources` and an echoed source ID
reaches at most `provider_reported`. Prove that an injected trusted NotebookLM
verification record raises it to `independently_verified`.

- [ ] **Step 2: Add failing NotebookLM verifier tests**

Inject a fake adapter and cover:

```ts
test("verifies source ID through list_sources", ...);
test("rejects a source ID absent from the resolved notebook", ...);
test("polls a report task by stable external ID", ...);
test("returns bounded failure evidence when adapter lookup fails", ...);
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
npm test -- notebooklm-operation-verifier.test.ts agent-result-finalizer.test.ts codex-result-evaluator.test.ts
```

- [ ] **Step 4: Implement verifier interfaces and registry**

Use:

```ts
export interface AgentOperationVerifier {
  readonly id: string;
  supports(input: AgentVerificationInput): boolean;
  verify(input: AgentVerificationInput): Promise<TrustedOperationVerification[]>;
}
```

Registry output must identify `verifier: "execution_subsystem_adapter"` and
include `checked_at`. Redact and bound evidence summaries.

- [ ] **Step 5: Implement NotebookLM trusted checks**

Resolve the notebook from server-owned operation context. Use `list_sources` to
match a source ID and `poll_artifact_task` to check a report task ID. Do not let
the Agent supply a different notebook scope during verification.

- [ ] **Step 6: Implement shared result finalization**

Reconcile operation evidence, trusted verification, expected-output persistence,
diagnostics, and terminal status in one component. Both providers call it after
protocol parsing. Provider evaluators no longer emit independent evidence.

- [ ] **Step 7: Run provider-neutral and provider suites**

```powershell
npm test -- agent-result-finalizer.test.ts notebooklm-operation-verifier.test.ts codex-result-evaluator.test.ts codex-cli-provider.test.ts openclaw-cli-provider.test.ts execute-agent.test.ts
npm run typecheck
```

- [ ] **Step 8: Run the real Codex NotebookLM smoke**

Run `npm run smoke:codex-notebooklm` with explicit live-test environment. Assert
that source addition is independently verified by the adapter and report
generation is either provider-reported as started or independently verified as
ready. Do not require a new source mutation for a read-only listing smoke.

- [ ] **Step 9: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/agents
git commit -m "feat(agent): verify external operations outside agent transcripts"
```

---

## Milestone 4: Real Asynchronous Agent Execution

### Task 5: Add Persisted Queue State And Worker

**Files:**
- Modify: `ragenius_execution_subsystem/src/api/schemas/common-response.schema.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/prisma-execution-store.ts`
- Create: `ragenius_execution_subsystem/src/core/execution/agent-execution-queue.ts`
- Create: `ragenius_execution_subsystem/tests/execution/agent-execution-queue.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execution-store.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/prisma-execution-store.test.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`

**Interfaces:**
- Adds: execution status `queued`.
- Adds: conditional `ExecutionStore.transition()`.
- Produces: `AgentExecutionQueue.enqueue/start/stop/reconcileInterrupted`.

- [ ] **Step 1: Add failing store transition tests**

Cover `pending_confirmation -> queued`, `queued -> running`, terminal rejection,
scope mismatch, two workers racing to claim one job, and restart reconciliation.

- [ ] **Step 2: Add failing queue tests**

Use a deferred fake engine to prove enqueue returns before completion, status is
observable as queued/running, bounded concurrency is respected, and duplicate
enqueue does not invoke the engine twice.

- [ ] **Step 3: Run queue/store tests and verify failure**

```powershell
npm test -- agent-execution-queue.test.ts execution-store.test.ts prisma-execution-store.test.ts
```

- [ ] **Step 4: Add queued schema and atomic transitions**

Implement conditional updates in both stores. Add any required Prisma migration
without changing app/session uniqueness or confirmation tables.

- [ ] **Step 5: Implement the bounded queue**

Read configuration:

```text
AGENT_ASYNC_EXECUTION_ENABLED=false
AGENT_ASYNC_CONCURRENCY=1
```

Persist queued before adding to memory. Persist running only after an atomic
claim. On startup, fail interrupted records with `AGENT_EXECUTION_INTERRUPTED`.

- [ ] **Step 6: Run migration validation and tests**

```powershell
npx prisma validate
npx prisma generate
npm test -- agent-execution-queue.test.ts execution-store.test.ts prisma-execution-store.test.ts
npm run typecheck
```

- [ ] **Step 7: Commit the queue foundation**

```powershell
git add ragenius_execution_subsystem/src ragenius_execution_subsystem/tests/execution ragenius_execution_subsystem/prisma
git commit -m "feat(agent): add persisted asynchronous execution queue"
```

### Task 6: Route Async Submission And Confirmation Through The Queue

**Files:**
- Modify: `ragenius_execution_subsystem/src/api/routes/executions.routes.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/tests/api/execution-routes.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/confirmation-state-machine.test.ts`
- Modify: `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.test.jsx`

**Interfaces:**
- Async submit/confirm returns scoped `queued` execution immediately.
- App polls `queued` and `running` until terminal.

- [ ] **Step 1: Add failing execution-route tests**

Assert async submit and confirm return before a deferred provider resolves,
persist `queued`, and invoke the provider once. Assert duplicate confirmation
returns existing state and does not enqueue again.

- [ ] **Step 2: Add failing app client and UI tests**

Test bounded connect/response timeouts, transport error normalization, `queued`
lane rendering, polling continuation, and terminal status replacement.

- [ ] **Step 3: Run focused tests and verify failure**

```powershell
cd ragenius_execution_subsystem
npm test -- execution-routes.test.ts confirmation-state-machine.test.ts
cd ..\ragenius_app_skeleton
python -m pytest backend/tests/test_execution_subsystem_client.py backend/tests/test_chat_exec_routing.py -q
cd frontend
npm test -- App.test.jsx ExecutionLaneStatusCard.test.jsx
```

- [ ] **Step 4: Queue async route execution**

When `execution_options.mode` or normalized `context.execution_mode` is `async`
and the feature flag is enabled, persist/enqueue and return. Keep the synchronous
path unchanged. If the flag is disabled, reject async explicitly with
`AGENT_ASYNC_DISABLED`; do not silently run synchronously.

- [ ] **Step 5: Bound app transport and avoid event-loop blocking**

Configure separate connect and API response timeouts. Convert the execution
client to async HTTP or call it through FastAPI's thread-pool helper. Do not use
the Agent runtime timeout as the async submission response timeout.

- [ ] **Step 6: Render and poll queued state**

Show `Queued` separately from `Running`. Continue polling both. Use only scoped
status responses and normalized terminal results.

- [ ] **Step 7: Run end-to-end automated tests**

```powershell
cd ragenius_execution_subsystem
npm test
npm run typecheck
cd ..\ragenius_app_skeleton
python -m pytest backend/tests/test_execution_subsystem_client.py backend/tests/test_chat_exec_routing.py -q
cd frontend
npm test
npm run build
```

- [ ] **Step 8: Commit the async integration**

```powershell
git add ragenius_execution_subsystem/src ragenius_execution_subsystem/tests ragenius_app_skeleton/backend ragenius_app_skeleton/frontend/src
git commit -m "feat(agent): execute asynchronous requests through persisted queue"
```

---

## Milestone 5: Artifact Byte Isolation

### Task 7: Serve Agent Artifacts Through The Execution Subsystem

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts`
- Create: `ragenius_execution_subsystem/src/api/routes/artifacts.routes.ts`
- Create: `ragenius_execution_subsystem/tests/api/artifact-file-routes.test.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`
- Create: `ragenius_app_skeleton/backend/tests/test_session_artifact_proxy.py`
- Modify: `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.test.jsx`

**Interfaces:**
- Produces scoped execution API preview/download/delete operations by artifact ID.
- Removes app dependence on inventory `file_path` and `path`.

- [ ] **Step 1: Add failing containment tests**

Create records for a contained file, traversal path, symlink escape, missing
file, wrong app, and wrong session. Require 404-equivalent behavior for scope
mismatch and reject deletion outside the artifact root.

- [ ] **Step 2: Add failing app proxy tests**

Assert the app checks user/session ownership, forwards service authentication
and scope to the execution subsystem, streams safe response metadata, and never
calls `Path.unlink()` from inventory metadata.

- [ ] **Step 3: Run focused tests and verify failure**

```powershell
cd ragenius_execution_subsystem
npm test -- artifact-file-routes.test.ts
cd ..\ragenius_app_skeleton
python -m pytest backend/tests/test_session_artifact_proxy.py backend/tests/test_execution_subsystem_client.py -q
```

- [ ] **Step 4: Add artifact-store byte operations**

Resolve records under `{app_id, session_id, artifact_id}`, canonicalize beneath
the configured artifact root, reject escaping symlinks, and expose bounded
metadata for streaming. Delete the record and contained bytes atomically enough
that retry is idempotent.

- [ ] **Step 5: Add authenticated scoped artifact routes**

Implement preview, download, and delete routes behind existing service auth.
Do not return absolute paths in inventory or response JSON.

- [ ] **Step 6: Convert app handlers to proxies**

Retain current browser-facing app URLs, but proxy bytes and delete requests to
the execution subsystem after `_require_session_scope`. Remove direct
`FileResponse(Path(candidate_path))` and `Path.unlink()` behavior.

- [ ] **Step 7: Run artifact and UI regression tests**

```powershell
cd ragenius_execution_subsystem
npm test -- artifact-file-routes.test.ts agent-output-artifact-persister.test.ts
cd ..\ragenius_app_skeleton
python -m pytest backend/tests/test_session_artifact_proxy.py backend/tests/test_execution_subsystem_client.py -q
cd frontend
npm test -- ChatMessageCard.test.jsx ArtifactLibrary.test.jsx App.test.jsx
```

- [ ] **Step 8: Commit artifact isolation**

```powershell
git add ragenius_execution_subsystem/src ragenius_execution_subsystem/tests/api ragenius_app_skeleton/backend ragenius_app_skeleton/frontend/src/components
git commit -m "fix(artifacts): proxy scoped bytes through execution service"
```

---

## Milestone 6: Cross-Provider Acceptance

### Task 8: Prove Shared Semantics With Live Codex And OpenClaw

**Files:**
- Modify: `ragenius_execution_subsystem/scripts/smoke-codex-notebooklm-agent.ts`
- Modify: `ragenius_execution_subsystem/scripts/smoke-openclaw-agent.ts`
- Modify: `ragenius_execution_subsystem/package.json`
- Modify: `docs/agent-execution-lifecycle-evidence-contract.md`

**Interfaces:**
- Produces redacted live evidence for the shared acceptance criteria.

- [ ] **Step 1: Extend opt-in smoke assertions**

Codex smoke must assert queued/running observability in async mode, trusted
NotebookLM verification source, inventory-backed artifacts only, and no duplicate
side effect after repeated confirmation.

OpenClaw smoke must assert the same lifecycle and artifact projection semantics,
plus WSL required-output verification.

- [ ] **Step 2: Add timeout cleanup smoke**

Use an execution-owned fake descendant tree and assert no recorded PID survives.
Do not kill processes by executable name.

- [ ] **Step 3: Run all automated gates**

```powershell
cd ragenius_execution_subsystem
npx prisma validate
npm run lint
npm run typecheck
npm test
cd ..\ragenius_app_skeleton
python -m pytest backend/tests/test_execution_subsystem_client.py backend/tests/test_chat_exec_routing.py backend/tests/test_session_artifact_proxy.py -q
cd frontend
npm test
npm run build
```

- [ ] **Step 4: Run live Codex acceptance**

Enable only the documented Codex/NotebookLM real-smoke variables. Verify a
read-only notebook listing and the existing selected-artifact source/report flow.

- [ ] **Step 5: Run live OpenClaw acceptance**

Enable only the documented OpenClaw real-smoke variables. Verify one read-only
response and one required markdown output persisted as a scoped artifact.

- [ ] **Step 6: Record acceptance evidence**

Add an implementation status section to the contract containing test date,
platform, redacted execution IDs, and pass/fail outcomes. Do not include tokens,
cookies, absolute paths, or user artifact content.

- [ ] **Step 7: Commit acceptance evidence**

```powershell
git add ragenius_execution_subsystem/scripts ragenius_execution_subsystem/package.json docs/agent-execution-lifecycle-evidence-contract.md
git commit -m "test(agent): verify shared Codex and OpenClaw lifecycle"
```

---

## Final Acceptance Checklist

- [x] OpenClaw artifact staging uses `wsl --exec`, direct commands, TypeScript
  canonical containment, and actionable staging errors without dynamic
  `bash -c` staging.
- [ ] Async Agent submission returns before provider completion.
- [ ] Queued and running state are persisted and scoped.
- [ ] Duplicate confirmation cannot enqueue or execute twice.
- [ ] Restart reconciliation terminates stale lifecycle state truthfully.
- [ ] Timeout removes execution-owned descendants on Windows and WSL.
- [ ] Provider-backed reads require process evidence.
- [ ] Only execution-subsystem adapters emit independent verification.
- [ ] NotebookLM source and report checks use trusted adapter calls.
- [ ] Provider-reported output IDs never become RAGenius artifact actions.
- [ ] Required persisted outputs appear in scoped inventory.
- [ ] Primary diagnostics survive secondary verification and persistence failures.
- [ ] Provider-state access is distinct from user workspace access.
- [ ] Artifact preview, download, and delete cannot escape approved storage.
- [ ] Existing synchronous Codex and OpenClaw requests remain compatible.
- [ ] Tool and RAGenius skill execution regressions pass unchanged.
