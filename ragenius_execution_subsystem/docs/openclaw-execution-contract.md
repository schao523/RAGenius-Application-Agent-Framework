# OpenClaw Execution Subsystem Contract

Date: 2026-06-14

## Shared Agent Lifecycle Reference

`docs/agent-execution-lifecycle-evidence-contract.md` is authoritative for
provider-neutral lifecycle, evidence levels, process termination, provider-state
policy, artifact projection, diagnostics, and artifact byte serving. This
contract remains authoritative for OpenClaw-specific invocation and result
translation.

Observed behavior source:

- [openclaw-cli-test-results-2026-06-13.md](/D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-cli-test-results-2026-06-13.md)
- [openclaw-cli-test-checklist.md](/D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-cli-test-checklist.md)

## Purpose

This document defines the provider/runtime contract for supporting OpenClaw inside `ragenius_execution_subsystem`.

This is not the cross-subsystem app integration contract. The app-facing boundary is defined separately in:

- [openclaw-agent-execution-integration-contract.md](/D:/GitHub/Codex-RAGenius-System/docs/openclaw-agent-execution-integration-contract.md)

## Scope

This contract covers what the execution subsystem must guarantee when `agent_backend = "openclaw_cli"` is requested:

- provider selection
- OpenClaw CLI invocation
- session key handling
- workspace-scoped input staging
- workspace-scoped output verification
- success/failure classification
- provider diagnostics
- security constraints

This contract does not define:

- user-facing GUI behavior
- chat command grammar
- `ragenius_app_skeleton` session lane state
- `ragenius_builder` skill management
- exact implementation order

Those belong in the integration and design documents.

## Boundary

OpenClaw is an agent execution backend owned by `ragenius_execution_subsystem`.

```text
ragenius_execution_subsystem
  validates execute_agent requests
  enforces policy
  dispatches to OpenClaw
  stages inputs
  verifies outputs
  returns normalized execution results

OpenClaw
  performs external agent work through its CLI runtime
```

OpenClaw must not be modeled as:

- a normal skill
- a normal tool provider
- a generic shell escape
- an MCP provider in Phase 1
- an implicitly trusted backend

## Execution Scope And Ownership

Every persisted execution is owned by an immutable scope:

```ts
type ExecutionAccessScope = {
  app_id: string;
  session_id: string;
};
```

The execution subsystem must persist this scope at submission and require an
exact scoped match for status, logs, confirmation, request replay, and result
retrieval. Store methods must accept the scope rather than loading by execution
id and checking after data has been returned. Scope mismatch returns `404`.

The app backend owns user authentication and verifies that the session belongs
to the authenticated user before submission or follow-up operations. The
execution subsystem authenticates the app service and treats raw app/session
values from an unauthenticated caller, or an execution id alone, as insufficient
authorization.

## Trusted Confirmation Lifecycle

`execution_options.require_confirmation` is not an approval credential and must
be removed from the public request schema. When policy requires confirmation,
the subsystem persists a server-issued confirmation resource containing a
random `confirmation_id`, execution id, immutable app/session scope, policy snapshot,
expiry, and consumption state.

Confirmation performs an atomic compare-and-set transition:

```text
pending_confirmation -> running -> completed | partial | failed
```

Only `pending_confirmation` may transition through confirmation. Repeated,
expired, consumed, or scope-mismatched confirmation requests must not invoke the
provider. Repeated requests for a terminal execution return its existing state.

## Agent Dry Run

With `execution_options.dry_run = true`, the engine may validate and return the
policy, backend, resolved artifact metadata, expected output plan, and
confirmation requirement. It must stop before provider invocation, workspace
staging, output creation, artifact persistence, or confirmation consumption.

## Backend Discriminator

The execution request schema must support:

```text
agent_backend = "openclaw_cli"
```

The OpenClaw backend must run through the `execute_agent` path.

It must not run through the skill `ToolEngine` path.

Reason:

- OpenClaw is prompt-driven.
- OpenClaw owns an agent session.
- OpenClaw can perform internal planning.
- CLI exit code and top-level JSON status are not authoritative.
- Output success requires RAGenius-side verification.

## Runtime Invocation

Phase 1 invocation must use the observed Windows-to-WSL bridge:

```text
wsl -d OpenClawGateway openclaw agent ...
```

Configurable provider settings:

- WSL distro name
- OpenClaw command
- OpenClaw agent id
- default timeout
- workspace root

Observed defaults:

```text
distro = OpenClawGateway
agent = main
workspace_root = /home/openclaw/.openclaw/workspace
```

The provider must not hardcode these values except as defaults.

## Request Inputs

An OpenClaw run is initiated by a normalized execution subsystem request with at least:

- `request_type = "execute_agent"`
- `app_id`
- `session_id`
- `agent_backend = "openclaw_cli"`
- `agent_query`
- optional `agent_skill_hint`
- optional `approved_content_id`
- optional `approved_revision_id`
- optional `context`
- optional `execution_options`

Provider-specific inputs may be carried in `context.openclaw` or a future typed provider-options object.

Phase 1 provider-specific inputs:

- explicit OpenClaw session key, if supplied by caller
- expected output artifact descriptors
- staged input artifact descriptors
- timeout override

If the caller does not supply an OpenClaw session key, the execution subsystem must generate one.

### Concrete Provider Options Schema

Phase 1 uses `context.openclaw` as the provider-options carrier.

The execution subsystem must validate this structure after the generic request schema succeeds:

```ts
type OpenClawExecutionMode = "read_only" | "output_required";

type OpenClawStagedInput = {
  input_id: string;
  source_kind: "approved_content" | "artifact" | "inline_text";
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

type OpenClawExpectedOutput = {
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

type OpenClawContext = {
  execution_mode?: OpenClawExecutionMode;
  session_key?: string;
  timeout_ms?: number;
  max_stdout_bytes?: number;
  max_stderr_bytes?: number;
  staged_inputs?: OpenClawStagedInput[];
  expected_outputs?: OpenClawExpectedOutput[];
};
```

Rules:

- `input_id` and `output_id` must be unique within one execution request.
- `workspace_relative_path` must be relative, normalized, and must not contain `..`.
- app/front-end callers may omit `workspace_relative_path`; the provider may generate it.
- execution subsystem callers must not provide absolute WSL paths through this schema.
- `persist_as_artifact = true` means the verified output should be registered in the execution subsystem artifact store when artifact persistence is available.
- `required = true` means a missing or invalid output fails the execution.

### Read-Only vs Output-Required Decision

The execution subsystem must classify each OpenClaw request before provider invocation:

```ts
type OpenClawExecutionMode = "read_only" | "output_required";
```

Decision rules:

- If `context.openclaw.execution_mode` is supplied, it is authoritative after validation.
- If any `expected_outputs.required = true`, mode is `output_required`.
- If approved content or artifact inputs are supplied and the user request asks to create, write, export, save, generate, produce, transform, convert, summarize into a file, or prepare a reusable result, mode is `output_required`.
- If the request asks only for explanation, inspection, classification, or a short conversational answer, mode is `read_only`.
- If classification is ambiguous and the request references artifacts or approved content, choose `output_required`.

For `output_required`, the provider must ensure at least one required expected output exists before invoking OpenClaw. If the app did not supply one, the provider must generate a default UTF-8 markdown output descriptor:

```text
purpose = "answer"
display_name = "openclaw-result.md"
media_type = "text/markdown"
required = true
persist_as_artifact = true
```

## Session Contract

OpenClaw sessions are persistent and externally visible.

Observed facts:

- session reuse works
- session isolation works
- session keys are visible through `openclaw sessions --json`
- session keys are stored as scoped values such as `agent:main:<key>`

Contract rules:

1. The provider must always pass an explicit session key.
2. The provider must not rely on OpenClaw default-session behavior.
3. Generated session keys must be app-scoped.
4. Generated session keys must be session-aware.
5. Generated session keys must prevent accidental cross-execution contamination.

Recommended generated key shape:

```text
ragenius:<app_id>:<session_id>:<execution_id>
```

The exact string format may change during design, but it must remain deterministic, app-scoped, and execution-safe.

## Workspace Contract

All OpenClaw file interaction must be constrained to the OpenClaw workspace.

Observed workspace:

```text
/home/openclaw/.openclaw/workspace
```

Phase 1 rules:

- staged inputs must be copied into the OpenClaw workspace
- expected outputs must be under the OpenClaw workspace
- prompts must reference OpenClaw workspace paths only
- Windows paths must not be passed to OpenClaw prompts
- `/mnt/c` and `/mnt/d` must not be used unless a later test pass proves them reliable
- every execution must use an isolated run root such as
  `runs/<execution_id>/inputs` and `runs/<execution_id>/outputs`
- normalized caller paths must be rebased beneath the current execution run root
- verification must reject any path that resolves outside the current run root
- a file from another execution must never satisfy current-run verification
- run directories older than `OPENCLAW_RUN_RETENTION_HOURS` are eligible for
  bounded cleanup; cleanup never removes the current run or persisted RAGenius
  artifacts

For output-producing requests, the provider must generate or receive explicit expected output paths before invoking OpenClaw.

OpenClaw must not be asked to choose important output paths itself.

## Input Staging

OpenClaw does not expose a verified upload API through the tested CLI path.

The execution subsystem owns input staging.

### Text Inputs

Observed reliable pattern:

```text
Windows text file -> PowerShell Get-Content -> wsl tee -> OpenClaw workspace file
```

Text-safe staging applies to:

- markdown
- plain text
- JSON
- YAML
- source code

The provider must verify that the staged file exists after transfer.

### Binary Inputs

Observed behavior:

- binary staging via base64 produced noisy command behavior
- the staged PNG still existed
- OpenClaw successfully inspected the staged PNG

Contract rules:

- binary staging must use a byte-safe transfer method
- staging must verify file existence and expected byte size/hash where available
- staging command exit code alone is not sufficient proof

## Output Verification

For any request that declares expected outputs:

1. The provider must pass exact output paths to OpenClaw.
2. OpenClaw must be instructed to write to those exact paths.
3. OpenClaw should be instructed to verify existence before returning.
4. The provider must independently verify outputs after OpenClaw returns.

The independent verification step is mandatory.

The execution subsystem must not normalize a run as completed when required outputs are missing, even if:

- CLI exit code is `0`
- OpenClaw JSON says `ok`
- assistant text claims success

### Verification Result Schema

Each expected output must produce one verification result:

```ts
type OpenClawVerificationResult = {
  output_id: string;
  workspace_relative_path: string;
  workspace_absolute_path: string;
  required: boolean;
  exists: boolean;
  verified: boolean;
  verification_status: "verified" | "failed" | "not_run";
  persistence_status:
    | "not_requested"
    | "persisted"
    | "failed"
    | "not_run";
  size_bytes?: number;
  sha256?: string;
  media_type?: string;
  persisted_artifact_id?: string;
  failure_code?:
    | "missing_output"
    | "empty_output"
    | "size_below_minimum"
    | "hash_mismatch"
    | "read_failed";
  persistence_failure_code?: "persist_failed";
  persistence_failure_message?: string;
  failure_message?: string;
};
```

Completion rule:

- all `required = true` verification results must have `verified = true`
- required persistence requests must have `persistence_status = "persisted"`
- optional verification or requested persistence failures produce top-level `partial`
- persistence failure must not change a verified file to `verified = false`

## Success Semantics

OpenClaw success is a composite decision.

### Read-Only Requests

A read-only request may be normalized as completed only when:

- the CLI process completed
- a usable response was captured
- no timeout or provider-level failure was detected
- no declared verification condition failed

### Output-Producing Requests

An output-producing request may be normalized as completed only when:

- the CLI process completed
- response parsing produced usable diagnostics
- every required output path was verified
- any required export/post-read step succeeded

Top-level execution status must reflect provider outcome:

- provider task failure, timeout, required verification failure, or required
  persistence failure maps to `failed`
- optional verification or requested optional persistence failure maps to `partial`
- only a fully successful provider result maps to `completed`

The engine must not wrap a provider `failed` result in a top-level `completed`
execution.

## Failure Semantics

The provider must classify failures into execution-subsystem error categories.

Required categories:

- launch failure
- CLI argument failure
- provider timeout
- malformed or unusable JSON
- staged input missing
- output artifact missing
- output verification failed
- backend refusal or inability
- unsupported provider option

OpenClaw conversational failures are not structured errors. The provider must inspect:

- process exit code
- stdout
- stderr
- parsed JSON, when available
- required artifact verification results

## JSON Output

OpenClaw `--json` is useful but not authoritative.

Observed stable top-level fields:

- `runId`
- `status`
- `summary`
- `result`

Observed useful nested fields:

- `result.payloads`
- `result.meta`
- `result.finalAssistantVisibleText`
- `result.toolSummary`

Observed limitation:

- task-level failure can still return `status = ok`
- timeout-like outcomes can still return exit code `0`

Contract rules:

1. Prefer `--json` when available.
2. Preserve raw stdout/stderr for diagnostics.
3. Do not trust top-level JSON status as execution truth.
4. Extract useful response text and metadata when available.
5. Enforce declared verification rules independently.

## Prompt Construction

The provider prompt builder must include:

- user task
- app/session-safe execution context
- staged input paths
- expected output paths
- workspace-only rules
- no Windows path rules
- concise return expectations

For output-producing tasks, the prompt must instruct OpenClaw to:

- work only inside the OpenClaw workspace
- use the exact provided input paths
- write to the exact provided output paths
- verify file existence
- return final paths and a short status summary

Prompt instructions reduce ambiguity but do not replace provider-side verification.

## Concurrency

Observed behavior:

- two concurrent runs using the same session key both completed and created separate files

This is not enough evidence to declare same-session concurrency safe.

Phase 1 rule:

- concurrent runs with the same OpenClaw session key are unsupported

The provider or scheduler must avoid dispatching parallel runs against the same OpenClaw session key.

Concrete Phase 1 behavior:

- maintain an in-process per-session-key mutex for OpenClaw provider execution
- queue later requests for the same session key until the active run exits or times out
- allow different session keys to run concurrently only if the process manager is configured to allow provider concurrency
- default maximum provider concurrency is `1`

## Timeout Handling

The provider must implement timeout interpretation outside OpenClaw.

Rules:

- support a configurable timeout
- default timeout is `120000` milliseconds unless config overrides it
- detect timeout messages in output when needed
- classify timed-out output-producing runs as failed unless all required outputs are verified
- include timeout evidence in diagnostics

Process handling rules:

- spawn WSL without shell interpolation
- pass command arguments as an argv array
- on timeout, send process termination to the spawned WSL process
- if the process does not exit within `5000` milliseconds, force kill the process tree where supported
- capture timeout state separately from OpenClaw conversational timeout text

Output capture rules:

- default `max_stdout_bytes = 262144`
- default `max_stderr_bytes = 65536`
- truncate from the tail when output exceeds the limit
- record `stdout_truncated` and `stderr_truncated` booleans in diagnostics
- never return unredacted raw output directly to app-facing response fields

## Security

The provider must treat OpenClaw as an untrusted external execution surface.

Rules:

- do not pass Windows filesystem paths to OpenClaw prompts
- do not expose secrets in prompts, logs, or normalized results
- redact secret-like environment/config values
- do not let OpenClaw choose export paths into Windows
- verify all required artifacts outside OpenClaw
- include app/session identifiers only when safe and useful

### Provider-Aware Policy

OpenClaw uses the existing agent policy pipeline, but policy metadata must include backend-specific details:

```ts
type AgentBackendPolicyMetadata = {
  backend: "openclaw_cli";
  filesystem_surface: "wsl_workspace";
  network_surface: "provider_default";
  requires_workspace_staging: boolean;
  requires_output_verification: boolean;
};
```

OpenClaw default risk handling:

- read-only conversational requests may remain `agent_read_only`
- any request that writes files, transforms artifacts, exports content, or persists outputs is at least `agent_workspace_write`
- requests that ask OpenClaw to contact external services or publish/send data are at least `agent_external_write`
- destructive file operations remain blocked unless a future explicit policy permits them

## Logging and Provenance

Every OpenClaw execution result must preserve enough metadata for debugging and audit.

Minimum metadata:

- `agent_backend = "openclaw_cli"`
- invocation mode, for example `wsl_cli`
- WSL distro name
- OpenClaw command
- OpenClaw agent id
- OpenClaw session key
- expected output paths
- verified output paths
- raw exit code
- JSON parse status
- verification status

Completed results must include evidence that required verification checks passed.

### Provider Metadata Shape

The normalized execution result must include OpenClaw metadata under a provider-specific metadata object:

```ts
type OpenClawProviderMetadata = {
  backend: "openclaw_cli";
  provider_name: "OpenClaw";
  invocation_mode: "wsl_cli";
  wsl_distro: string;
  openclaw_command: string;
  openclaw_agent_id: string;
  openclaw_session_key: string;
  execution_mode: "read_only" | "output_required";
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

## Phase 1 Completion Criteria

Provider support satisfies this contract when the execution subsystem can:

1. accept `execute_agent` with `agent_backend = "openclaw_cli"`
2. dispatch to an OpenClaw provider instead of Codex
3. invoke OpenClaw through WSL with explicit session keys
4. stage text inputs into the OpenClaw workspace
5. stage binary inputs through a byte-safe verified path
6. provide explicit expected output paths for artifact-producing requests
7. independently verify required outputs
8. classify provider failures without trusting exit code or top-level JSON alone
9. return normalized results with OpenClaw diagnostics

## Binary Staging Decision

Phase 1 must use a verified byte-safe staging helper.

Required method:

1. Read the source artifact bytes on the Windows side.
2. Compute SHA-256 and byte size before transfer.
3. Base64-encode the bytes into chunks.
4. Send chunks to WSL through stdin to a small WSL-side decode command.
5. Decode into a temporary file under the OpenClaw workspace.
6. Move the temporary file to the final workspace-relative path.
7. Verify byte size and SHA-256 from WSL after the move.

The helper may observe noisy command exit behavior, but it must not accept a staged binary unless size and hash verification pass.

## Remaining Design Decisions

The design document must still decide implementation names and file placement, but the Phase 1 contract decisions are fixed:

- provider options use `context.openclaw`
- output verification uses `OpenClawVerificationResult`
- result metadata uses `OpenClawProviderMetadata`
- binary staging uses verified base64 chunk transfer with size/hash verification
