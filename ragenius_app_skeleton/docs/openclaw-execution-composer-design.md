# OpenClaw Execution Composer Design

Date: 2026-06-14

## Shared Agent Design Reference

`docs/superpowers/specs/2026-08-03-agent-execution-lifecycle-evidence-design.md`
defines shared queued/running behavior, normalized evidence, trusted artifact
actions, and app transport requirements for Codex and OpenClaw. This document
remains authoritative for OpenClaw Composer routing and presentation details.

## Goal

Add OpenClaw as a selectable agent backend in `ragenius_app_skeleton` without moving provider execution logic into the app.

## Design Summary

The app remains the user-facing execution surface. Execution Composer lets the user choose an agent backend, `App.jsx` serializes that choice into an `@exec` command, the backend router parses it, and `execution_subsystem_client.py` submits an explicit `agent_backend` to `ragenius_execution_subsystem`.

The app does not invoke OpenClaw directly.

## Execution Security And Lifecycle Design

This section is normative for the hardening implementation.

### Trust Boundary

The browser talks to `ragenius_app_skeleton`; it must not call
`ragenius_execution_subsystem` directly in production. The app backend verifies
that the authenticated user owns the stored app/session, then sends only the
execution scope over an authenticated service-to-service channel:

```python
execution_scope = {
    "app_id": app_id,
    "session_id": session_id,
}
```

The execution client must include this scope for submission, status, logs, and
confirmation. User identity remains app-owned and is not persisted by the MVP
execution subsystem.

### Confirmation UX And Backend State

The initial request does not send `require_confirmation = true` as approval. A
`pending_confirmation` response includes a server-issued `confirmation_id`,
reason, policy class, and expiry. The app backend stores that data in the session
execution lane and exposes only the information needed to render confirmation.

When the user approves, the frontend calls the app backend. The app backend then
submits the stored `confirmation_id`, `decision = "approve"`, and authenticated
execution scope to the execution subsystem. It must not synthesize confirmation
ids or replay the original request with an approval boolean.

Disable the confirmation action after submission. If a retry receives an
existing `running` or terminal state, render that state instead of starting a new
execution.

### Status Rendering

Execution cards use only the normalized top-level status:

- `pending_confirmation`: show confirmation action
- `running`: show in-progress state and status refresh
- `completed`: show successful result and persisted artifacts
- `partial`: show result plus warnings and any successfully persisted artifacts
- `failed`: show failure summary and inspector action
- `blocked`: show policy denial

The app must not infer success from HTTP `200`, raw OpenClaw output, or a nested
provider status.

### Dry Run

If Composer exposes dry run, label it as a preview. A dry-run result may show
backend, policy, required confirmation, selected artifacts, and expected outputs,
but must not be added to the Artifact Library as if execution occurred.

## Files to Modify

- `frontend/src/components/ExecutionComposer.jsx`
- `frontend/src/App.jsx`
- `backend/app/exec_router.py`
- `backend/app/execution_subsystem_client.py`
- `backend/app/main.py`
- `backend/tests/test_chat_exec_routing.py`
- `frontend/src/App.test.jsx`
- `frontend/src/components/ExecutionComposer.test.jsx`

## Command Syntax

Add OpenClaw command support beside existing Codex support.

Existing:

```text
@exec codex "<request>"
@exec async codex "<request>"
@exec codex use <skill> "<request>"
```

New Phase 1:

```text
@exec openclaw "<request>"
@exec async openclaw "<request>"
```

Do not remove or rename Codex commands.

## ExecutionComposer Changes

Current agent mode hardcodes:

```js
targetId: "codex_cli"
```

Target behavior:

- add `agentBackend` state
- default to `codex_cli` for backward compatibility
- offer `Codex CLI` and `OpenClaw CLI`
- show backend-specific helper copy
- submit `targetId` equal to selected backend

Conceptual payload:

```js
{
  commandKind: "agent",
  targetId: "openclaw_cli",
  executionMode: "sync",
  args: {
    request: "Summarize the approved content."
  }
}
```

For Codex, existing skill hint behavior remains available.

For OpenClaw Phase 1, hide or disable Codex-specific skill hints unless a future OpenClaw skill hint contract is defined.

### Agent Artifact Selection

Phase 1 Composer behavior:

- Codex agent mode remains unchanged.
- OpenClaw agent mode supports selected approved content immediately.
- Direct artifact selection in agent mode may be added only if it emits artifact refs, not provider paths.

If direct artifact selection is exposed for OpenClaw, Composer must submit:

```js
{
  commandKind: "agent",
  targetId: "openclaw_cli",
  executionMode: "sync",
  args: {
    request: "Transform this source into a markdown summary.",
    artifactRefs: [
      {
        artifact_id: "art_001",
        role: "source",
        reuse_mode: "file_backed",
        display_name: "source.pdf",
        mime_type: "application/pdf"
      }
    ]
  }
}
```

The app backend converts these refs into execution context. Composer must not expose or accept OpenClaw workspace paths.

## App.jsx Command Building

Current `buildExecCommand(...)` serializes all agent requests to `@exec codex`.

Target behavior:

```js
if (commandKind === "agent") {
  if (targetId === "openclaw_cli") {
    return `${execPrefix} openclaw "${escapedRequest}"`;
  }
  return existingCodexCommand;
}
```

`approvedContentId` handling currently applies only to tool/skill command strings. For agent commands, approved content is already resolved through backend session context. Keep that behavior unless the backend requires an explicit command argument later.

Concrete Phase 1 rule:

- `@exec openclaw "<request>"` does not include `approvedContentId` in the command string.
- The backend must attach selected approved content from session state exactly as it does for Codex agent runs.
- If direct artifact refs are added to Composer agent payloads, they should be sent through backend context, not serialized into a fragile chat command string.

## Router Changes

`backend/app/exec_router.py` must recognize:

```text
openclaw
```

It should produce a route decision equivalent to Codex agent mode, but with:

```python
command = "openclaw"
agent_backend = "openclaw_cli"
```

If the existing `ExecRouteDecision` lacks `agent_backend`, add it as an optional field.

Error messages should list supported commands:

```text
tool, skill, codex, openclaw, status
```

Concrete route decision shape:

```python
ExecRouteDecision(
    is_exec_turn=True,
    command="openclaw",
    agent_backend="openclaw_cli",
    execution_mode=execution_mode,
    agent_query=agent_query,
    raw_args=rest,
    parsed_args={
        "execution_mode": execution_mode,
        "agent_backend": "openclaw_cli",
    },
)
```

## Execution Client Changes

Current:

```python
"agent_backend": "codex_cli"
```

Target:

```python
def submit_agent(..., agent_backend: str = "codex_cli", ...):
    payload = {
        "request_type": "execute_agent",
        "agent_backend": agent_backend,
        ...
    }
```

The client should not infer OpenClaw from request text.

Add scoped client methods for status, logs, and confirmation. These methods must
always receive the authenticated execution scope and must never issue an
execution-id-only request.

## Main Backend Flow

Current `_handle_exec_codex_turn(...)` is Codex-specific.

Target options:

1. Rename to `_handle_exec_agent_turn(...)` and pass backend/display metadata.
2. Keep the function name temporarily but add OpenClaw branching.

Preferred design:

- introduce `_handle_exec_agent_turn(...)`
- route both `codex` and `openclaw` through it
- preserve Codex response shape for compatibility

Session lane state should record:

- latest execution id
- latest command, for example `openclaw`
- latest agent backend
- latest request query
- latest result
- latest execution mode

Concrete lane fields:

```python
execution_lane = {
    "latest_execution_id": "...",
    "latest_execution_intent_id": "...",
    "latest_execution_request_skill_id": "openclaw_cli",
    "latest_execution_request_query": "...",
    "latest_agent_backend": "openclaw_cli",
    "latest_execution_mode": "sync",
    "latest_execution_result": submit_result,
}
```

Existing UI should continue to render status and confirmation results.

## Frontend Display

Execution result cards should display OpenClaw distinctly when metadata is present:

- `OpenClaw`
- `openclaw_cli`
- policy class
- status
- diagnostics summary

Do not display raw WSL command strings or raw workspace paths as primary UI.

Safe artifact names and verification summaries may be displayed.

## Approved Content

Approved content behavior remains app-owned.

When OpenClaw is selected:

- the selected approved revision remains visible in Composer
- the backend passes approved content context to the execution subsystem
- the execution subsystem decides how to stage it

The app frontend should not expose OpenClaw workspace staging details.

The backend must pass approved content context explicitly:

```python
context = {
    "execution_mode": execution_mode or "sync",
    "approved_content": {
        "approved_content_id": approved_content_id,
        "revision_id": approved_revision_id,
        "content_hash": content_hash,
        "content_text": content_text,
        "artifact_refs": artifact_refs,
        "target_refs": target_refs,
    },
    "artifact_refs": artifact_refs,
}
```

If OpenClaw is selected and approved content exists, the backend should set `context.openclaw.execution_mode = "output_required"` when the request asks for a reusable output.

## Artifact Selection

Phase 1 can start with prompt-only and approved-content-driven OpenClaw runs.

If agent-mode artifact selection is added, the app should pass artifact references, not OpenClaw paths.

The execution subsystem remains responsible for staging artifacts into the OpenClaw workspace.

Artifact ref shape:

```js
{
  artifact_id: "art_001",
  role: "source",
  reuse_mode: "file_backed",
  display_name: "source.md",
  mime_type: "text/markdown"
}
```

Allowed provider-neutral `reuse_mode` values:

- `inline_text`
- `file_backed`
- `binary_payload`
- `metadata_only`

Transform intent belongs in the user request and provider-neutral
`expected_outputs`, not in an OpenClaw-specific reuse mode.

## Tests

Frontend tests:

- Composer defaults to Codex agent backend.
- Composer can select OpenClaw agent backend.
- Composer submits `targetId = "openclaw_cli"` for OpenClaw.
- `buildExecCommand` returns `@exec openclaw "..."` for OpenClaw.
- `buildExecCommand` keeps existing `@exec codex ...` behavior.
- OpenClaw Composer does not show Codex-only skill hints.
- OpenClaw Composer does not expose workspace path fields.
- OpenClaw artifact refs are submitted as refs when agent artifact selection is enabled.

Backend tests:

- parser accepts `@exec openclaw "hello"`.
- parser accepts `@exec async openclaw "hello"`.
- parser rejects missing OpenClaw request with a clear message.
- app backend submits `agent_backend = "openclaw_cli"`.
- Codex route still submits `agent_backend = "codex_cli"`.
- pending confirmation and confirm flows still work for agent backends.
- OpenClaw agent run includes approved content context when selected approved content exists.
- OpenClaw agent run records `latest_agent_backend = "openclaw_cli"`.
- OpenClaw route does not serialize provider workspace paths.
- app backend validates authenticated session ownership before execution operations.
- status and logs include app/session scope.
- confirmation uses the stored server-issued confirmation id, not a public
  approval flag.
- repeated confirmation renders existing state without duplicating execution.
- `partial` and `failed` render from top-level status without parsing raw output.
- dry-run results do not create user artifact actions.

## Non-Goals

- invoking OpenClaw from the frontend
- exposing WSL paths in editable GUI fields
- moving Builder admin workflows into the app
- replacing `@exec codex`
- adding Builder skill creation support

## Implementation Order

The original OpenClaw Composer work is complete. Apply hardening in this order:

1. Propagate app/session scope through the authenticated execution client.
2. Scope status, logs, and confirmation requests.
3. Replace approval-boolean replay with server-issued confirmation state.
4. Render `running`, `partial`, and provider-propagated `failed` statuses.
5. Add dry-run presentation without artifact actions.
6. Run Codex, OpenClaw, tool, skill, status, and confirmation regressions.
