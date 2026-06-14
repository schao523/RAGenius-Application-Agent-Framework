# OpenClaw Provider Design

Date: 2026-06-14

## Goal

Add OpenClaw as a second `execute_agent` backend in `ragenius_execution_subsystem`, while preserving the existing Codex CLI agent path.

## Design Summary

The execution subsystem should generalize agent backend dispatch around a small provider interface. `CodexCliProvider` remains the implementation for `codex_cli`; a new `OpenClawCliProvider` implements `openclaw_cli`.

OpenClaw-specific behavior lives below the execution engine boundary:

- WSL invocation
- session key generation
- workspace staging
- prompt construction
- output verification
- provider diagnostics

## Files to Modify

- `src/api/schemas/execution-request.schema.ts`
- `src/core/execution/execution-engine.ts`
- `src/core/execution/execution-store.ts`
- `src/core/agents/codex-cli-provider.ts`
- `src/core/agents/codex-cli-types.ts`
- `src/config/env.ts`
- `src/config/provider-config.ts`
- `src/config/runtime-config.ts`
- `src/app.ts`

## Files to Create

- `src/core/agents/agent-provider.ts`
- `src/core/agents/openclaw-cli-provider.ts`
- `src/core/agents/openclaw-cli-bridge.ts`
- `src/core/agents/openclaw-cli-types.ts`
- `src/core/agents/openclaw-workspace.ts`
- `src/core/agents/openclaw-prompt-builder.ts`
- tests for schema, provider dispatch, staging, verification, and normalization

## Request Schema

Current state:

```ts
agent_backend: z.literal("codex_cli")
```

Target state:

```ts
const agentBackendSchema = z.enum(["codex_cli", "openclaw_cli"]);
```

The `execute_agent` schema should continue to accept:

- `agent_query`
- `agent_skill_hint`
- `approved_content_id`
- `approved_revision_id`
- `context`
- `execution_options`

For Phase 1, OpenClaw provider options can be carried under:

```ts
context: {
  openclaw?: {
    session_key?: string;
    staged_inputs?: Array<...>;
    expected_outputs?: Array<...>;
    timeout_ms?: number;
  }
}
```

If provider options become heavily used, promote them later to a typed top-level `provider_options`.

### Concrete TypeScript Interfaces

Create these shared types in `src/core/agents/openclaw-cli-types.ts`:

```ts
export type OpenClawExecutionMode = "read_only" | "output_required";

export type OpenClawSourceKind = "approved_content" | "artifact" | "inline_text";

export type OpenClawStagedInput = {
  input_id: string;
  source_kind: OpenClawSourceKind;
  source_ref: {
    approved_content_id?: string;
    approved_revision_id?: string;
    artifact_id?: string;
    artifact_version_id?: string;
  };
  display_name: string;
  media_type: string;
  encoding: "utf8" | "binary";
  content_sha256?: string;
  size_bytes?: number;
  workspace_relative_path?: string;
};

export type OpenClawExpectedOutput = {
  output_id: string;
  purpose: "answer" | "artifact" | "diagnostic";
  display_name: string;
  media_type: string;
  required: boolean;
  workspace_relative_path?: string;
  persist_as_artifact: boolean;
  artifact_role?: "final" | "intermediate" | "debug";
  min_size_bytes?: number;
  expected_sha256?: string;
};

export type OpenClawProviderOptions = {
  execution_mode?: OpenClawExecutionMode;
  session_key?: string;
  timeout_ms?: number;
  max_stdout_bytes?: number;
  max_stderr_bytes?: number;
  staged_inputs?: OpenClawStagedInput[];
  expected_outputs?: OpenClawExpectedOutput[];
};

export type OpenClawVerificationResult = {
  output_id: string;
  workspace_relative_path: string;
  workspace_absolute_path: string;
  required: boolean;
  exists: boolean;
  verified: boolean;
  size_bytes?: number;
  sha256?: string;
  media_type?: string;
  persisted_artifact_id?: string;
  failure_code?:
    | "missing_output"
    | "empty_output"
    | "size_below_minimum"
    | "hash_mismatch"
    | "read_failed"
    | "persist_failed";
  failure_message?: string;
};

export type OpenClawProviderMetadata = {
  backend: "openclaw_cli";
  provider_name: "OpenClaw";
  invocation_mode: "wsl_cli";
  wsl_distro: string;
  openclaw_command: string;
  openclaw_agent_id: string;
  openclaw_session_key: string;
  execution_mode: OpenClawExecutionMode;
  expected_output_count: number;
  required_output_count: number;
  verified_output_count: number;
  json_parse_status: "parsed" | "failed" | "not_requested";
  raw_exit_code: number | null;
  timed_out: boolean;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
};
```

Validation rules:

- reject absolute `workspace_relative_path`
- reject paths containing `..`
- reject duplicate `input_id` or `output_id`
- reject `timeout_ms < 1000`
- clamp `max_stdout_bytes` and `max_stderr_bytes` to configured maxima

## Provider Interface

Create a common provider interface:

```ts
export interface AgentProvider {
  readonly backend: "codex_cli" | "openclaw_cli";
  execute(request: ExecuteAgentRequest, policy: AgentPolicyDecision): Promise<AgentProviderResult>;
}
```

The shared result type should include:

- `status`
- `summary`
- `output_text`
- `diagnostics`
- `artifacts`
- `raw`

Codex can initially adapt its current result into this shape without changing CLI behavior.

## ExecutionEngine Dispatch

Current behavior:

```ts
this.codexCliProvider.execute(request, agentPolicy)
```

Target behavior:

```ts
const provider = this.agentProviders.get(request.agent_backend);
if (!provider) {
  return failed unknown-agent-backend result;
}
const agentResult = await provider.execute(request, agentPolicy);
```

Keep policy enforcement before provider invocation.

Do not duplicate policy checks inside individual providers except for provider-specific safety checks.

## OpenClaw Provider Flow

`OpenClawCliProvider.execute(...)` should perform:

1. Normalize provider options.
2. Generate an execution-scoped OpenClaw session key if missing.
3. Resolve the OpenClaw workspace root.
4. Stage approved content and artifact inputs into the workspace.
5. Generate expected output paths for output-producing requests.
6. Build a workspace-constrained prompt.
7. Invoke `wsl -d <distro> openclaw agent ... --json`.
8. Parse JSON when available.
9. Verify expected outputs outside OpenClaw.
10. Return normalized provider result.

### Output Mode Classification

Add `classifyOpenClawExecutionMode(...)` near the provider or prompt builder.

Rules:

- explicit `options.execution_mode` wins
- required expected outputs imply `output_required`
- transform/export/generate/save/write/create/produce verbs imply `output_required`
- selected artifacts with `reuse_mode = "transform"` imply `output_required`
- approved content plus ambiguous "prepare" or "summarize" requests imply `output_required`
- otherwise use `read_only`

When mode is `output_required` and no required expected output is provided, generate:

```ts
{
  output_id: "openclaw_answer",
  purpose: "answer",
  display_name: "openclaw-result.md",
  media_type: "text/markdown",
  required: true,
  persist_as_artifact: true,
  artifact_role: "final",
  min_size_bytes: 1
}
```

## Session Key Generation

Use deterministic app/session/execution scoping.

Recommended function:

```ts
function buildOpenClawSessionKey(input: {
  appId: string;
  sessionId: string;
  executionId: string;
}): string {
  return `ragenius:${input.appId}:${input.sessionId}:${input.executionId}`;
}
```

If OpenClaw rejects colon characters in a future test, encode with a safe delimiter or hash while preserving app/session/execution uniqueness.

## Workspace Staging

Create `openclaw-workspace.ts` with functions for:

- validating workspace-relative paths
- converting safe logical paths to OpenClaw workspace paths
- staging text content
- staging binary content
- verifying staged files
- verifying expected outputs

Provider prompts should receive only OpenClaw workspace paths.

The app must never send WSL paths as user-editable fields.

### Binary Staging Implementation

Use verified base64 chunk staging for Phase 1.

Implementation requirements:

- compute SHA-256 and byte size before transfer
- base64-encode bytes on the Windows/Node side
- stream chunks to WSL stdin
- decode into a temporary workspace path
- move the temporary file to the final workspace-relative path
- verify size and SHA-256 from WSL after transfer
- fail staging if verification does not match, regardless of conversational OpenClaw behavior

The staging helper should expose:

```ts
export type StageFileResult = {
  input_id: string;
  workspace_relative_path: string;
  workspace_absolute_path: string;
  size_bytes: number;
  sha256: string;
};
```

## Prompt Builder

Create `openclaw-prompt-builder.ts`.

Prompt must include:

- original user request
- staged input paths
- expected output paths
- workspace-only rule
- no Windows path rule
- verification instruction
- concise final response instruction

For expected outputs:

```text
Write the result to exactly: /home/openclaw/.openclaw/workspace/<path>
Do not choose a different path.
Verify the file exists before responding.
```

## Verification

Expected outputs are authoritative.

The provider result is `completed` only if all required outputs verify.

Verification should capture:

- output path
- exists
- byte size, when available
- hash, when available
- verification error, when failed

Missing required output maps to a provider failure even when OpenClaw returns exit code `0`.

Persist verified outputs with `persist_as_artifact = true` through the existing artifact persistence mechanism. If persistence is not available in the execution subsystem runtime, return the verified workspace output metadata and mark `persisted_artifact_id` absent; do not claim artifact persistence succeeded.

## Config

Add environment/config fields:

- `OPENCLAW_CLI_ENABLED`
- `OPENCLAW_WSL_DISTRO`
- `OPENCLAW_CLI_COMMAND`
- `OPENCLAW_AGENT_ID`
- `OPENCLAW_WORKSPACE_ROOT`
- `OPENCLAW_DEFAULT_TIMEOUT_MS`

Defaults:

```text
OPENCLAW_CLI_ENABLED=false
OPENCLAW_WSL_DISTRO=OpenClawGateway
OPENCLAW_CLI_COMMAND=openclaw
OPENCLAW_AGENT_ID=main
OPENCLAW_WORKSPACE_ROOT=/home/openclaw/.openclaw/workspace
```

## Execution Store

Current store derives agent skill id as:

```text
codex_cli
codex_cli:<hint>
```

Change to backend-aware format:

```text
<agent_backend>
<agent_backend>:<hint>
```

Examples:

```text
codex_cli:notebooklm
openclaw_cli
```

## Normalized Result Metadata

OpenClaw result metadata should include:

- backend
- provider name
- invocation mode
- WSL distro
- OpenClaw agent id
- OpenClaw session key
- expected output count
- verified output count
- JSON parse status
- raw exit code

Do not expose secret-bearing config values.

### Normalized Provider Result Shape

The OpenClaw provider should return:

```ts
export type OpenClawProviderResult = {
  status: "completed" | "failed";
  summary: string;
  output_text: string;
  artifacts: Array<{
    artifact_id?: string;
    output_id: string;
    display_name: string;
    media_type: string;
    role: "final" | "intermediate" | "debug";
    verified: boolean;
  }>;
  provider_metadata: OpenClawProviderMetadata;
  verification_results: OpenClawVerificationResult[];
  diagnostics: {
    failure_code?: string;
    failure_message?: string;
    stdout_tail?: string;
    stderr_tail?: string;
    stdout_truncated: boolean;
    stderr_truncated: boolean;
    redactions_applied: boolean;
  };
  raw: {
    json?: unknown;
    exit_code: number | null;
  };
};
```

`ExecutionEngine` must map this into the existing normalized execution response without requiring app-side raw output parsing.

## WSL Process Management

The bridge must use argv-style spawning, not shell string interpolation.

Command shape:

```ts
[
  "wsl",
  "-d",
  config.wslDistro,
  config.openclawCommand,
  "agent",
  "--agent",
  config.agentId,
  "--session-key",
  sessionKey,
  "--message",
  prompt,
  "--json"
]
```

Output policy:

- capture stdout and stderr separately
- default stdout cap: `262144` bytes
- default stderr cap: `65536` bytes
- keep tail when truncating
- record truncation flags

Timeout policy:

- default timeout: `120000` ms
- kill spawned process on timeout
- wait `5000` ms for graceful exit
- force kill process tree where supported
- return `timed_out = true` even if partial JSON exists

Concurrency policy:

- in-process mutex by OpenClaw session key
- default provider concurrency: `1`
- same-session requests queue, not parallelize

## Tests

Required tests:

- schema accepts `openclaw_cli`
- schema still accepts `codex_cli`
- schema rejects unknown agent backend
- execution engine dispatches `codex_cli` to Codex provider
- execution engine dispatches `openclaw_cli` to OpenClaw provider
- execution store persists backend-aware agent ids
- OpenClaw provider fails when required output is missing
- OpenClaw provider completes when required output verifies
- OpenClaw provider does not trust top-level JSON `status = ok`
- OpenClaw provider includes diagnostics without leaking secrets
- OpenClaw provider generates a default expected output for ambiguous approved-content output requests
- OpenClaw provider keeps read-only prompt requests artifact-free
- OpenClaw bridge truncates stdout/stderr and records truncation flags
- OpenClaw bridge times out and reports `timed_out = true`
- binary staging rejects hash mismatch

Integration tests that invoke real WSL/OpenClaw should be opt-in, not part of normal unit test runs.

## Non-Goals

- replacing Codex CLI support
- adding Builder skill management
- exposing raw OpenClaw workspace paths in frontend
- using OpenClaw as a generic shell tool
- treating OpenClaw JSON status as authoritative

## Implementation Order

1. Add backend enum and tests.
2. Add provider interface and adapt Codex provider.
3. Add execution engine provider dispatch.
4. Add backend-aware execution store id handling.
5. Add OpenClaw config.
6. Add OpenClaw provider with mocked bridge tests.
7. Add staging and verification helpers.
8. Add opt-in real OpenClaw smoke test script.
