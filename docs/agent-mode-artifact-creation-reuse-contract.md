# Agent Mode Artifact Creation And Reuse Contract

## Purpose

Agent-mode execution turns must support artifacts as first-class reusable inputs and outputs.

Users should not paste artifact ids into natural-language prompts or understand provider-specific paths. Execution Composer should let users select artifacts explicitly, and the app/backend should pass structured artifact references to the selected agent backend.

This contract applies to:

- `@exec codex`
- `@exec openclaw`

OpenClaw has stricter handling because selected artifacts must be staged into an OpenClaw workspace before the agent can use them.

## Scope

Applies to:

- `ragenius_app_skeleton` Execution Composer Agent mode
- `ragenius_app_skeleton` exec routing and execution subsystem client
- `ragenius_execution_subsystem` `execute_agent` request contract
- Agent providers such as `codex_cli` and `openclaw_cli`
- RAGenius artifact store persistence for verified agent outputs

Does not apply to:

- RAG ingestion or retrieval internals
- Builder admin UI
- Cross-session or app-wide artifact library design
- Provider-specific workspace internals except where needed for OpenClaw staging

## Product Principles

- The user-facing reuse unit is an artifact, not an approved-content id, execution id, or provider path.
- Agent prompt text describes what the user wants done.
- Artifact selection describes what reusable inputs the agent may use.
- Output persistence is a RAGenius execution concern, not an OpenClaw-only concern.
- Verified agent outputs should become RAGenius artifacts when they are user-visible or marked for persistence.
- Debug details remain inspectable, but provider-local paths must not become the primary UX.

## Session Scope Rule

For the first implementation, `artifact_refs` are session-scoped only.

An `artifact_ref` is valid only in the current `{app_id, session_id}` execution context.

The execution subsystem must reject an artifact ref when:

- artifact `app_id` does not match request `app_id`
- artifact `session_id` does not match request `session_id`
- artifact is missing
- artifact is not ready
- artifact is not reusable
- requested `reuse_mode` is unsupported by the artifact
- selected agent backend does not support the resolved consumption mode

Cross-session and app-level artifact references require a future permission model and are out of scope for this contract.

## User Flows

### Reuse Existing Artifacts In Agent Mode

1. User opens Execution Composer.
2. User selects `Agent`.
3. User selects an agent backend, for example `Codex CLI` or `OpenClaw CLI`.
4. User enters a natural-language request.
5. User optionally selects one or more artifacts from an Agent-mode artifact selector.
6. User runs the execution.
7. The app submits prompt text and selected artifact refs separately.
8. The execution subsystem resolves artifact refs and prepares provider-specific context.

### Persist Agent Outputs

1. Agent backend completes execution.
2. Execution subsystem verifies expected outputs when the run is output-producing.
3. Verified outputs marked for persistence are copied or saved into the RAGenius artifact store.
4. Execution result returns stable artifact metadata and artifact ids.
5. App shows artifact actions on the execution turn:
   - `Preview`
   - `Open Saved File`
   - `Reuse In Composer`
   - `View In Artifact Library`

## Frontend Contract

### Execution Composer Agent Mode

Agent mode must include:

- Agent backend selector
- Natural-language request input
- Optional artifact selector
- Selected artifact summary
- Remove or unselect controls for selected artifacts
- Reuse-mode visibility when relevant

The artifact selector should use checkboxes for multi-select.

For each artifact row, the UI should show:

- `display_name`
- `artifact_type_label`
- `mime_type`
- default reuse mode
- compatible backend hint

For OpenClaw-selected artifacts, the UI should show:

```text
Will be staged into the OpenClaw workspace by the execution subsystem.
```

The UI must not show or accept OpenClaw workspace paths.

### Compatibility UX

Composer should allow artifact selection when:

- `artifact.capabilities.can_reuse` is true
- artifact belongs to the active session
- selected backend supports at least one of the artifact's supported consumption modes

Composer should display incompatible artifacts as unavailable with a short reason, not silently hide everything.

Examples:

- `text/markdown` chat export can be used as `inline_text` or `file_backed`.
- PDF export can be used as `file_backed` or `binary_payload`.
- metadata-only artifact can be passed as `metadata_only`.

## App Backend Contract

The app backend must parse and route Agent-mode execution turns without embedding artifact details in the command string.

The app backend submits structured artifact refs and expected outputs to the execution subsystem.

Conceptual request:

```json
{
  "request_type": "execute_agent",
  "agent_backend": "openclaw_cli",
  "app_id": "app_123",
  "session_id": "session_123",
  "agent_query": "Summarize the selected artifacts into a reusable markdown output.",
  "artifact_refs": [
    {
      "artifact_id": "artifact_123",
      "role": "source",
      "reuse_mode": "file_backed"
    }
  ],
  "expected_outputs": [
    {
      "output_id": "agent_answer",
      "display_name": "agent-answer.md",
      "media_type": "text/markdown",
      "required": true,
      "persist_as_artifact": true,
      "artifact_type": "agent_output"
    }
  ],
  "context": {
    "openclaw": {
      "execution_mode": "output_required"
    }
  }
}
```

Backward compatibility:

- Existing approved-content fields may remain during migration.
- If approved content is present, the app may convert it into an artifact ref or approved-content staged input.
- New Agent-mode UX should prefer artifact refs over approved-content ids.

## Execution Subsystem Request Contract

`execute_agent` must support `artifact_refs` and provider-neutral `expected_outputs`.

```ts
type ExecuteAgentRequest = {
  request_type: "execute_agent";
  app_id: string;
  session_id: string;
  agent_backend: "codex_cli" | "openclaw_cli";
  agent_query: string;
  agent_skill_hint?: string;
  approved_content_id?: string;
  approved_revision_id?: string;
  artifact_refs?: AgentArtifactRef[];
  expected_outputs?: AgentExpectedOutput[];
  context?: {
    openclaw?: {
      execution_mode?: "read_only" | "output_required";
      timeout_ms?: number;
    };
    [key: string]: unknown;
  };
  execution_options?: {
    dry_run?: boolean;
    require_confirmation?: boolean;
  };
};
```

Artifact ref:

```ts
type AgentArtifactRef = {
  artifact_id: string;
  artifact_version_id?: string;
  role: "source" | "context" | "template" | "attachment";
  reuse_mode:
    | "inline_text"
    | "file_backed"
    | "binary_payload"
    | "metadata_only";
  display_name?: string;
  mime_type?: string;
};
```

Expected output:

```ts
type AgentExpectedOutput = {
  output_id: string;
  display_name?: string;
  media_type?: string;
  required?: boolean;
  persist_as_artifact?: boolean;
  artifact_type?: "agent_output";
  min_size_bytes?: number;
  expected_sha256?: string;
};
```

Rules:

- `artifact_refs` describe reusable inputs.
- `expected_outputs` describe what RAGenius wants as reusable outputs.
- `context.openclaw` describes how OpenClaw should run.
- OpenClaw workspace paths are generated by the OpenClaw provider only.
- Raw file paths from the frontend are forbidden.
- Provider workspace paths from the frontend are forbidden.
- The execution subsystem resolves artifact refs against current app/session boundaries.
- The execution subsystem chooses provider-specific staging and prompt injection.

## Backend Compatibility Rules

The execution subsystem should expose or share backend compatibility metadata so the app can render Agent-mode artifact eligibility.

Conceptual compatibility table:

```ts
type AgentBackendArtifactCompatibility = {
  backend: "codex_cli" | "openclaw_cli";
  supported_reuse_modes: Array<
    "inline_text" | "file_backed" | "binary_payload" | "metadata_only"
  >;
  max_inline_text_bytes: number;
  max_staged_file_bytes: number;
  max_artifact_count: number;
};
```

Initial defaults:

- `codex_cli`: supports `inline_text`, `file_backed`, `metadata_only`
- `openclaw_cli`: supports `inline_text`, `file_backed`, `binary_payload`, `metadata_only`

The frontend may start with hardcoded defaults, but the target design is backend-provided compatibility metadata.

## Resolved Artifact Payload Contract

The execution subsystem resolves frontend refs into internal payloads before provider execution.

```ts
type ResolvedAgentArtifact = {
  artifact_id: string;
  artifact_type: string;
  display_name: string;
  mime_type?: string;
  role: "source" | "context" | "template" | "attachment";
  reuse_mode: "inline_text" | "file_backed" | "binary_payload" | "metadata_only";
  file_path?: string;
  inline_text?: string;
  inline_text_truncated?: boolean;
  metadata?: Record<string, unknown>;
  size_bytes?: number;
  sha256?: string;
};
```

Rules:

- `file_path` is server-side only.
- `inline_text` must respect configured truncation limits.
- `binary_payload` must include size/hash verification before staging.
- `metadata_only` must never load full file bytes.

## Size And Truncation Limits

The execution subsystem must define limits before implementation.

Recommended defaults:

- max selected artifacts per agent turn: `10`
- max inline text per artifact: `64 KiB`
- max total inline text in one agent prompt: `256 KiB`
- max staged file size for OpenClaw MVP: `25 MiB`
- binary staging chunk size: `64 KiB`

If inline content is truncated:

- provider prompt must state that content was truncated
- diagnostics must record original size when known
- artifact id and file-backed mode should be offered as fallback when possible

## Provider Behavior

### Codex CLI

Codex may consume artifacts through:

- inline text context for text artifacts
- file path references for file-backed artifacts when safe
- metadata-only summaries when content should not be expanded

Codex prompt construction should include a structured artifact context block.

Example:

```text
Selected artifacts:
- Chat Export - Bible observation notes.md
  Artifact id: artifact_123
  Reuse mode: inline_text
  Content:
  ...
```

Codex should not depend on the user manually mentioning artifact ids in request text.

### OpenClaw CLI

OpenClaw must consume artifacts through execution-subsystem-managed staging.

OpenClaw provider flow:

1. Resolve `artifact_refs`.
2. Stage supported artifact payloads into the OpenClaw workspace.
3. Build a prompt that lists staged workspace-safe paths.
4. Run OpenClaw.
5. Verify expected outputs.
6. Persist verified outputs back to the RAGenius artifact store when required.
7. Return stable artifact records to the app.

OpenClaw prompt construction should include:

```text
Staged inputs:
- artifact_123: /home/openclaw/.openclaw/workspace/inputs/artifact_123.md

Required outputs:
- agent_answer: write exactly to /home/openclaw/.openclaw/workspace/outputs/agent_answer-openclaw-result.md
```

OpenClaw prompt construction must also include approved content or artifact inline text when selected and when the selected consumption mode requires inline text.

### OpenClaw Binary Staging

Binary staging must be implemented without shell interpolation.

Required behavior:

- source bytes are read by the execution subsystem from a resolved artifact path
- SHA-256 and size are calculated before transfer
- bytes are transferred to OpenClaw workspace in verified chunks
- staged file is inspected in WSL after transfer
- staged size and SHA-256 must match source size and hash

The implementation may use base64 chunks only if arguments are passed without shell interpolation and verified after writing. A raw string-built shell pipeline is not allowed.

## Output Persistence Contract

Verified agent outputs must be persisted as RAGenius artifacts when:

- output is marked `required`, or
- output has `persist_as_artifact: true`, or
- provider returns a user-visible final file and provider policy says to persist it

Persistence should map to the existing stored artifact record shape instead of introducing redundant top-level fields.

Do not add `created_by_agent_backend` as a separate top-level persisted field if `provider_origin` already carries the backend identity.

Persisted record mapping:

```ts
type StoredAgentOutputArtifact = StoredArtifactRecord & {
  artifact_type: "agent_output";
  provider_origin: "codex_cli" | "openclaw_cli";
  created_by_execution_id: string;
  content: {
    source_kind: "agent_execution";
    source_session_id: string;
    source_execution_id: string;
    agent_backend: "codex_cli" | "openclaw_cli";
    provider_output_id?: string;
    verification?: {
      output_id: string;
      verified: boolean;
      workspace_relative_path?: string;
      mime_type?: string;
      size_bytes?: number;
      sha256?: string;
    };
  };
};
```

The app API returns a normalized UI projection:

```ts
type AgentOutputArtifactView = {
  artifact_id: string;
  artifact_type: "agent_output";
  display_name: string;
  summary?: string;
  mime_type?: string;
  created_by_execution_id: string;
  provider_origin: "codex_cli" | "openclaw_cli";
  routes: {
    open: string;
    preview?: string | null;
    delete: string;
  };
  consumption: {
    default_mode: "file_backed" | "inline_text" | "binary_payload";
    supported_modes: string[];
  };
};
```

Artifact Library should display source labels such as:

- `Generated by OpenClaw Agent`
- `Generated by Codex Agent`

Execution result cards should display persisted artifact actions, not provider-local output paths.

## Partial Failure Semantics

Required output handling:

- If provider execution fails, execution status is `failed`.
- If a required output is missing or verification fails, execution status is `failed`.
- If a required output verifies but artifact persistence fails, execution status is `failed`.

Optional output handling:

- If an optional output fails verification, execution may still be `completed`.
- If optional output persistence fails, execution may still be `completed`.
- Optional failures must be reported in `diagnostics` and inspector details.

If the normalized execution model later supports `completed_with_warnings`, optional output failures should use that status. Until then, use `completed` with diagnostics for optional failures and `failed` for required failures.

## Result Shape

Agent provider result should include:

```ts
type AgentProviderResult = {
  status: "completed" | "failed";
  summary: string;
  output_text?: string;
  artifacts?: AgentOutputArtifactView[];
  provider_metadata?: Record<string, unknown>;
  verification_results?: Array<{
    output_id: string;
    verified: boolean;
    persisted_artifact_id?: string;
    failure_code?: string;
    failure_message?: string;
  }>;
  diagnostics?: Record<string, unknown>;
};
```

Rules:

- User-facing summary should be concise.
- Full provider trace remains available in inspector diagnostics.
- Raw stdout/stderr should not be rendered directly in the chat card by default.
- Non-zero provider exit codes must produce `status = "failed"` unless explicitly classified as benign by provider-specific logic.

## Security And Isolation

Rules:

- Artifact refs must be resolved server-side.
- App and session isolation must be enforced before staging.
- Frontend must never submit raw local filesystem paths.
- OpenClaw workspace paths must be generated only by the execution subsystem.
- Source artifacts must not be mutated in place.
- Output artifact persistence must copy data out of provider workspace into the RAGenius artifact store.
- Inspector may show provider-local paths for debugging, but main UI should not depend on them.

## Confirmation Contract

Existing confirmation flow applies.

Agent execution requires confirmation when policy class is:

- external write
- workspace write
- output-producing action with side effects

The app must show confirmation actions on pending agent turns.

The execution subsystem remains responsible for:

- classifying agent request risk
- returning `pending_confirmation`
- running only after confirmation

## Acceptance Criteria

- Agent mode Composer can select one or more compatible session artifacts.
- User can unselect artifacts before running.
- App submits artifact refs separately from prompt text.
- `@exec openclaw` receives `agent_backend = "openclaw_cli"`.
- `@exec codex` receives `agent_backend = "codex_cli"`.
- `execute_agent` accepts provider-neutral `expected_outputs`.
- OpenClaw provider stages selected artifact payloads into workspace-safe paths.
- OpenClaw prompt includes staged input paths and selected inline content when applicable.
- Codex prompt/context includes selected artifacts without requiring manual id references.
- Verified OpenClaw outputs marked for persistence are persisted as RAGenius artifacts.
- Required output persistence failure makes execution fail.
- Optional output persistence failure is visible in diagnostics.
- Execution cards show persisted artifact actions.
- Artifact Library shows generated agent artifacts with friendly names.
- Inspector shows provider diagnostics and raw paths only as debug information.
- Non-zero provider exit codes are reported as failures.

## Migration Notes

Phase 1 may keep approved-content plumbing internally.

Target end state:

- `Mark Reviewed` creates or updates artifact metadata.
- Agent-mode reuse uses artifacts by default.
- Approved content remains only as compatibility plumbing where necessary.
- New UX documentation should describe artifacts as the single visible reuse concept.

