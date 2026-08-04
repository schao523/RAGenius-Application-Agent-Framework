# OpenClaw Agent Execution Integration Contract

Date: 2026-06-14

## Shared Agent Lifecycle Addendum

`docs/agent-execution-lifecycle-evidence-contract.md` is the normative shared
contract for Codex and OpenClaw lifecycle, process termination, evidence,
provider-state access, artifact projection, diagnostics, and artifact byte
serving. This document remains authoritative for OpenClaw cross-subsystem
routing and payload details.

## Purpose

This document defines the cross-subsystem contract for OpenClaw-backed agent execution from `ragenius_app_skeleton` through `ragenius_execution_subsystem`.

It exists to keep responsibilities explicit and prevent runtime execution logic from leaking into the wrong subsystem.

## Normative Hardening Addendum

The rules in this section supersede older examples in this document where they
conflict. Provider-neutral `artifact_refs` and `expected_outputs` are defined by
`docs/agent-mode-artifact-creation-reuse-contract.md`; OpenClaw-specific context
must not duplicate their persistence or reuse semantics.

Execution access is scoped by:

```ts
type ExecutionAccessScope = {
  app_id: string;
  session_id: string;
};
```

`ragenius_app_skeleton` must authenticate the user and verify that the stored
session belongs to the requested app and user before sending an authenticated
service-to-service request. The execution subsystem stores `app_id` and
`session_id` and uses both for status, logs, confirmation, and result retrieval.
Browser clients must not call the execution subsystem directly in production.

The initial implementation uses a configured service bearer credential:

```text
Authorization: Bearer <RAGenius execution service credential>
```

The execution subsystem validates the service credential before accepting the
app/session scope. User identity remains app-owned and is not required in the MVP
execution request or persisted execution record. Tests may inject a trusted
service principal directly. Production mode must fail startup when execution
service authentication is required but not configured.

An execution id is an identifier, not an authorization credential.

## Participating Subsystems

### `ragenius_app_skeleton`

Owns:

- Execution Composer GUI
- chat command construction
- `@exec` command routing
- session lane state
- approved content selection
- user-facing artifact selection
- display of execution status, confirmations, and results

Does not own:

- OpenClaw WSL invocation
- OpenClaw workspace paths
- artifact staging implementation
- artifact verification implementation
- provider-specific process management

### `ragenius_execution_subsystem`

Owns:

- execution request validation
- agent backend selection
- policy enforcement
- OpenClaw provider invocation
- input staging into the OpenClaw workspace
- output artifact verification
- normalized execution results
- provider diagnostics

Does not own:

- end-user chat UX
- app session lane rendering
- Builder admin workflows

### `ragenius_builder`

Phase 1 role:

- no runtime OpenClaw execution responsibility

Future role:

- skill definition and management
- published skill binding to apps
- admin configuration for skill/provider availability

Builder must not become the user-facing OpenClaw execution surface.

## End-to-End Flow

```text
ExecutionComposer.jsx
  -> App.jsx buildExecCommand(...)
  -> chat query with @exec command
  -> ragenius_app_skeleton backend exec_router.py
  -> execution_subsystem_client.submit_agent(...)
  -> ragenius_execution_subsystem POST /v1/executions
  -> ExecutionEngine execute_agent path
  -> OpenClaw provider
  -> normalized result
  -> app session lane state
  -> frontend execution display
```

## Command Contract

The app must support an OpenClaw agent command form.

Preferred Phase 1 command:

```text
@exec openclaw "<request>"
@exec async openclaw "<request>"
```

Optional future generic form:

```text
@exec agent openclaw "<request>"
```

Phase 1 should prefer `@exec openclaw` because it follows the existing `@exec codex` pattern and minimizes parser/UI disruption.

## App-to-Execution Request Contract

When the app backend receives an OpenClaw exec command, it must call the execution subsystem with:

```json
{
  "request_type": "execute_agent",
  "app_id": "app_001",
  "session_id": "sess_001",
  "agent_backend": "openclaw_cli",
  "agent_query": "user request",
  "approved_content_id": "optional",
  "approved_revision_id": "optional",
  "artifact_refs": [],
  "expected_outputs": [],
  "context": {
    "execution_mode": "sync",
    "approved_content": {},
    "openclaw": {
      "execution_mode": "read_only",
      "timeout_ms": 120000
    }
  },
  "execution_options": {
    "mode": "sync"
  }
}
```

Exact optional fields may evolve, but these rules are stable:

- `agent_backend` must be explicit.
- OpenClaw must not be inferred from free text.
- app/session ids must be preserved.
- the app backend must validate authenticated session ownership before submission.
- approved content metadata must remain app-owned and passed as context.
- provider file paths must not be invented by the app frontend.

### Exact Phase 1 Payload Shape

The app backend must submit this shape for OpenClaw agent runs:

```json
{
  "request_type": "execute_agent",
  "app_id": "app_001",
  "session_id": "sess_001",
  "agent_backend": "openclaw_cli",
  "agent_query": "Summarize the selected approved content into a reusable markdown artifact.",
  "approved_content_id": "ac_123",
  "approved_revision_id": "rev_456",
  "artifact_refs": [
    {
      "artifact_id": "art_001",
      "role": "source",
      "reuse_mode": "file_backed"
    }
  ],
  "expected_outputs": [
    {
      "output_id": "openclaw_answer",
      "display_name": "openclaw-result.md",
      "media_type": "text/markdown",
      "required": true,
      "persist_as_artifact": true,
      "artifact_type": "agent_output",
      "min_size_bytes": 1
    }
  ],
  "context": {
    "execution_mode": "sync",
    "approved_content": {
      "approved_content_id": "ac_123",
      "revision_id": "rev_456",
      "content_hash": "sha256:...",
      "content_text": "approved text when safe to send",
      "target_refs": []
    },
    "openclaw": {
      "execution_mode": "output_required",
      "timeout_ms": 120000
    }
  },
  "execution_options": {
    "mode": "sync"
  }
}
```

The app backend may omit top-level `artifact_refs` and `expected_outputs` for
simple read-only prompt runs. The execution subsystem generates a provider-neutral
default expected output when the run is classified as output-required. Resolved
OpenClaw staged inputs and workspace paths are internal provider data and never
part of the app-to-execution payload.

### Approved Content Assembly

For agent runs, the app backend must assemble approved content context explicitly.

Rules:

- If a selected approved content id exists, include `approved_content_id` and `approved_revision_id` at the top level.
- Include `context.approved_content` with revision metadata and safe content text when available.
- Include top-level `artifact_refs` for artifacts selected directly in the UI or
  inherited from approved content.
- Do not include OpenClaw workspace paths in this payload.

If approved content text is too large for direct context, the app may send only refs and hashes; the execution subsystem then resolves or rejects based on available artifact/context access.

## Response Contract

The execution subsystem response must remain compatible with existing app execution rendering.

Required high-level result states:

- `running`
- `completed`
- `partial`
- `failed`
- `pending_confirmation`
- `blocked`

Required agent metadata:

- `backend = "openclaw_cli"`
- provider display name, for example `OpenClaw`
- policy class
- execution id
- diagnostics summary

Required artifact metadata for output-producing runs:

- declared expected outputs
- verified outputs
- artifact names or paths safe for display
- verification status

The app must not parse raw OpenClaw stdout as the primary success signal.

### Exact Normalized Result Expectations

The app should expect OpenClaw details in normalized execution responses using this shape:

```json
{
  "status": "completed",
  "execution_id": "exec_123",
  "result": {
    "summary": "OpenClaw completed and verified 1 output.",
    "output_text": "Short provider-visible answer.",
    "artifacts": [
      {
        "artifact_id": "art_result_001",
        "display_name": "openclaw-result.md",
        "media_type": "text/markdown",
        "role": "final",
        "verified": true
      }
    ],
    "execution_metadata": {
      "agent_backend": "openclaw_cli",
      "provider_name": "OpenClaw",
      "policy_class": "agent_workspace_write"
    },
    "provider_metadata": {
      "backend": "openclaw_cli",
      "invocation_mode": "wsl_cli",
      "openclaw_session_key": "redacted-or-safe-key",
      "execution_mode": "output_required",
      "verified_output_count": 1,
      "required_output_count": 1,
      "timed_out": false
    },
    "verification_results": [
      {
        "output_id": "openclaw_answer",
        "verified": true,
        "size_bytes": 1024,
        "persisted_artifact_id": "art_result_001"
      }
    ],
    "logs_summary": {
      "stdout_truncated": false,
      "stderr_truncated": false,
      "redactions_applied": true
    }
  }
}
```

App rendering rules:

- use `result.summary` for the primary message
- use `result.artifacts` for reusable outputs
- use `verification_results` for inspector/debug UI
- do not parse raw provider stdout/stderr
- do not display WSL workspace paths as primary user-facing labels

## Approved Content Contract

Approved content remains owned by `ragenius_app_skeleton`.

The app may pass approved content to the execution subsystem as context.

The execution subsystem may transform approved content into staged OpenClaw workspace inputs when needed.

Rules:

- app stores and selects approved content
- execution subsystem stages provider-readable files
- OpenClaw receives only workspace-safe paths
- normalized results must not leak raw secret-bearing approved content

## Artifact Contract

The app frontend may let users select existing artifacts.

The app backend must pass artifact references, not OpenClaw workspace paths.

The execution subsystem resolves/stages those artifacts for OpenClaw.

Phase 1 may support:

- no input artifacts for read-only prompt runs
- approved content converted to a staged text input
- explicit expected text output generated by the execution subsystem

Binary artifact staging can remain provider-side and contract-covered even if the first GUI flow does not expose binary input selection.

### Artifact Reference Shape

The app must use this artifact ref shape when passing artifacts to execution:

```ts
type AppExecutionArtifactRef = {
  artifact_id: string;
  role: "source" | "context" | "template" | "attachment";
  reuse_mode: "inline_text" | "file_backed" | "binary_payload" | "metadata_only";
  display_name?: string;
  mime_type?: string;
};
```

Mapping to OpenClaw staged inputs:

- `inline_text` resolves bounded text into prompt context.
- `file_backed` stages a read-only copy under the execution run input root.
- `binary_payload` stages verified bytes under the execution run input root.
- `metadata_only` includes metadata without loading full content.

Transformation and append intent are not reuse modes. They are represented by
the user task plus provider-neutral `expected_outputs`; source artifacts are
always immutable.

The execution subsystem must not mutate the source artifact in place.

## Confirmation Contract

The execution subsystem remains responsible for deciding whether an agent request requires confirmation.

The public submission payload must not accept `require_confirmation = true` as
proof of approval. If the policy requires confirmation, the execution subsystem
returns `pending_confirmation` with a server-issued `confirmation_id`, records
its app/session scope and expiry, and does not invoke the provider.

The app remains responsible for:

- displaying the pending confirmation state
- retaining the server-issued confirmation id in backend session state
- calling `POST /v1/executions/:execution_id/confirm` with the execution scope,
  `confirmation_id`, and `decision = "approve"`
- updating session lane state after confirmation

OpenClaw must not introduce a separate confirmation mechanism.

The execution subsystem must atomically consume the confirmation and transition
`pending_confirmation -> running`. Repeated confirm requests must not invoke the
provider twice. Scope mismatch, expiry, or an invalid confirmation id must not
reveal whether another tenant's execution exists.

## Status Contract

Existing status flow must be reused.

The app calls:

```text
GET /v1/executions/:execution_id?app_id=...&session_id=...
```

The authenticated app client supplies the same `app_id` and `session_id`. The
execution subsystem performs a scoped lookup and returns normalized status. Logs
and confirmation use the same scope.

The app must not poll OpenClaw directly.

## Security and Isolation

Rules:

- every request must carry `app_id`
- every request must carry `session_id`
- execution results must remain app/session scoped
- the app must validate the authenticated user's ownership of the app/session
- status, logs, confirmation, and result lookups must match app and session
- no cross-app artifact leakage
- app frontend must not expose raw WSL paths as editable user fields
- execution subsystem must redact provider diagnostics before returning them
- scope mismatch must be indistinguishable from an unknown execution id

## Dry-Run Contract

The app may submit `execution_options.dry_run = true` to preview validation,
policy, backend selection, artifact resolution metadata, and expected outputs.
The execution subsystem must not invoke OpenClaw/Codex, stage files, create
outputs, persist artifacts, or consume confirmation state during a dry run.

## Terminal Status Mapping

The app renders the top-level execution status and must not infer success from a
nested provider status.

- `completed`: provider task succeeded and every required verification and
  requested persistence obligation succeeded.
- `partial`: the core task succeeded, but an optional expected output failed
  verification or requested optional persistence failed.
- `failed`: provider task failed, timed out, a required output failed
  verification, or required persistence failed.
- `blocked`: policy denied execution before provider invocation.

The execution subsystem must propagate provider `failed` to top-level `failed`.
It must preserve provider diagnostics inside the normalized result even when the
HTTP request itself was handled successfully.

## Compatibility

Codex agent mode must continue to work.

OpenClaw support must be additive:

- existing `@exec codex` commands continue to route to `codex_cli`
- existing Execution Composer tool/skill modes continue unchanged
- existing status and confirmation rendering continue to work

## Phase 1 Acceptance Criteria

The cross-subsystem flow is complete when:

1. Execution Composer can submit a Codex or OpenClaw agent request.
2. `App.jsx` serializes OpenClaw requests to a supported `@exec` command.
3. `exec_router.py` recognizes OpenClaw agent commands.
4. `execution_subsystem_client.py` submits `agent_backend = "openclaw_cli"`.
5. `ragenius_execution_subsystem` accepts and dispatches OpenClaw requests.
6. app session lane state records OpenClaw execution ids and results.
7. frontend status/confirmation/result UI works without direct OpenClaw knowledge.
