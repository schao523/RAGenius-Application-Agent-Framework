# OpenClaw Agent Execution Integration Contract

Date: 2026-06-14

## Purpose

This document defines the cross-subsystem contract for OpenClaw-backed agent execution from `ragenius_app_skeleton` through `ragenius_execution_subsystem`.

It exists to keep responsibilities explicit and prevent runtime execution logic from leaking into the wrong subsystem.

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
  "context": {
    "execution_mode": "sync",
    "approved_content": {},
    "artifact_refs": [],
    "openclaw": {
      "expected_outputs": [],
      "staged_inputs": []
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
  "context": {
    "execution_mode": "sync",
    "approved_content": {
      "approved_content_id": "ac_123",
      "revision_id": "rev_456",
      "content_hash": "sha256:...",
      "content_text": "approved text when safe to send",
      "artifact_refs": [
        {
          "artifact_id": "art_001",
          "artifact_version_id": "v1",
          "role": "source"
        }
      ],
      "target_refs": []
    },
    "artifact_refs": [
      {
        "artifact_id": "art_001",
        "artifact_version_id": "v1",
        "role": "source",
        "reuse_mode": "read"
      }
    ],
    "openclaw": {
      "execution_mode": "output_required",
      "timeout_ms": 120000,
      "staged_inputs": [
        {
          "input_id": "approved_content_rev_456",
          "source_kind": "approved_content",
          "source_ref": {
            "approved_content_id": "ac_123",
            "approved_revision_id": "rev_456"
          },
          "display_name": "approved-content.md",
          "media_type": "text/markdown",
          "encoding": "utf8",
          "content_sha256": "sha256..."
        }
      ],
      "expected_outputs": [
        {
          "output_id": "openclaw_answer",
          "purpose": "answer",
          "display_name": "openclaw-result.md",
          "media_type": "text/markdown",
          "required": true,
          "persist_as_artifact": true,
          "artifact_role": "final",
          "min_size_bytes": 1
        }
      ]
    }
  },
  "execution_options": {
    "mode": "sync"
  }
}
```

The app backend may omit `context.openclaw.staged_inputs` and `context.openclaw.expected_outputs` for simple read-only prompt runs. The execution subsystem must generate defaults when the run is classified as output-required.

### Approved Content Assembly

For agent runs, the app backend must assemble approved content context explicitly.

Rules:

- If a selected approved content id exists, include `approved_content_id` and `approved_revision_id` at the top level.
- Include `context.approved_content` with revision metadata and safe content text when available.
- Include `context.approved_content.artifact_refs` when the approved revision points to artifacts.
- Include `context.artifact_refs` for artifacts selected directly in the UI or inherited from approved content.
- Do not include OpenClaw workspace paths in this payload.

If approved content text is too large for direct context, the app may send only refs and hashes; the execution subsystem then resolves or rejects based on available artifact/context access.

## Response Contract

The execution subsystem response must remain compatible with existing app execution rendering.

Required high-level result states:

- `completed`
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
  artifact_version_id?: string;
  role: "source" | "context" | "template" | "attachment";
  reuse_mode: "read" | "transform" | "append" | "reference_only";
  display_name?: string;
  media_type?: string;
};
```

Mapping to OpenClaw staged inputs:

- `read` maps to `source_kind = "artifact"` and a read-only staged input.
- `transform` maps to a staged input plus at least one required expected output.
- `append` is not supported for OpenClaw Phase 1 unless the execution subsystem can create a safe copy and verify output separately.
- `reference_only` should be included in prompt context but not staged unless needed.

The execution subsystem must not mutate the source artifact in place.

## Confirmation Contract

Existing confirmation flow must be reused.

The execution subsystem remains responsible for deciding whether an agent request requires confirmation.

The app remains responsible for:

- displaying the pending confirmation state
- calling `POST /v1/executions/:execution_id/confirm`
- updating session lane state after confirmation

OpenClaw must not introduce a separate confirmation mechanism.

## Status Contract

Existing status flow must be reused.

The app calls:

```text
GET /v1/executions/:execution_id
```

The execution subsystem returns normalized status.

The app must not poll OpenClaw directly.

## Security and Isolation

Rules:

- every request must carry `app_id`
- every request must carry `session_id`
- execution results must remain app/session scoped
- no cross-app artifact leakage
- app frontend must not expose raw WSL paths as editable user fields
- execution subsystem must redact provider diagnostics before returning them

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
