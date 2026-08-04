# Codex Agent Confirmation, Artifact, And Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make confirmed Codex Agent-mode executions receive trusted authorization and selected artifacts, and prevent mutation requests from reporting completion without evidence that every required operation ran.

**Architecture:** The execution engine constructs an immutable provider context after policy validation and confirmation claim. Codex-specific modules stage resolved artifacts into an execution-scoped workspace, build the system-authored prompt, parse Codex JSONL, and reconcile structured operation evidence against the engine's operation plan. The app consumes only normalized execution status and evidence; it does not infer success from Codex text or process exit code.

**Tech Stack:** Node.js 20+, TypeScript 5.7, Zod 3, Fastify 5, Node test runner, Prisma 6, JavaScript Codex bridge process, Python/FastAPI app backend, React 18, Vitest, Testing Library.

## Execution Status

- Milestones 1 through 7 are implemented and covered by automated tests.
- Milestone 8 steps 1 through 3 are implemented. The live smoke script is present and the automated regression gates pass.
- Milestone 8 step 4 remains pending because it requires an explicitly opted-in live Codex CLI, NotebookLM account, target notebook, session, and selected artifact.
- Specification provenance and implementation commits remain pending until the live smoke succeeds. Milestone-by-milestone commits were intentionally skipped during inline execution in the existing dirty worktree.

## Global Constraints

- Normative specification: `docs/superpowers/specs/2026-08-02-codex-agent-confirmation-artifact-execution-design.md`.
- Preserve the public provider-neutral `execute_agent` request schema; clients cannot submit trusted authorization, resolved artifacts, operation plans, or policy fingerprints.
- Artifact references remain scoped to the exact `app_id` and `session_id`.
- Never pass original artifact-store paths to Codex; prompts contain only verified workspace-relative paths.
- A zero Codex process exit is necessary but insufficient for mutation completion.
- A confirmed execution cannot obtain a second confirmation for the same planned operations.
- Do not change RAGenius skill execution behavior or add Codex assertions to `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`.
- Do not redesign OpenClaw behavior. Its provider may ignore new optional context fields until a separate refactor, but existing OpenClaw tests must remain green.
- Do not persist confirmation tokens, secrets, authorization headers, or unbounded child-process output.
- Default `CODEX_RUN_ROOT` to `storage/codex-runs`, default retention to 24 hours, and cap persisted stdout/stderr tails at 16 KiB each.
- Replace `--dangerously-bypass-approvals-and-sandbox` with explicit `--sandbox workspace-write`; enable workspace-write network access only when trusted policy says `network_access = "allowlisted"`.
- Preserve all unrelated dirty worktree changes. Execute this plan only from a reviewed baseline commit or an isolated worktree created with `superpowers:using-git-worktrees`.

## File Structure

### New Execution-Subsystem Files

- `ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts`: trusted internal context and operation-plan types.
- `ragenius_execution_subsystem/src/core/agents/agent-operation-planner.ts`: deterministic server-side operation planning and policy fingerprint support.
- `ragenius_execution_subsystem/src/core/agents/codex-workspace.ts`: local Codex run workspace creation, staging, verification, and cleanup.
- `ragenius_execution_subsystem/src/core/agents/codex-prompt-builder.ts`: system-authored authorization, operation, artifact, and final-result instructions.
- `ragenius_execution_subsystem/src/core/agents/codex-result-evaluator.ts`: reconciliation of planned operations with parsed Codex evidence.
- `ragenius_execution_subsystem/scripts/codex_cli_protocol.js`: bounded line-by-line Codex JSONL parser.
- `ragenius_execution_subsystem/scripts/codex_cli_protocol.d.ts`: TypeScript declarations for protocol tests.
- `ragenius_execution_subsystem/tests/agents/agent-operation-planner.test.ts`: operation-plan and fingerprint tests.
- `ragenius_execution_subsystem/tests/agents/codex-workspace.test.ts`: safe staging and cleanup tests.
- `ragenius_execution_subsystem/tests/agents/codex-cli-protocol.test.ts`: JSONL event extraction tests.
- `ragenius_execution_subsystem/tests/agents/codex-prompt-builder.test.ts`: trusted prompt projection tests.
- `ragenius_execution_subsystem/tests/agents/codex-result-evaluator.test.ts`: semantic status-mapping tests.
- `ragenius_execution_subsystem/scripts/smoke-codex-notebooklm-agent.ts`: opt-in live acceptance smoke test.

### Modified Execution-Subsystem Files

- `ragenius_execution_subsystem/src/core/agents/agent-provider.ts`: require trusted provider context in the provider interface.
- `ragenius_execution_subsystem/src/core/agents/codex-cli-types.ts`: define bridge protocol, staged input, operation evidence, and normalized result fields.
- `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`: orchestrate staging, prompt projection, bridge invocation, evidence evaluation, and cleanup.
- `ragenius_execution_subsystem/src/core/agents/codex-cli-bridge.ts`: forward workspace and bounded bridge settings.
- `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`: create immutable plans, include them in confirmation snapshots, resolve Codex inputs, and construct trusted context.
- `ragenius_execution_subsystem/src/core/execution/confirmation-service.ts`: expose the server-recorded confirmation time through `ApprovedConfirmation`.
- `ragenius_execution_subsystem/src/api/routes/executions.routes.ts`: pass claimed confirmation time into the engine.
- `ragenius_execution_subsystem/src/config/env.ts`: validate Codex run-root, retention, output-limit, and sandbox settings.
- `ragenius_execution_subsystem/src/config/provider-config.ts`: project the new settings into `CodexCliProviderConfig`.
- `ragenius_execution_subsystem/src/app.ts`: inject `AgentArtifactResolver` and Codex provider dependencies.
- `ragenius_execution_subsystem/scripts/codex_cli_bridge.js`: use the protocol parser, execution workspace, explicit sandbox, and structured bridge result.
- `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`: engine confirmation/context and normalization integration tests.
- `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`: Codex configuration tests.
- `ragenius_execution_subsystem/.env.example`: document safe Codex runtime defaults.

### Modified App Files

- `ragenius_app_skeleton/frontend/src/App.jsx`: produce status preview text from normalized Codex status and operation evidence.
- `ragenius_app_skeleton/frontend/src/App.test.jsx`: test failed, partial, processing, and verified Codex previews.
- `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx`: render authorization, staged inputs, commands, and operation verification.
- `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.test.jsx`: test inspector evidence and secret omission.
- `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx`: distinguish generation started from ready completion.
- `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.test.jsx`: test normalized status labels.
- `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`: prove the app forwards public artifact refs but cannot manufacture trusted fields.

---

## Milestone 1: Trusted Context And Immutable Operation Plan

### Task 1: Add Provider Context Types And Deterministic Planning

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts`
- Create: `ragenius_execution_subsystem/src/core/agents/agent-operation-planner.ts`
- Create: `ragenius_execution_subsystem/tests/agents/agent-operation-planner.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-provider.ts`

**Interfaces:**
- Consumes: `ExecuteAgentRequest`, `AgentPolicyDecision`, `ResolvedAgentArtifact`, and `AgentExpectedOutput`.
- Produces: `AgentProviderExecutionContext`, `AgentOperationPlanItem`, `createAgentOperationPlan(request, policy)`, and `fingerprintAgentPolicy(snapshot)`.

- [ ] **Step 1: Write failing operation-plan tests**

Cover these exact cases:

```ts
test("plans NotebookLM source add and report generation separately", () => {
  const plan = createAgentOperationPlan(notebookLmRequest, externalWritePolicy);
  assert.deepEqual(plan.map((item) => item.operation_id), [
    "notebooklm_source_add",
    "notebooklm_report_generate"
  ]);
  assert.equal(plan.every((item) => item.required), true);
});

test("plans one verifiable generic mutation for an unknown external write", () => {
  const plan = createAgentOperationPlan(genericMutationRequest, externalWritePolicy);
  assert.deepEqual(plan, [{
    operation_id: "agent_external_write",
    kind: "external_write",
    description: genericMutationRequest.agent_query,
    required: true,
    minimum_verification: "provider_reported"
  }]);
});

test("read-only requests receive one process-observed read operation", () => {
  assert.equal(createAgentOperationPlan(readRequest, readPolicy)[0]?.kind, "read");
});

test("fingerprint changes when the operation plan changes", () => {
  assert.notEqual(fingerprintAgentPolicy(firstSnapshot), fingerprintAgentPolicy(secondSnapshot));
});
```

- [ ] **Step 2: Run the planner test and verify it fails**

Run from `ragenius_execution_subsystem`:

```powershell
npm test -- agent-operation-planner.test.ts
```

Expected: build failure because the new modules and exports do not exist.

- [ ] **Step 3: Define the trusted internal types**

Add these exact core shapes to `agent-provider-context.ts`:

```ts
export type AgentOperationPlanItem = {
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

export type AgentProviderExecutionContext = {
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

Change `AgentProvider.execute` to require the third argument:

```ts
execute(
  request: ExecuteAgentRequest,
  policy: AgentPolicyDecision,
  context: AgentProviderExecutionContext
): Promise<AgentProviderResult>;
```

- [ ] **Step 4: Implement deterministic planning and stable fingerprinting**

Use fixed operation IDs. For `agent_skill_hint === "notebooklm"`, recognize `add` plus `source` as `notebooklm_source_add`, and `report`, `study guide`, `briefing`, `slide deck`, or `video` with `create` or `generate` as a second generation operation. Build generic operations from the policy risk class when no known rule matches. Stable serialization must recursively sort object keys before SHA-256 hashing.

Use these minimum levels: `notebooklm_source_add` requires `independently_verified`; NotebookLM generation requires `provider_reported` because accepted/processing is a valid started state; generic external writes require `provider_reported`; workspace writes and reads require `process_observed`. For a read-only turn, a successful terminal turn with a valid final agent message counts as process-observed read evidence even when no shell command was needed.

```ts
export function fingerprintAgentPolicy(snapshot: Record<string, unknown>): string {
  return createHash("sha256").update(stableStringify(snapshot), "utf8").digest("hex");
}
```

- [ ] **Step 5: Run focused tests and typecheck**

```powershell
npm test -- agent-operation-planner.test.ts
npm run typecheck
```

Expected: all planner tests pass and TypeScript identifies every provider implementation that still needs the new context signature.

- [ ] **Step 6: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts ragenius_execution_subsystem/src/core/agents/agent-operation-planner.ts ragenius_execution_subsystem/src/core/agents/agent-provider.ts ragenius_execution_subsystem/tests/agents/agent-operation-planner.test.ts
git commit -m "feat(execution): define trusted agent operation context"
```

---

## Milestone 2: Confirmation Propagation And Artifact Resolution

### Task 2: Construct Trusted Context In The Execution Engine

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/confirmation-service.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/executions.routes.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

**Interfaces:**
- Consumes: `createAgentOperationPlan`, `fingerprintAgentPolicy`, `AgentArtifactResolver.resolve`, and the claimed confirmation record.
- Produces: one `AgentProviderExecutionContext` for each provider invocation; Codex receives resolved artifacts while OpenClaw retains its current provider-specific artifact path during this plan.

- [ ] **Step 1: Add failing engine tests**

Add provider spies that capture the third argument and assert:

```ts
assert.equal(capturedContext.authorization.state, "confirmed");
assert.equal(capturedContext.authorization.confirmed_at, "2026-08-03T01:02:03.000Z");
assert.equal(capturedContext.operation_plan[0]?.operation_id, "notebooklm_source_add");
assert.equal(capturedContext.resolved_artifacts[0]?.artifact_id, "artifact_123");
assert.equal(capturedContext.expected_outputs.length, 1);
```

Also test that public `context` keys named `authorization`, `operation_plan`, and `resolved_artifacts` do not alter captured trusted values; policy-plan mismatch blocks provider invocation; and artifact resolution failure blocks provider invocation.

- [ ] **Step 2: Run the engine test and verify it fails**

```powershell
npm test -- execute-agent.test.ts
```

Expected: failures because the engine currently passes only `{ executionId }` and does not resolve Codex artifacts.

- [ ] **Step 3: Carry the claimed timestamp into `ApprovedConfirmation`**

Extend the internal interface only:

```ts
export interface ApprovedConfirmation {
  confirmationId: string;
  confirmedAt: string;
  policySnapshot: Record<string, unknown>;
}
```

In `executions.routes.ts`, set `confirmedAt` from `claim.record.consumedAt` and reject a claimed record without that timestamp as an invalid confirmation state.

- [ ] **Step 4: Generate the plan before issuing confirmation**

In the agent branch of `ExecutionEngine.execute`, construct `operationPlan` before `agentPolicySnapshot`, include it in the snapshot, and compute the fingerprint from that complete snapshot:

```ts
const operationPlan = createAgentOperationPlan(request, agentPolicy);
const agentPolicySnapshot = {
  backend: request.agent_backend,
  operation_plan: operationPlan,
  // existing policy fields remain here
};
const policyFingerprint = fingerprintAgentPolicy(agentPolicySnapshot);
```

The existing stable snapshot comparison then rejects query, policy, or operation-plan drift before provider invocation.

- [ ] **Step 5: Resolve Codex artifact refs after confirmation and before invocation**

Inject this dependency into `ExecutionEngine`:

```ts
resolveAgentArtifacts?: (input: AgentArtifactResolverInput) => Promise<ResolvedAgentArtifact[]>;
```

Call it only after confirmation validation. For Codex, resolve `request.artifact_refs ?? []` with exact app/session/backend scope. Map resolver errors to `CODEX_ARTIFACT_RESOLUTION_FAILED` while retaining the original cause code in `details.cause_code`. Do not resolve bytes during the initial `pending_confirmation` response.

- [ ] **Step 6: Build and pass trusted context**

```ts
const providerContext: AgentProviderExecutionContext = {
  execution_id: executionId,
  authorization: {
    state: options?.approvedConfirmation ? "confirmed" : "not_required",
    permission_scope: agentPolicy.permissionScope,
    policy_fingerprint: policyFingerprint,
    ...(options?.approvedConfirmation
      ? { confirmed_at: options.approvedConfirmation.confirmedAt }
      : {})
  },
  operation_plan: operationPlan,
  resolved_artifacts: resolvedArtifacts,
  expected_outputs: request.expected_outputs ?? []
};
const agentResult = await provider.execute(request, agentPolicy, providerContext);
```

Update the OpenClaw provider signature to accept and ignore the additional trusted fields without changing its current behavior. Wire the existing `AgentArtifactResolver` into `ExecutionEngine` in `app.ts`.

- [ ] **Step 7: Run confirmation, artifact, and OpenClaw regression tests**

```powershell
npm test -- execute-agent.test.ts
npm test -- confirmation-state-machine.test.ts
npm test -- agent-artifact-resolver.test.ts
npm test -- openclaw-cli-provider.test.ts
```

Expected: confirmation invokes the provider once with trusted context, resolution is session-scoped, and OpenClaw behavior remains unchanged.

- [ ] **Step 8: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/execution/execution-engine.ts ragenius_execution_subsystem/src/core/execution/confirmation-service.ts ragenius_execution_subsystem/src/api/routes/executions.routes.ts ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts ragenius_execution_subsystem/tests/execution/execute-agent.test.ts
git commit -m "feat(execution): propagate confirmed agent context"
```

---

## Milestone 3: Execution-Scoped Codex Workspace

### Task 3: Stage And Verify Selected Artifacts Safely

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agents/codex-workspace.ts`
- Create: `ragenius_execution_subsystem/tests/agents/codex-workspace.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-types.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
- Modify: `ragenius_execution_subsystem/.env.example`

**Interfaces:**
- Consumes: `ResolvedAgentArtifact[]`, `execution_id`, and Codex runtime config.
- Produces: `createCodexRunWorkspace`, `stageCodexArtifacts`, `cleanupCodexRunWorkspaces`, and `CodexStagedArtifact[]`.

- [ ] **Step 1: Write failing workspace tests**

Test inline UTF-8 staging, file-backed byte copying, hash/size verification, metadata-only handling, generated filenames, cross-root rejection, traversal rejection, symlink rejection, and retention cleanup that never removes the current run.

```ts
assert.match(staged[0]!.workspace_relative_path!, /^inputs\/artifact_123-/);
assert.equal("workspace_absolute_path" in staged[0]!, false);
assert.equal(staged[0]!.sha256, expectedSha256);
```

- [ ] **Step 2: Run workspace tests and verify they fail**

```powershell
npm test -- codex-workspace.test.ts
```

Expected: build failure because `codex-workspace.ts` does not exist.

- [ ] **Step 3: Define the staged artifact type**

```ts
export interface CodexStagedArtifact {
  artifact_id: string;
  role: "source" | "reference" | "attachment" | "context";
  reuse_mode: "file_backed" | "inline_text" | "binary_payload" | "metadata_only";
  display_name: string;
  media_type?: string;
  size_bytes?: number;
  sha256?: string;
  workspace_relative_path?: string;
}
```

Keep absolute paths in a private workspace return type used by the provider, never in normalized results.

- [ ] **Step 4: Implement workspace creation and staging**

Create `<runRoot>/<executionId>/inputs` and `outputs` using `fs.mkdir({ recursive: true })`. Validate `executionId` with `/^[A-Za-z0-9_-]+$/`. Generate destination names from artifact ID plus a sanitized basename. Use `lstat` to reject symlink source and destination paths. Resolve every destination and verify it starts with the resolved run root plus `path.sep`. Read/write bytes, then recompute SHA-256 and size from the staged file.

Map errors to these provider-facing codes:

```ts
"CODEX_ARTIFACT_STAGING_FAILED"
"CODEX_STAGED_ARTIFACT_VERIFICATION_FAILED"
```

- [ ] **Step 5: Add bounded runtime configuration**

Add and validate:

```text
CODEX_RUN_ROOT=storage/codex-runs
CODEX_RUN_RETENTION_HOURS=24
CODEX_MAX_OUTPUT_BYTES=16384
CODEX_CLI_SANDBOX_MODE=workspace-write
```

`CODEX_RUN_RETENTION_HOURS` and `CODEX_MAX_OUTPUT_BYTES` must be positive integers. `CODEX_CLI_SANDBOX_MODE` accepts only `read-only` or `workspace-write`; production code must not accept `danger-full-access` or a bypass flag.

- [ ] **Step 6: Run workspace/config tests and typecheck**

```powershell
npm test -- codex-workspace.test.ts
npm test -- runtime-config.test.ts
npm run typecheck
```

Expected: all tests pass, and staged normalized metadata contains no absolute artifact-store path.

- [ ] **Step 7: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents/codex-workspace.ts ragenius_execution_subsystem/src/core/agents/codex-cli-types.ts ragenius_execution_subsystem/src/config/env.ts ragenius_execution_subsystem/src/config/provider-config.ts ragenius_execution_subsystem/tests/agents/codex-workspace.test.ts ragenius_execution_subsystem/tests/config/runtime-config.test.ts ragenius_execution_subsystem/.env.example
git commit -m "feat(codex): add isolated artifact workspace"
```

---

## Milestone 4: Structured Codex Prompt And JSONL Protocol

### Task 4: Build Trusted Prompts And Parse CLI Events

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agents/codex-prompt-builder.ts`
- Create: `ragenius_execution_subsystem/tests/agents/codex-prompt-builder.test.ts`
- Create: `ragenius_execution_subsystem/scripts/codex_cli_protocol.js`
- Create: `ragenius_execution_subsystem/scripts/codex_cli_protocol.d.ts`
- Create: `ragenius_execution_subsystem/tests/agents/codex-cli-protocol.test.ts`
- Modify: `ragenius_execution_subsystem/scripts/codex_cli_bridge.js`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-types.ts`

**Interfaces:**
- Consumes: trusted authorization, immutable operation plan, staged artifacts, public request text, and Codex JSONL lines.
- Produces: `buildCodexPrompt(input)` and `parseCodexJsonl(stdout, limits)` returning terminal state, final message, commands, errors, usage, and truncation flags.

- [ ] **Step 1: Write failing prompt tests**

Assert that a confirmed prompt contains the server scope, fingerprint, operation IDs, and staged relative paths; a not-required prompt never says confirmed; public context cannot inject an authorization block; and original artifact paths/secrets are absent.

```ts
assert.match(prompt, /State: confirmed/);
assert.match(prompt, /notebooklm_source_add/);
assert.match(prompt, /inputs\/artifact_123-/);
assert.doesNotMatch(prompt, /storage\/artifacts/);
assert.doesNotMatch(prompt, /confirmation_[A-Za-z0-9]+/);
```

- [ ] **Step 2: Write failing JSONL parser tests**

Use literal fixtures for `thread.started`, `turn.started`, command item start/completion, agent-message completion, `turn.completed`, `turn.failed`, malformed lines, and output truncation. Assert line-by-line parsing rather than whole-stream `JSON.parse`.

```ts
const parsed = parseCodexJsonl(jsonl, { maxOutputBytes: 16384 });
assert.equal(parsed.turn_status, "completed");
assert.equal(parsed.command_events.length, 1);
assert.equal(parsed.final_message, structuredFinalMessage);
assert.equal(parsed.raw_exit_code, 0);
```

- [ ] **Step 3: Run both tests and verify they fail**

```powershell
npm test -- codex-prompt-builder.test.ts
npm test -- codex-cli-protocol.test.ts
```

Expected: build failure because the prompt and protocol modules do not exist.

- [ ] **Step 4: Implement the system-authored prompt**

The final instruction must demand one JSON object matching this shape and no Markdown fence:

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
  errors: Array<{ code: string; message: string }>;
};
```

Separate the authorization and artifact sections from `User request:`. Tell Codex that unknown operation IDs are unauthorized, all required IDs must appear once, and confirmed operations must not trigger another confirmation request.

- [ ] **Step 5: Implement bounded JSONL parsing**

Parse each non-empty line independently. Retain only bounded command text, exit code, stdout summary, and stderr summary for command events. Redact case-insensitive keys and text patterns for `authorization`, `token`, `api_key`, `cookie`, and bearer values. Set `turn_status = "failed"` on `turn.failed` even if the process exits zero. Do not treat the entire JSONL stream as `final_message`.

- [ ] **Step 6: Replace bridge prompt/parsing and sandbox bypass**

In `codex_cli_bridge.js`:

```js
args.push("--cd", request.workspace_absolute_path);
args.push("--sandbox", request.sandbox_mode);
if (request.policy?.network_access === "allowlisted") {
  args.push("-c", "sandbox_workspace_write.network_access=true");
}
```

Remove automatic insertion of `--dangerously-bypass-approvals-and-sandbox`. Continue passing the prompt through stdin. Return a structured bridge response containing parsed protocol fields, not a synthesized success based on raw stdout.

- [ ] **Step 7: Run protocol, environment, and bridge tests**

```powershell
npm test -- codex-prompt-builder.test.ts
npm test -- codex-cli-protocol.test.ts
npm test -- codex-cli-environment.test.ts
npm run typecheck
```

Expected: JSONL is parsed line-by-line, TLS isolation remains intact, and no generated command includes the bypass flag.

- [ ] **Step 8: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents/codex-prompt-builder.ts ragenius_execution_subsystem/tests/agents/codex-prompt-builder.test.ts ragenius_execution_subsystem/scripts/codex_cli_protocol.js ragenius_execution_subsystem/scripts/codex_cli_protocol.d.ts ragenius_execution_subsystem/tests/agents/codex-cli-protocol.test.ts ragenius_execution_subsystem/scripts/codex_cli_bridge.js ragenius_execution_subsystem/src/core/agents/codex-cli-types.ts
git commit -m "feat(codex): add trusted prompt and JSONL protocol"
```

---

## Milestone 5: Semantic Evidence And Authoritative Status

### Task 5: Reconcile Planned Operations With Codex Results

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agents/codex-result-evaluator.ts`
- Create: `ragenius_execution_subsystem/tests/agents/codex-result-evaluator.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-types.ts`

**Interfaces:**
- Consumes: `AgentOperationPlanItem[]`, parsed bridge result, and structured final `CodexAgentTaskResult`.
- Produces: `evaluateCodexResult(input): CodexNormalizedResult` and `OperationVerification[]`.

- [ ] **Step 1: Write the status-matrix tests**

Cover the ordered contract rules:

```ts
test("exit zero plus pending confirmation after approval fails", ...);
test("exit zero plus no mutation evidence fails", ...);
test("missing required operation fails when none succeeded", ...);
test("one of two required operations maps to partial", ...);
test("all required provider-reported operations complete", ...);
test("accepted async operation reports generation started", ...);
test("independently verified async operation reports ready", ...);
test("read-only final text remains completed", ...);
test("turn.failed overrides structured completed", ...);
test("unknown operation id contributes no evidence", ...);
```

- [ ] **Step 2: Run evaluator tests and verify they fail**

```powershell
npm test -- codex-result-evaluator.test.ts
```

Expected: build failure because the evaluator does not exist.

- [ ] **Step 3: Parse and validate the final agent JSON**

Use Zod or an equivalent strict type guard. A malformed final result may supply read-only text but must set `final_json_status = "invalid"` and cannot prove a mutation. Missing required operation IDs become `not_run`; duplicate planned IDs make the final result invalid.

- [ ] **Step 4: Implement evidence-level calculation**

Use this exact ordering:

```ts
const evidenceRank = {
  none: 0,
  process_observed: 1,
  provider_reported: 2,
  independently_verified: 3
} as const;
```

A matching successful command can establish `process_observed`. A non-empty stable `external_id` establishes `provider_reported`. A provider verification record with matching operation and external IDs establishes `independently_verified`. Free-form `evidence` text alone cannot exceed `process_observed`.

Derive NotebookLM independent verification only from ordered command events. For source creation, a successful later `list-sources` or source-status command must contain the exact source `external_id` in its bounded output. For report readiness, a successful later artifact-status, list-artifacts, or wait command must contain the exact artifact/job `external_id` and a terminal-ready status. A model statement such as `source exists` or `report complete` does not independently verify anything.

- [ ] **Step 5: Implement ordered top-level status mapping**

Return the specification error codes exactly:

```ts
"CODEX_FINAL_RESULT_INVALID"
"CODEX_UNEXPECTED_CONFIRMATION_REQUEST"
"CODEX_REQUIRED_OPERATION_NOT_RUN"
"CODEX_OPERATION_PARTIAL"
"CODEX_OPERATION_VERIFICATION_FAILED"
```

For `accepted` or `processing` with a stable external ID, use top-level `completed` only when the plan's minimum level is met, and force summary wording to `Generation started; external output is still processing.` Never use `ready` wording until independent verification succeeds.

- [ ] **Step 6: Run evaluator tests and typecheck**

```powershell
npm test -- codex-result-evaluator.test.ts
npm run typecheck
```

Expected: all status-matrix cases pass.

- [ ] **Step 7: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents/codex-result-evaluator.ts ragenius_execution_subsystem/tests/agents/codex-result-evaluator.test.ts ragenius_execution_subsystem/src/core/agents/codex-cli-types.ts
git commit -m "feat(codex): require semantic operation evidence"
```

---

## Milestone 6: Codex Provider Integration

### Task 6: Orchestrate Workspace, Bridge, Evaluation, And Cleanup

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-bridge.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Create: `ragenius_execution_subsystem/tests/agents/codex-cli-provider.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

**Interfaces:**
- Consumes: trusted provider context, Codex workspace functions, prompt builder, bridge protocol, and result evaluator.
- Produces: `AgentProviderResult` with authoritative `status`, `summary`, `staged_inputs`, `operation_verification`, `provider_metadata`, and bounded diagnostics.

- [ ] **Step 1: Write failing provider orchestration tests**

Use injected fakes and assert this order:

```text
create workspace -> stage artifacts -> build prompt -> invoke bridge -> evaluate -> cleanup
```

Test that bridge failure still cleans up; staging failure never invokes the bridge; the bridge receives the unique workspace as `cwd`; normalized results contain no absolute path; and an exit-zero `pending_confirmation` result becomes failed.

- [ ] **Step 2: Run provider tests and verify they fail**

```powershell
npm test -- codex-cli-provider.test.ts
```

Expected: failures because Codex provider currently forwards the raw request directly to the bridge.

- [ ] **Step 3: Add injectable Codex provider dependencies**

```ts
type CodexCliProviderDependencies = {
  createWorkspace: typeof createCodexRunWorkspace;
  stageArtifacts: typeof stageCodexArtifacts;
  buildPrompt: typeof buildCodexPrompt;
  executeBridge: CodexCliBridgeExecutor;
  evaluateResult: typeof evaluateCodexResult;
  cleanupWorkspaces: typeof cleanupCodexRunWorkspaces;
};
```

Default every dependency in production; inject fakes in tests.

- [ ] **Step 4: Implement orchestration and normalized metadata**

The provider must return:

```ts
{
  backend: "codex_cli",
  status,
  summary,
  activated_skills,
  staged_inputs,
  operation_verification,
  artifacts,
  provider_metadata: {
    thread_id,
    turn_status,
    raw_exit_code,
    confirmation_state: context.authorization.state,
    policy_fingerprint: context.authorization.policy_fingerprint,
    command_count,
    successful_command_count,
    final_json_status
  },
  diagnostics
}
```

`diagnostics.stdout_tail` and `stderr_tail` are already bounded/redacted by the bridge protocol module.

- [ ] **Step 5: Preserve execution-engine authority**

Keep `ExecutionEngine` behavior:

```ts
const providerStatus = agentResult.status ?? "completed";
```

but make Codex provider always set `status`. Add an engine test proving a failed Codex semantic result persists and returns top-level `failed`, while read-only completion remains backward compatible.

- [ ] **Step 6: Run focused and full execution-subsystem tests**

```powershell
npm test -- codex-cli-provider.test.ts
npm test -- execute-agent.test.ts
npm test -- openclaw-cli-provider.test.ts
npm test
```

Expected: the full execution-subsystem suite passes, including unchanged `execute-skill.test.ts`.

- [ ] **Step 7: Commit the milestone**

```powershell
git add ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts ragenius_execution_subsystem/src/core/agents/codex-cli-bridge.ts ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/agents/codex-cli-provider.test.ts ragenius_execution_subsystem/tests/execution/execute-agent.test.ts
git commit -m "feat(codex): integrate verified agent execution"
```

---

## Milestone 7: App Rendering And Inspector Evidence

### Task 7: Render Only Normalized Codex State

**Files:**
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.test.jsx`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`

**Interfaces:**
- Consumes: existing app execution payload containing `result.status`, `result.summary`, `result.operation_verification`, `result.staged_inputs`, and `result.provider_metadata`.
- Produces: user-facing `Confirmation required`, `Failed`, `Partially completed`, `Generation started`, and `Completed` states plus inspector evidence.

- [ ] **Step 1: Add failing preview and status-card tests**

Assert these exact outcomes:

```ts
expect(failedPreview).toBe("Codex failed: Required operation was not run.");
expect(partialPreview).toContain("Codex partially completed");
expect(processingPreview).toContain("Generation started");
expect(verifiedPreview).toContain("Codex completed");
```

Ensure process exit code zero with normalized `status: "failed"` still displays failure.

- [ ] **Step 2: Add failing inspector tests**

Render a Codex result and assert visible confirmation state, policy fingerprint prefix, staged relative path, operation status, verification level, external ID, bounded command count, and failure code. Assert that `confirmation_id`, bearer tokens, and absolute artifact paths are absent.

- [ ] **Step 3: Run frontend tests and verify they fail**

Run from `ragenius_app_skeleton/frontend`:

```powershell
npm test -- App.test.jsx ExecutionInspector.test.jsx ExecutionLaneStatusCard.test.jsx
```

Expected: current UI lacks processing and operation-evidence rendering.

- [ ] **Step 4: Update preview and lane-state resolution**

Resolve status from the top-level execution result first and nested provider result second. Do not read `raw_exit_code` to determine the label. When any required operation has `status` equal to `accepted` or `processing`, show `Generation started`; show `Completed` only when the normalized summary/status says complete and no required operation remains processing.

- [ ] **Step 5: Add inspector evidence sections**

Add Codex tabs or groups for:

```text
Authorization: state, permission scope, fingerprint prefix
Inputs: artifact ID, role, reuse mode, workspace-relative path, hash verification
Operations: operation ID, status, verification level, external ID, evidence
Diagnostics: turn status, command counts, final JSON status, failure code
```

Use normalized fields only. Keep the existing raw tab for already-sanitized app payloads.

- [ ] **Step 6: Verify the app client remains provider-neutral**

Extend `test_execution_subsystem_client.py` to assert public payload forwarding for `artifact_refs` and `expected_outputs`, and absence of `authorization`, `resolved_artifacts`, `operation_plan`, and `policy_fingerprint` at the request root.

- [ ] **Step 7: Run frontend and backend focused tests**

```powershell
cd frontend
npm test -- App.test.jsx ExecutionInspector.test.jsx ExecutionLaneStatusCard.test.jsx
cd ..
python -m pytest backend/tests/test_execution_subsystem_client.py -q
```

Expected: all focused app tests pass.

- [ ] **Step 8: Commit the milestone**

```powershell
git add ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/App.test.jsx ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx ragenius_app_skeleton/frontend/src/components/ExecutionInspector.test.jsx ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.test.jsx ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py
git commit -m "feat(app): render verified Codex execution state"
```

---

## Milestone 8: Live NotebookLM Acceptance And Regression Gate

### Task 8: Prove The Original Failure Is Fixed End To End

**Files:**
- Create: `ragenius_execution_subsystem/scripts/smoke-codex-notebooklm-agent.ts`
- Modify: `ragenius_execution_subsystem/package.json`
- Modify: `docs/superpowers/specs/2026-08-02-codex-agent-confirmation-artifact-execution-design.md`

**Interfaces:**
- Consumes: a running execution subsystem, valid Codex CLI login, valid NotebookLM profile, one session-scoped reusable artifact, and notebook title `Testing`.
- Produces: machine-readable live evidence for confirmation, staged input, source creation, report-generation start, and final status semantics.

- [ ] **Step 1: Add an opt-in live smoke script**

Require `CODEX_NOTEBOOKLM_REAL_SMOKE=1`; otherwise exit successfully with a skip message. Read these required variables:

```text
RAGENIUS_EXECUTION_BASE_URL=http://127.0.0.1:3001
RAGENIUS_SMOKE_APP_ID=<existing app id>
RAGENIUS_SMOKE_SESSION_ID=<existing session id>
RAGENIUS_SMOKE_ARTIFACT_ID=<ready artifact in that session>
RAGENIUS_SMOKE_NOTEBOOK_TITLE=Testing
```

The script must submit the exact task, confirm once, poll terminal state, and print redacted JSON:

```text
Use notebooklm. Add the selected artifact as a source to the Testing notebook, then create a study report answering all questions in that notebook.
```

- [ ] **Step 2: Assert contract outcomes in the smoke script**

Fail the process unless all assertions hold:

```ts
assert.equal(initial.status, "pending_confirmation");
assert.equal(terminal.result.provider_metadata.confirmation_state, "confirmed");
assert.equal(terminal.result.staged_inputs.length, 1);
assert.match(terminal.result.staged_inputs[0].workspace_relative_path, /^inputs\//);
assert.equal(sourceOperation.level, "independently_verified");
assert.ok(sourceOperation.external_id);
assert.ok(reportOperation.external_id);
assert.ok(["accepted", "processing", "completed"].includes(reportOperation.status));
```

Also issue a duplicate confirmation request and assert it does not invoke Codex or repeat either external side effect.

- [ ] **Step 3: Add the npm command and run all automated gates**

Add:

```json
"smoke:codex-notebooklm": "tsx scripts/smoke-codex-notebooklm-agent.ts"
```

Run:

```powershell
cd ragenius_execution_subsystem
npm run lint
npm run typecheck
npm test
cd ..\ragenius_app_skeleton\frontend
npm test
npm run build
cd ..
python -m pytest backend/tests/test_execution_subsystem_client.py backend/tests/test_chat_exec_routing.py -q
```

Expected: every automated gate passes.

- [ ] **Step 4: Run the real smoke test with explicit opt-in**

```powershell
$env:CODEX_NOTEBOOKLM_REAL_SMOKE = "1"
$env:RAGENIUS_EXECUTION_BASE_URL = "http://127.0.0.1:3001"
$env:RAGENIUS_SMOKE_APP_ID = "2302c77b-3d82-4650-bd15-e0ff9c0faab7"
$env:RAGENIUS_SMOKE_SESSION_ID = "<current test session id>"
$env:RAGENIUS_SMOKE_ARTIFACT_ID = "<ready artifact id from that session>"
$env:RAGENIUS_SMOKE_NOTEBOOK_TITLE = "Testing"
npm run smoke:codex-notebooklm
```

Expected: the selected source appears in NotebookLM with a stable source ID; report generation returns a stable artifact/job ID; processing is labeled started rather than ready; duplicate confirmation does not repeat work.

- [ ] **Step 5: Record implementation provenance in the specification**

Change the spec status from `Proposed normative addendum` to `Implemented` only after Step 4 passes. Add the implementation commit IDs and the smoke-test date, but do not include tokens, local absolute artifact paths, NotebookLM cookies, or raw session content.

- [ ] **Step 6: Commit the acceptance milestone**

```powershell
git add ragenius_execution_subsystem/scripts/smoke-codex-notebooklm-agent.ts ragenius_execution_subsystem/package.json docs/superpowers/specs/2026-08-02-codex-agent-confirmation-artifact-execution-design.md
git commit -m "test(codex): add live NotebookLM acceptance smoke"
```

---

## Final Acceptance Checklist

- [ ] Public clients cannot manufacture trusted confirmation or artifact-resolution state.
- [ ] Operation plans are generated before confirmation and included in the claimed policy snapshot.
- [ ] Confirmed authorization reaches Codex exactly once with a server fingerprint and timestamp.
- [ ] Selected session artifacts are resolved after confirmation, copied into the Codex run workspace, and hash-verified.
- [ ] Codex receives only workspace-relative artifact paths.
- [ ] Codex JSONL is parsed line-by-line with bounded, redacted diagnostics.
- [ ] The dangerous sandbox bypass flag is absent from Codex invocation.
- [ ] Exit zero plus duplicate confirmation, missing operation, or absent mutation evidence is not `completed`.
- [ ] Partial operation success returns `partial` with per-operation evidence.
- [ ] NotebookLM asynchronous generation is shown as started until independent readiness verification.
- [ ] Execution Inspector exposes normalized evidence without secrets or original storage paths.
- [ ] Full execution-subsystem, app frontend, and focused app backend tests pass.
- [ ] Real NotebookLM smoke test proves source creation and report-generation start.
