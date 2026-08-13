# Interactive Agent Execution Contract

Date: 2026-08-13

## Status

Normative cross-subsystem addendum for interactive Agent execution through
Codex app-server and OpenClaw Gateway.

This contract extends:

- `docs/agent-execution-lifecycle-evidence-contract.md`
- `docs/agent-skill-discovery-selection-contract.md`
- `docs/agent-mode-artifact-creation-reuse-contract.md`
- `docs/openclaw-agent-execution-integration-contract.md`

Those contracts remain authoritative unless this addendum explicitly changes
interactive lifecycle or provider-session behavior.

## Purpose

An Agent may need a user decision after provider invocation has started.
RAGenius must mediate that decision without exposing provider credentials,
parsing terminal prompts, weakening policy, or confusing ordinary input with
authorization.

## Product Boundary

`ragenius_app_skeleton` owns authenticated user/session checks, interaction UX,
polling or streaming from its backend, and user-visible history.

`ragenius_execution_subsystem` owns Agent sessions, normalized events,
interaction state, policy binding, provider communication, cancellation,
recovery, artifact verification, and authoritative execution status.

Provider adapters own protocol translation and protected provider handles.

`ragenius_builder` owns administrator-reviewed interaction capability metadata
for governed Agent skills. It has no live interaction or provider-session role.

Browser clients must not connect directly to Codex app-server, OpenClaw
Gateway, or the execution subsystem in production.

## Lifecycle

The lifecycle becomes:

```text
pending_confirmation -> queued -> running <-> waiting_for_interaction
                                   |                  |
                                   +-> completed | partial | failed | cancelled

blocked remains terminal before provider invocation.
```

Rules:

- `pending_confirmation` remains the single-use RAGenius pre-execution policy
  confirmation. It must not store provider-time interactions.
- `waiting_for_interaction` is non-terminal and means at least one required,
  unresolved interaction is blocking provider progress.
- The interaction record, not another top-level status, distinguishes approval,
  clarification, selection, authentication handoff, and user action.
- `cancelled` is terminal only after a user or trusted service cancellation and
  bounded provider cleanup or reconciliation.
- Timeout remains `failed` with the existing timeout diagnostics.
- Process loss or restart remains `failed` with
  `AGENT_EXECUTION_INTERRUPTED` unless the adapter successfully reconciles an
  authoritative provider state.

## Identity Model

```ts
type AgentSessionRecord = {
  agent_session_id: string;
  execution_id: string;
  app_id: string;
  session_id: string;
  backend: "codex_cli" | "openclaw_cli";
  transport: "codex_app_server" | "openclaw_gateway";
  state:
    | "starting"
    | "running"
    | "waiting_for_interaction"
    | "completed"
    | "failed"
    | "cancelled";
  provider_session_ref: string;
  provider_run_ref: string | null;
  provider_turn_ref: string | null;
  continuation_mode: "same_turn" | "same_session_new_turn";
  protocol_version: string;
  capability_snapshot: AgentInteractionCapabilities;
  last_event_seq: number;
  created_at: string;
  updated_at: string;
};
```

Provider references are protected service data. App-facing APIs return only the
RAGenius `agent_session_id`, capability summary, and normalized state.
Provider credentials, tokens, session files, sockets, and raw handles are never
returned.

One execution has at most one active Agent session but may contain multiple
provider runs, turns, and interactions.

## Capability Contract

```ts
type AgentInteractionType =
  | "approval"
  | "clarification"
  | "selection"
  | "authentication_handoff"
  | "user_action_required";

type AgentInteractionCapabilities = {
  protocol_transport: boolean;
  same_turn_resume: boolean;
  same_session_continuation: boolean;
  cancellation: boolean;
  reconnect_reconciliation: boolean;
  event_replay: "none" | "bounded" | "documented";
  interaction_types: AgentInteractionType[];
};
```

Capabilities come from the active adapter's tested protocol version and
runtime preflight. Skill metadata may require or raise capabilities but may not
claim that an unavailable provider capability exists.

The initial verified profiles are:

- Codex app-server: approvals, clarification/selection through the managed
  RAGenius dynamic tool, same-turn resume, cancellation, session continuation.
- OpenClaw Gateway: execution approvals when administrator-enabled, session
  continuation, cancellation, and reconciliation. Clarification is unavailable
  until a managed OpenClaw interaction tool is implemented and verified.

## Interaction Record

```ts
type AgentInteractionRecord = {
  interaction_id: string;
  execution_id: string;
  agent_session_id: string;
  app_id: string;
  session_id: string;
  sequence: number;
  type: AgentInteractionType;
  state: "pending" | "resolving" | "resolved" | "expired" | "cancelled";
  prompt: string;
  options: Array<{ id: string; label: string; description?: string }>;
  allows_free_text: boolean;
  secret_input: false;
  provider_correlation_ref: string;
  policy_binding_hash: string;
  version: number;
  expires_at: string;
  resolved_at: string | null;
  response_summary: Record<string, unknown> | null;
};
```

Rules:

- An execution may have multiple interactions; each has its own sequence and
  provider correlation reference.
- `secret_input` is always false. Passwords, OTPs, cookies, access tokens, and
  recovery codes must not be submitted through this channel.
- Payloads are bounded, schema-validated, redacted, and stored independently of
  raw provider output.
- Only one pending blocking interaction is exposed as actionable in the MVP.
  Additional provider requests are durably recorded and processed in sequence.
- Provider prose is not an interaction. Only a typed adapter event or a managed
  RAGenius interaction tool may create a record.

## Response Contract

```ts
type AgentInteractionResponse = {
  expected_version: number;
  idempotency_key: string;
  response:
    | { kind: "approval"; decision: "allow_once" | "deny" | "cancel_execution" }
    | { kind: "selection"; option_ids: string[] }
    | { kind: "clarification"; text: string }
    | { kind: "user_action"; outcome: "completed" | "cancelled" };
};
```

The execution subsystem must atomically claim a pending interaction using
`interaction_id`, complete `{app_id, session_id, execution_id}` scope,
`expected_version`, and `idempotency_key`.

Responses are single-use and idempotent. A duplicate idempotency key returns
the original normalized outcome. A stale version, expired record, mismatched
type, or wrong scope fails closed without contacting the provider.

`allow_once` authorizes only the exact provider request bound by
`policy_binding_hash`. `allow-always`, allowlist mutation, provider policy
amendments, and session-wide approval are excluded from the initial release.

Ordinary clarification and selection responses cannot authorize filesystem,
network, credential, external-write, or destructive operations.

## Authentication And User Action

Authentication is a handoff, not an input form. The interaction may provide a
bounded instruction and an administrator-approved launch target. The user acts
in the provider-controlled browser or application and returns only
`outcome: completed` or `cancelled`.

After `completed`, the adapter reruns a non-mutating capability/authentication
check. User assertion alone is not proof of authentication.

## Event Contract

```ts
type AgentExecutionEvent = {
  execution_id: string;
  sequence: number;
  type:
    | "session_started"
    | "run_started"
    | "progress"
    | "message_delta"
    | "message_completed"
    | "tool_started"
    | "tool_completed"
    | "interaction_requested"
    | "interaction_resolved"
    | "warning"
    | "error"
    | "run_completed"
    | "run_cancelled";
  provider_event_ref?: string;
  interaction_id?: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};
```

Events are append-only, monotonically sequenced per execution, bounded,
redacted, and deduplicated by provider event reference where available. Raw
reasoning, secrets, credential paths, and unbounded command output are not
public event payloads.

Polling with `after_sequence` is required initially. SSE may be added without
changing event semantics. Event delivery is not the source of truth; after a
gap or reconnect, RAGenius reconciles provider status and persisted session
state.

## Service APIs

Execution-subsystem service endpoints:

```text
GET  /v1/executions/{execution_id}/interactions?app_id=&session_id=
POST /v1/executions/{execution_id}/interactions/{interaction_id}/responses
GET  /v1/executions/{execution_id}/events?app_id=&session_id=&after_sequence=
POST /v1/executions/{execution_id}/cancel
```

All endpoints require existing service authentication and complete execution
scope. The app backend provides user/session-scoped proxy endpoints and must
verify session ownership before every request.

## Preflight

Before starting an interactive transport, the execution subsystem validates:

- provider and protocol version;
- required transport and authentication state;
- adapter capability profile;
- selected skill interaction requirements;
- required binaries, platform, workspace, and staged artifacts;
- Gateway scope requirements such as `operator.approvals`;
- administrator-enabled provider approval behavior where required.

Preflight is read-only and must not refresh credentials, change approval
configuration, install software, or mutate provider policy without a separate
administrator action.

## Builder Skill Metadata

The synchronized trusted read model adds administrator-reviewed fields:

```ts
type AgentSkillInteractionPolicy = {
  interaction_requirement: "autonomous" | "conditional" | "required";
  supported_interaction_types: AgentInteractionType[];
  required_transport: "one_shot" | "interactive";
  recovery_class: "not_resumable" | "session_resumable" | "turn_resumable";
};
```

These fields are included in the reviewed fingerprint and published projection.
They may raise the minimum execution requirements and risk but never lower
runtime policy. Existing approval and app binding remain mandatory.

## Cancellation And Recovery

- Cancellation is scoped, idempotent, and records who requested it.
- Pending interactions become `cancelled` before provider cancellation begins.
- Codex cancellation targets the exact thread and turn.
- OpenClaw cancellation targets the exact canonical session key and run id.
- The adapter attempts bounded cleanup, then reconciles provider state.
- On reconnect, the adapter uses provider lookup/wait APIs; it does not assume
  missed events will replay.
- A provider still running after bounded cancellation produces failed cleanup
  diagnostics and must not be reported as successfully cancelled.

## Fallback And Rollout

Existing `codex exec --json` and `openclaw agent --json` providers remain
available for autonomous executions. Interactive requirements must fail closed
when only the one-shot transport is available; they must not silently fall back
and complete from conversational text.

Interactive transports are feature-gated per provider. Capability preflight,
mocked protocol tests, and provider-version smoke tests are required before
enabling them for users.
