# OpenClaw Agent Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenClaw as an `execute_agent` backend that can be launched from `ragenius_app_skeleton` Execution Composer and executed safely by `ragenius_execution_subsystem`.

**Architecture:** `ragenius_app_skeleton` remains the user-facing chat/composer/session layer. `ragenius_execution_subsystem` owns OpenClaw provider dispatch, WSL invocation, staging, verification, and normalized results. `ragenius_builder` is not part of Phase 1 runtime execution.

**Tech Stack:** TypeScript, Fastify, Zod, Node child process APIs, Python, Pydantic, React, Vitest, Node test runner.

---

## Reference Documents

- `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-execution-contract.md`
- `D:/GitHub/Codex-RAGenius-System/docs/openclaw-agent-execution-integration-contract.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-provider-design.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/docs/openclaw-execution-composer-design.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-cli-test-results-2026-06-13.md`

## Test Placement Decision

Do not add new OpenClaw coverage to `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts` unless an existing assertion in that file must be updated for compatibility.

Reason:

- the file name suggests skill execution, but it currently also contains broad route and Codex `execute_agent` coverage
- it already has unrelated in-progress Gmail MCP test edits in the working tree
- adding OpenClaw tests there would increase merge/conflict risk and make the file more overloaded

Use dedicated test files instead:

- `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts` for multi-backend execution engine and schema dispatch
- `ragenius_execution_subsystem/tests/agents/openclaw-options.test.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-cli-bridge.test.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts`
- `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`

## Milestone 1: Execution Subsystem Schema and Provider Dispatch

### Task 1: Add Agent Backend Schema Support

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/schemas/execution-request.schema.ts`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

- [ ] **Step 1: Add failing schema tests**

Add tests near the existing `execute_agent` schema tests:

```ts
it("accepts openclaw_cli as an execute_agent backend", () => {
  const parsed = executionRequestSchema.parse({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "sess_001",
    agent_backend: "openclaw_cli",
    agent_query: "Inspect the approved content."
  });

  assert.equal(parsed.request_type, "execute_agent");
  assert.equal(parsed.agent_backend, "openclaw_cli");
});

it("rejects unknown execute_agent backends", () => {
  assert.throws(() =>
    executionRequestSchema.parse({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "unknown_agent",
      agent_query: "Inspect the approved content."
    })
  );
});
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-agent.test.ts
```

Expected: the OpenClaw schema test fails because `agent_backend` only accepts `codex_cli`.

- [ ] **Step 3: Implement the schema change**

Change:

```ts
agent_backend: z.literal("codex_cli"),
```

to:

```ts
export const agentBackendSchema = z.enum(["codex_cli", "openclaw_cli"]);

agent_backend: agentBackendSchema,
```

- [ ] **Step 4: Run the test again**

Run:

```powershell
npm test -- execute-agent.test.ts
```

Expected: schema tests pass; existing Codex tests still pass.

### Task 2: Introduce a Shared Agent Provider Interface

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/agents/agent-provider.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

- [ ] **Step 1: Add dispatch tests**

Add a test that injects a fake OpenClaw provider:

```ts
it("dispatches openclaw_cli agent requests to the OpenClaw provider", async () => {
  const openclawProvider = {
    backend: "openclaw_cli" as const,
    async execute() {
      return {
        status: "completed" as const,
        summary: "OpenClaw completed.",
        output_text: "OpenClaw response.",
        artifacts: [],
        provider_metadata: {
          backend: "openclaw_cli",
          provider_name: "OpenClaw",
          invocation_mode: "wsl_cli",
          wsl_distro: "OpenClawGateway",
          openclaw_command: "openclaw",
          openclaw_agent_id: "main",
          openclaw_session_key: "ragenius:app_001:sess_001:execution_test",
          execution_mode: "read_only",
          expected_output_count: 0,
          required_output_count: 0,
          verified_output_count: 0,
          json_parse_status: "parsed",
          raw_exit_code: 0,
          timed_out: false,
          stdout_truncated: false,
          stderr_truncated: false
        },
        verification_results: [],
        diagnostics: {
          stdout_truncated: false,
          stderr_truncated: false,
          redactions_applied: true
        },
        raw: { exit_code: 0 }
      };
    }
  };

  const engine = new ExecutionEngine({
    agentProviders: new Map([["openclaw_cli", openclawProvider]])
  });

  const result = await engine.execute({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "sess_001",
    agent_backend: "openclaw_cli",
    agent_query: "Reply with OK."
  });

  assert.equal(result.status, "completed");
  assert.equal((result.result as Record<string, unknown>).backend, "openclaw_cli");
});
```

- [ ] **Step 2: Run the failing dispatch test**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- execute-agent.test.ts
```

Expected: TypeScript fails because `agentProviders` and the shared provider interface do not exist.

- [ ] **Step 3: Create `agent-provider.ts`**

Create:

```ts
import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { AgentPolicyDecision } from "./agent-policy.js";

export type AgentBackend = "codex_cli" | "openclaw_cli";

export type AgentProviderResult = {
  status?: "completed" | "failed";
  summary?: string;
  output_text?: string;
  artifacts?: unknown[];
  provider_metadata?: Record<string, unknown>;
  verification_results?: unknown[];
  diagnostics?: Record<string, unknown>;
  raw?: Record<string, unknown>;
  [key: string]: unknown;
};

export interface AgentProvider {
  readonly backend: AgentBackend;
  execute(
    request: ExecuteAgentRequest,
    policy: AgentPolicyDecision
  ): Promise<AgentProviderResult>;
}
```

- [ ] **Step 4: Adapt Codex provider**

Make `CodexCliProvider` implement `AgentProvider` and add:

```ts
readonly backend = "codex_cli" as const;
```

- [ ] **Step 5: Update `ExecutionEngine` constructor**

Replace the single `codexCliProvider` field with:

```ts
private readonly agentProviders: Map<string, AgentProvider>;
```

Constructor option:

```ts
agentProviders?: Map<string, AgentProvider>;
codexCliProvider?: CodexCliProvider;
```

Default:

```ts
const codexCliProvider = options?.codexCliProvider ?? new CodexCliProvider(...);
this.agentProviders =
  options?.agentProviders ?? new Map([[codexCliProvider.backend, codexCliProvider]]);
```

- [ ] **Step 6: Update dispatch**

Replace:

```ts
const agentResult = await this.codexCliProvider.execute(request, agentPolicy);
```

with:

```ts
const provider = this.agentProviders.get(request.agent_backend);
if (!provider) {
  throw new AppError({
    code: "UNKNOWN_AGENT_BACKEND",
    message: `Unknown agent backend: ${request.agent_backend}`,
    errorClass: "validation",
    httpStatus: 400,
    details: { backend: request.agent_backend },
    recoverable: false,
    suggestedAction: "Use a supported agent backend."
  });
}
const agentResult = await provider.execute(request, agentPolicy);
```

Use `provider.backend` for metadata provider ids instead of hardcoded `codex_cli`.

- [ ] **Step 7: Run tests**

Run:

```powershell
npm test -- execute-agent.test.ts
```

Expected: Codex tests and OpenClaw dispatch test pass.

### Task 3: Make Execution Store Backend-Aware

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/execution/execution-store.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

- [ ] **Step 1: Add failing persisted id tests**

Add:

```ts
it("persists backend-aware agent skill ids", () => {
  assert.equal(
    persistedSkillIdForRequest({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Inspect content."
    }),
    "openclaw_cli"
  );

  assert.equal(
    persistedSkillIdForRequest({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "codex_cli",
      agent_query: "Use NotebookLM.",
      agent_skill_hint: "notebooklm"
    }),
    "codex_cli:notebooklm"
  );
});
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
npm test -- execute-agent.test.ts
```

Expected: OpenClaw case fails because store hardcodes `codex_cli`.

- [ ] **Step 3: Implement backend-aware id**

Change helper logic to:

```ts
function persistedAgentSkillIdForRequest(request: ExecuteAgentRequest): string {
  const backend = String(request.agent_backend || "").trim();
  const hint = String(request.agent_skill_hint || "").trim();
  return hint ? `${backend}:${hint}` : backend;
}
```

- [ ] **Step 4: Run test**

Run:

```powershell
npm test -- execute-agent.test.ts
```

Expected: tests pass.

## Milestone 2: OpenClaw Provider Core With Mocked Bridge

### Task 4: Add OpenClaw Types and Option Normalization

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/agents/openclaw-cli-types.ts`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/agents/openclaw-options.ts`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/agents/openclaw-options.test.ts`

- [ ] **Step 1: Write option normalization tests**

Create `openclaw-options.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { normalizeOpenClawOptions } from "../../src/core/agents/openclaw-options.js";

test("normalizes read-only OpenClaw options", () => {
  const options = normalizeOpenClawOptions({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Explain this briefly."
    },
    executionId: "execution_001"
  });

  assert.equal(options.execution_mode, "read_only");
  assert.equal(options.expected_outputs.length, 0);
});

test("generates default output for ambiguous approved-content output requests", () => {
  const options = normalizeOpenClawOptions({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Prepare a reusable markdown summary.",
      context: {
        approved_content: { approved_content_id: "ac_123", revision_id: "rev_1" }
      }
    },
    executionId: "execution_001"
  });

  assert.equal(options.execution_mode, "output_required");
  assert.equal(options.expected_outputs.length, 1);
  assert.equal(options.expected_outputs[0].output_id, "openclaw_answer");
  assert.equal(options.expected_outputs[0].required, true);
});

test("rejects unsafe workspace relative paths", () => {
  assert.throws(() =>
    normalizeOpenClawOptions({
      request: {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Write output.",
        context: {
          openclaw: {
            expected_outputs: [
              {
                output_id: "bad",
                purpose: "answer",
                display_name: "bad.md",
                media_type: "text/markdown",
                required: true,
                workspace_relative_path: "../bad.md",
                persist_as_artifact: true
              }
            ]
          }
        }
      },
      executionId: "execution_001"
    })
  );
});
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- openclaw-options.test.ts
```

Expected: fails because files do not exist.

- [ ] **Step 3: Add OpenClaw types**

Implement the exact interfaces from `ragenius_execution_subsystem/docs/openclaw-provider-design.md`.

- [ ] **Step 4: Add `normalizeOpenClawOptions`**

Implement:

```ts
export function normalizeOpenClawOptions(input: {
  request: ExecuteAgentRequest;
  executionId: string;
}): Required<Pick<OpenClawProviderOptions, "execution_mode" | "staged_inputs" | "expected_outputs">>
  & OpenClawProviderOptions {
  // Parse request.context?.openclaw, validate ids and paths,
  // classify read_only/output_required, generate default output when required.
}
```

Use these detection terms for output-required:

```ts
const outputTerms = [
  "create", "write", "export", "save", "generate",
  "produce", "transform", "convert", "prepare"
];
```

- [ ] **Step 5: Run tests**

Run:

```powershell
npm test -- openclaw-options.test.ts
```

Expected: tests pass.

### Task 5: Add WSL Bridge Process Wrapper

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/agents/openclaw-cli-bridge.ts`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/agents/openclaw-cli-bridge.test.ts`

- [ ] **Step 1: Write bridge tests with fake spawn**

Create tests that assert argv construction, truncation, and timeout behavior. Use dependency injection for spawn:

```ts
test("builds OpenClaw argv without shell interpolation", async () => {
  const calls: unknown[] = [];
  const result = await executeOpenClawCliBridge({
    config: {
      wslDistro: "OpenClawGateway",
      command: "openclaw",
      agentId: "main",
      timeoutMs: 120000,
      maxStdoutBytes: 262144,
      maxStderrBytes: 65536
    },
    sessionKey: "ragenius:app:sess:exec",
    prompt: "Reply OK",
    spawnProcess: async (command, args) => {
      calls.push({ command, args });
      return {
        exitCode: 0,
        stdout: JSON.stringify({ status: "ok", result: { finalAssistantVisibleText: "OK" } }),
        stderr: "",
        timedOut: false
      };
    }
  });

  assert.deepEqual(calls[0], {
    command: "wsl",
    args: [
      "-d",
      "OpenClawGateway",
      "openclaw",
      "agent",
      "--agent",
      "main",
      "--session-key",
      "ragenius:app:sess:exec",
      "--message",
      "Reply OK",
      "--json"
    ]
  });
  assert.equal(result.exitCode, 0);
});
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
npm test -- openclaw-cli-bridge.test.ts
```

Expected: fails because bridge does not exist.

- [ ] **Step 3: Implement bridge**

Implement `executeOpenClawCliBridge` with:

- argv-based spawn
- stdout/stderr capture
- tail truncation
- timeout flag support
- JSON parse helper returning parse status

- [ ] **Step 4: Run bridge tests**

Run:

```powershell
npm test -- openclaw-cli-bridge.test.ts
```

Expected: tests pass without invoking real WSL.

### Task 6: Add Workspace Staging and Verification Helpers

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/agents/openclaw-workspace.ts`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts`

- [ ] **Step 1: Write verification tests**

Create tests for safe paths, missing output failure, verified output success, and hash mismatch:

```ts
test("rejects unsafe workspace paths", () => {
  assert.throws(() => assertSafeWorkspaceRelativePath("../secret.txt"));
  assert.throws(() => assertSafeWorkspaceRelativePath("/absolute.txt"));
  assert.equal(assertSafeWorkspaceRelativePath("outputs/result.md"), "outputs/result.md");
});

test("marks required missing output as failed", async () => {
  const result = await verifyOpenClawOutputs({
    workspaceRoot: "/home/openclaw/.openclaw/workspace",
    expectedOutputs: [
      {
        output_id: "out",
        purpose: "answer",
        display_name: "result.md",
        media_type: "text/markdown",
        required: true,
        workspace_relative_path: "outputs/result.md",
        persist_as_artifact: true
      }
    ],
    inspectFile: async () => ({ exists: false })
  });

  assert.equal(result[0].verified, false);
  assert.equal(result[0].failure_code, "missing_output");
});
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
npm test -- openclaw-workspace.test.ts
```

Expected: helper module missing.

- [ ] **Step 3: Implement helpers**

Implement:

```ts
export function assertSafeWorkspaceRelativePath(path: string): string;
export function buildWorkspaceAbsolutePath(root: string, relativePath: string): string;
export async function verifyOpenClawOutputs(input: VerifyOpenClawOutputsInput): Promise<OpenClawVerificationResult[]>;
export async function stageBinaryInputWithVerifiedBase64(input: StageBinaryInput): Promise<StageFileResult>;
```

Use injected file inspectors/transports for unit tests so real WSL is not required.

- [ ] **Step 4: Run workspace tests**

Run:

```powershell
npm test -- openclaw-workspace.test.ts
```

Expected: tests pass.

### Task 7: Implement OpenClaw Provider With Mocked Bridge

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`

- [ ] **Step 1: Write provider tests**

Tests must cover:

- read-only completed run
- missing required output fails
- verified required output completes
- top-level OpenClaw JSON `status = ok` is not enough when output missing
- diagnostics include truncation flags

Example:

```ts
test("fails output-required run when required output is missing despite ok JSON", async () => {
  const provider = new OpenClawCliProvider({
    enabled: true,
    wslDistro: "OpenClawGateway",
    command: "openclaw",
    agentId: "main",
    workspaceRoot: "/home/openclaw/.openclaw/workspace",
    timeoutMs: 120000,
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ok", summary: "completed", result: {} }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: { status: "ok", summary: "completed", result: {} },
      jsonParseStatus: "parsed"
    }),
    verifyOutputs: async () => [
      {
        output_id: "openclaw_answer",
        workspace_relative_path: "outputs/result.md",
        workspace_absolute_path: "/home/openclaw/.openclaw/workspace/outputs/result.md",
        required: true,
        exists: false,
        verified: false,
        failure_code: "missing_output",
        failure_message: "Required output was not created."
      }
    ]
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Prepare a reusable markdown summary.",
      context: { openclaw: { execution_mode: "output_required" } }
    },
    fakeAgentPolicy("agent_workspace_write")
  );

  assert.equal(result.status, "failed");
  assert.equal(result.diagnostics?.failure_code, "missing_output");
});
```

- [ ] **Step 2: Run failing provider tests**

Run:

```powershell
npm test -- openclaw-cli-provider.test.ts
```

Expected: provider module missing.

- [ ] **Step 3: Implement provider**

Provider must:

- implement `AgentProvider`
- normalize options
- generate session key from app/session/execution id
- build prompt
- call bridge
- verify outputs
- return `OpenClawProviderResult`

- [ ] **Step 4: Run provider tests**

Run:

```powershell
npm test -- openclaw-cli-provider.test.ts
```

Expected: tests pass.

### Task 8: Wire OpenClaw Config and App Construction

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/env.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/provider-config.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/app.ts`
- Create or modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/config/openclaw-runtime-config.test.ts`

- [ ] **Step 1: Add runtime config test**

Extend readiness/runtime config assertions to include:

```ts
assert.equal(response.json().checks.runtime_config.providers.openClaw.enabled, false);
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
npm test -- openclaw-runtime-config.test.ts
```

Expected: runtime config lacks OpenClaw provider.

- [ ] **Step 3: Add env/config fields**

Add:

```ts
OPENCLAW_CLI_ENABLED
OPENCLAW_WSL_DISTRO
OPENCLAW_CLI_COMMAND
OPENCLAW_AGENT_ID
OPENCLAW_WORKSPACE_ROOT
OPENCLAW_DEFAULT_TIMEOUT_MS
```

Default `OPENCLAW_CLI_ENABLED` to `false`.

- [ ] **Step 4: Wire `OpenClawCliProvider` in `app.ts`**

Build an agent provider map:

```ts
const codexProvider = new CodexCliProvider(runtimeConfig.providers.codexCli);
const openClawProvider = new OpenClawCliProvider(runtimeConfig.providers.openClaw);
const agentProviders = new Map([
  [codexProvider.backend, codexProvider],
  [openClawProvider.backend, openClawProvider]
]);
```

Pass `agentProviders` into `ExecutionEngine`.

- [ ] **Step 5: Run subsystem tests**

Run:

```powershell
npm test
```

Expected: all execution subsystem tests pass.

## Milestone 3: App Backend Routing

### Task 9: Extend Exec Router for OpenClaw

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/exec_router.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`

- [ ] **Step 1: Add parser tests**

Add:

```python
def test_parse_exec_openclaw_turn():
    decision = parse_exec_turn('@exec openclaw "Reply with OK."')

    assert decision.is_exec_turn is True
    assert decision.command == "openclaw"
    assert decision.agent_backend == "openclaw_cli"
    assert decision.agent_query == "Reply with OK."


def test_parse_exec_async_openclaw_turn():
    decision = parse_exec_turn('@exec async openclaw "Reply with OK."')

    assert decision.command == "openclaw"
    assert decision.execution_mode == "async"
    assert decision.agent_backend == "openclaw_cli"


def test_parse_exec_openclaw_missing_request():
    decision = parse_exec_turn("@exec openclaw")

    assert decision.is_exec_turn is True
    assert decision.command == "openclaw"
    assert "Missing OpenClaw request" in str(decision.error)
```

- [ ] **Step 2: Run failing backend tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton
python -m pytest backend/tests/test_chat_exec_routing.py -q
```

Expected: fails because `agent_backend` is missing and `openclaw` is unsupported.

- [ ] **Step 3: Add `agent_backend` field**

Update `ExecRouteDecision`:

```python
agent_backend: str | None = None
```

- [ ] **Step 4: Add OpenClaw branch**

After Codex branch or by sharing helper logic:

```python
if command == "openclaw":
    try:
        _agent_skill_hint, agent_query = _parse_agent_query(rest)
    except Exception as exc:
        return ExecRouteDecision(
            is_exec_turn=True,
            command="openclaw",
            execution_mode=execution_mode,
            raw_args=rest,
            error=f"Invalid exec arguments: {exc}",
        )
    if not agent_query:
        return ExecRouteDecision(
            is_exec_turn=True,
            command="openclaw",
            execution_mode=execution_mode,
            raw_args=rest,
            error='Missing OpenClaw request. Use \'@exec openclaw "<request>"\'.',
        )
    parsed_args = {"agent_backend": "openclaw_cli"}
    if execution_mode:
        parsed_args["execution_mode"] = execution_mode
    return ExecRouteDecision(
        is_exec_turn=True,
        command="openclaw",
        agent_backend="openclaw_cli",
        execution_mode=execution_mode,
        agent_query=agent_query,
        raw_args=rest,
        parsed_args=parsed_args,
    )
```

- [ ] **Step 5: Run parser tests**

Run:

```powershell
python -m pytest backend/tests/test_chat_exec_routing.py -q
```

Expected: parser tests pass; existing Codex tests pass.

### Task 10: Make App Execution Client Backend-Aware

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`

- [ ] **Step 1: Add client payload test**

Add a monkeypatch test that captures the payload and asserts:

```python
assert captured_payload["request_type"] == "execute_agent"
assert captured_payload["agent_backend"] == "openclaw_cli"
assert captured_payload["agent_query"] == "Reply with OK."
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest backend/tests/test_chat_exec_routing.py -q
```

Expected: payload is hardcoded to `codex_cli`.

- [ ] **Step 3: Update `submit_agent` signature**

Change:

```python
def submit_agent(...):
```

to:

```python
def submit_agent(
    self,
    *,
    session_id: str,
    app_id: str,
    agent_query: str,
    agent_backend: str = "codex_cli",
    agent_skill_hint: str | None = None,
    approved_content_id: str | None = None,
    approved_revision_id: str | None = None,
    context_payload: dict[str, Any] | None = None,
    require_confirmation: bool = False,
) -> dict[str, Any]:
```

Set:

```python
"agent_backend": agent_backend,
```

- [ ] **Step 4: Run backend tests**

Run:

```powershell
python -m pytest backend/tests/test_chat_exec_routing.py -q
```

Expected: client and existing Codex tests pass.

### Task 11: Generalize App Agent Handler

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`

- [ ] **Step 1: Add OpenClaw chat routing test**

Add:

```python
def test_exec_openclaw_turn_submits_agent_execution(monkeypatch):
    captured = {}

    class FakeClient:
        def submit_agent(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_openclaw_123",
                "result": {
                    "backend": "openclaw_cli",
                    "summary": "OpenClaw completed."
                }
            }

    monkeypatch.setattr("app.main.ExecutionSubsystemClient", lambda: FakeClient())

    response = client.post(
        "/chat",
        json={
            "app_id": "app_001",
            "session_id": "sess_001",
            "user_id": "user_001",
            "user_query": '@exec openclaw "Reply with OK."',
        },
    )

    payload = response.get_json()
    assert captured["agent_backend"] == "openclaw_cli"
    assert captured["agent_query"] == "Reply with OK."
    assert payload["execution_override"]["command"] == "openclaw"
    assert payload["execution_override"]["target_id"] == "openclaw_cli"
    assert payload["session_lane_state"]["execution_lane"]["latest_agent_backend"] == "openclaw_cli"
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest backend/tests/test_chat_exec_routing.py -q
```

Expected: app backend has no OpenClaw handler.

- [ ] **Step 3: Generalize `_handle_exec_codex_turn`**

Preferred change:

```python
def _handle_exec_agent_turn(..., agent_backend: str, command: str):
    ...
    submit_result = execution_client.submit_agent(
        session_id=session_id,
        app_id=app_id,
        agent_backend=agent_backend,
        agent_query=decision.agent_query or "",
        agent_skill_hint=decision.agent_skill_hint,
        approved_content_id=approved_content_id,
        approved_revision_id=approved_revision_id,
        context_payload=context,
        require_confirmation=require_confirmation,
    )
```

Route:

```python
if decision.command in {"codex", "openclaw"}:
    agent_backend = decision.agent_backend or ("openclaw_cli" if decision.command == "openclaw" else "codex_cli")
    return _handle_exec_agent_turn(..., agent_backend=agent_backend, command=decision.command)
```

- [ ] **Step 4: Add lane state field**

Set:

```python
execution_lane["latest_agent_backend"] = agent_backend
```

Set `latest_execution_request_skill_id` to:

```python
f"{agent_backend}:{agent_skill_hint}" if agent_skill_hint else agent_backend
```

- [ ] **Step 5: Run backend tests**

Run:

```powershell
python -m pytest backend/tests/test_chat_exec_routing.py -q
```

Expected: Codex and OpenClaw routing tests pass.

## Milestone 4: Frontend Composer and Command Generation

### Task 12: Update `buildExecCommand` for OpenClaw

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] **Step 1: Add command-building tests**

Add:

```jsx
it("builds an openclaw agent command", () => {
  const command = buildExecCommand({
    commandKind: "agent",
    targetId: "openclaw_cli",
    args: { request: "Reply with OK." },
    executionMode: "sync"
  });

  expect(command).toBe('@exec openclaw "Reply with OK."');
});

it("builds an async openclaw agent command", () => {
  const command = buildExecCommand({
    commandKind: "agent",
    targetId: "openclaw_cli",
    args: { request: "Reply with OK." },
    executionMode: "async"
  });

  expect(command).toBe('@exec async openclaw "Reply with OK."');
});
```

- [ ] **Step 2: Run failing frontend tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- App.test.jsx
```

Expected: OpenClaw command tests fail because agent commands always serialize to Codex.

- [ ] **Step 3: Implement command branch**

In `buildExecCommand`:

```jsx
if (commandKind === "agent") {
  const requestText = String(args.request || "").trim();
  const skillHint = String(args.skillHint || "").trim();
  const execPrefix = executionMode === "async" ? "@exec async" : "@exec";
  if (targetId === "openclaw_cli") {
    return `${execPrefix} openclaw "${requestText.replace(/"/g, '\\"')}"`.trim();
  }
  if (skillHint) {
    return `${execPrefix} codex use ${skillHint} "${requestText.replace(/"/g, '\\"')}"`.trim();
  }
  return `${execPrefix} codex "${requestText.replace(/"/g, '\\"')}"`.trim();
}
```

- [ ] **Step 4: Run tests**

Run:

```powershell
npm test -- App.test.jsx
```

Expected: new OpenClaw tests and existing Codex tests pass.

### Task 13: Add Agent Backend Selector to Composer

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`

- [ ] **Step 1: Add Composer tests**

Add tests:

```jsx
it("defaults agent backend to Codex CLI", async () => {
  render(<ExecutionComposer {...defaultProps} />);

  await userEvent.selectOptions(screen.getByLabelText("Mode"), "agent");

  expect(screen.getByLabelText("Agent Backend")).toHaveValue("codex_cli");
});

it("submits OpenClaw agent backend", async () => {
  const onSubmit = vi.fn();
  render(<ExecutionComposer {...defaultProps} onSubmit={onSubmit} />);

  await userEvent.selectOptions(screen.getByLabelText("Mode"), "agent");
  await userEvent.selectOptions(screen.getByLabelText("Agent Backend"), "openclaw_cli");
  await userEvent.type(screen.getByLabelText("Agent Request"), "Reply with OK.");
  await userEvent.click(screen.getByRole("button", { name: /run/i }));

  expect(onSubmit).toHaveBeenCalledWith(
    expect.objectContaining({
      commandKind: "agent",
      targetId: "openclaw_cli",
      args: expect.objectContaining({ request: "Reply with OK." })
    })
  );
});
```

- [ ] **Step 2: Run failing Composer tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- ExecutionComposer.test.jsx
```

Expected: Agent Backend selector does not exist.

- [ ] **Step 3: Implement selector**

Add state:

```jsx
const [agentBackend, setAgentBackend] = useState("codex_cli");
```

In agent mode controls:

```jsx
<label>
  <div style={styles.label}>Agent Backend</div>
  <select
    style={styles.select}
    value={agentBackend}
    onChange={(event) => setAgentBackend(event.target.value)}
    aria-label="Agent Backend"
  >
    <option value="codex_cli">Codex CLI</option>
    <option value="openclaw_cli">OpenClaw CLI</option>
  </select>
</label>
```

Submit:

```jsx
targetId: agentBackend,
```

Only include `skillHint` when:

```jsx
agentBackend === "codex_cli"
```

- [ ] **Step 4: Update helper copy**

Use backend-aware copy:

```jsx
{agentBackend === "openclaw_cli"
  ? "OpenClaw runs the request through the OpenClaw CLI backend. Workspace staging and verification are handled by the execution subsystem."
  : "Codex agent mode runs a natural-language task through the codex_cli backend."}
```

- [ ] **Step 5: Run Composer tests**

Run:

```powershell
npm test -- ExecutionComposer.test.jsx
```

Expected: tests pass.

## Milestone 5: End-to-End Verification

### Task 14: Run Full Automated Test Suites

**Files:**
- No source edits unless tests reveal defects.

- [ ] **Step 1: Run execution subsystem tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test
```

Expected: all Node tests pass.

- [ ] **Step 2: Run app backend routing tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton
python -m pytest backend/tests/test_chat_exec_routing.py -q
```

Expected: all routing tests pass.

- [ ] **Step 3: Run frontend tests**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- App.test.jsx ExecutionComposer.test.jsx
```

Expected: command building and Composer tests pass.

### Task 15: Add Opt-In Real OpenClaw Smoke Test Script

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/scripts/smoke-openclaw-agent.ts`
- Add docs note in: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-provider-design.md`

- [ ] **Step 1: Create smoke script**

Script behavior:

- require `OPENCLAW_REAL_SMOKE=1`
- submit a direct `execute_agent` request to `ExecutionEngine`
- use `agent_backend = "openclaw_cli"`
- request `Reply with exactly: OK.`
- print normalized status and provider metadata
- exit nonzero if status is not `completed`

- [ ] **Step 2: Run smoke script only when WSL/OpenClaw is available**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
$env:OPENCLAW_REAL_SMOKE='1'
npx tsx scripts/smoke-openclaw-agent.ts
```

Expected: completes with OpenClaw response. This is not part of default CI/unit test runs.

## Milestone 6: Manual GUI Verification

### Task 16: Verify Composer-to-Backend Flow Manually

**Files:**
- No planned edits.

- [ ] **Step 1: Start execution subsystem**

Run:

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
powershell -ExecutionPolicy Bypass -File .\start-ragenius-execution-subsystem.ps1
```

Expected: subsystem starts on port `3001`.

- [ ] **Step 2: Start app skeleton backend and frontend**

Use the existing app skeleton start commands for the local environment.

Expected:

- backend available at `http://127.0.0.1:8000`
- frontend available through Vite

- [ ] **Step 3: Submit OpenClaw request from Composer**

In Execution Composer:

- Mode: `Agent`
- Agent Backend: `OpenClaw CLI`
- Execution Mode: `sync`
- Request: `Reply with exactly: OK.`

Expected:

- chat sends `@exec openclaw "Reply with exactly: OK."`
- backend submits `agent_backend = "openclaw_cli"`
- execution result displays OpenClaw backend metadata
- no raw WSL paths are shown as primary UI

## Completion Criteria

Implementation is complete when:

- `codex_cli` behavior is unchanged.
- `openclaw_cli` is accepted by execution subsystem schema.
- execution engine dispatches OpenClaw through provider map.
- OpenClaw provider has mocked tests for verification, timeout, truncation, and missing-output failure.
- app backend parses `@exec openclaw`.
- app backend submits `agent_backend = "openclaw_cli"`.
- Execution Composer can select OpenClaw.
- frontend command generation emits `@exec openclaw`.
- automated tests listed in Milestone 5 pass.
- real OpenClaw smoke test is opt-in and documented.
