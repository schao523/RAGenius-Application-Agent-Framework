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

## Request-Side Interaction Requirements

An `execute_agent` request may explicitly require a bounded non-authorizing
interaction even when `agent_skill_ref` is omitted:

```ts
type AgentRequestInteractionRequirements = {
  transport?: "interactive";
  style?: "structured" | "chat";
  allowed_types?: Array<"clarification" | "selection">;
  required_types?: Array<"clarification" | "selection">;
};
```

Rules:

- Omission means the request does not itself require interactive transport.
  Existing governed skill policy can still require it.
- Structured style has at least one allowed or required type. Both arrays are
  unique and limited to `clarification` and `selection`. A required type is
  implicitly allowed.
- Chat style advertises no typed interaction types. It requires the adapter's
  tested `chat_level_interaction` capability and preserves a provider session
  across completed runs.
- `allowed_types` advertises interaction capabilities that may be used without
  requiring any of them to occur. `required_types` additionally requires each
  listed type to be observed before successful completion.
- Presence forces capability preflight and interactive transport. It never
  falls back to a one-shot provider.
- Runtime requirements are the strict union of explicit request requirements
  and the selected skill's administrator-reviewed interaction policy. A
  request may raise requirements but cannot weaken skill governance.
- Every explicitly required type must be observed as a typed provider
  interaction before successful terminal completion. If the provider finishes
  without requesting it, the execution fails with
  `REQUIRED_INTERACTION_NOT_OBSERVED`.
- Requirement resolution uses this precedence: administrator-reviewed skill
  policy, explicit request metadata, then conservative high-confidence query
  inference. Query inference may only raise requirements for unambiguous
  imperative phrases such as "ask me to select/choose" or "ask me for
  clarification". Ambiguous collaborative wording must not create a required
  type. Inferred requirements are recorded in normalized execution metadata.
- Interactive Agent mode in Composer sends structured style with clarification
  and selection allowed for Codex, and chat style for OpenClaw. Advanced
  structured clients may supply `required_types`; callers cannot use explicit
  metadata to weaken skill policy or an unambiguous inferred requirement.
- When structured interaction is enabled, the Codex adapter supplies trusted
  protocol guidance requiring `ragenius_request_input` for any allowed user
  input. It must not force a tool call when input is unnecessary, and Codex
  must not represent a required interaction using ordinary assistant prose.
- A clarification or selection response remains content input only. It cannot
  authorize filesystem, network, credential, destructive, or external-write
  operations.

The initial verified profiles are:

- Codex app-server: approvals, clarification/selection through the managed
  RAGenius dynamic tool, same-turn resume, cancellation, session continuation.
- OpenClaw Gateway: execution approvals when administrator-enabled, session
  continuation, cancellation, and reconciliation. On OpenClaw 2026.6.8 an
  external approval adapter requires both `operator.admin` and
  `operator.approvals`; `operator.approvals` alone has cross-request visibility
  only for OpenClaw's process-internal approval runtime. Clarification is
  unavailable until a managed OpenClaw interaction tool is implemented and
  verified.

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

The execution subsystem enforces single-use state before provider contact. A
provider may accept a duplicate resolution idempotently; that behavior does not
permit a second RAGenius response or another provider call. Provider resolution
acknowledgement and normalized interaction resolution are separate records.

`allow_once` authorizes only the exact provider request bound by
`policy_binding_hash`. `allow-always`, allowlist mutation, provider policy
amendments, and session-wide approval are excluded from the initial release.

Ordinary clarification and selection responses cannot authorize filesystem,
network, credential, external-write, or destructive operations.

## Interactive Inputs And Final Outputs

- Selected artifact references are resolved under the existing app/session
  scope and staged into the execution-owned interactive workspace before the
  provider turn starts. The trusted prompt identifies only staged relative
  paths; browser-local and artifact-store paths are never exposed.
- Interactive message deltas are bounded and accumulated into one normalized
  final assistant response. Completion status alone is not a user result.
- When an interactive provider session is explicitly finished, the app backend
  may project the normalized final assistant response into session chat history.
  That projection must be idempotent by execution and final-turn identity and
  must preserve its Agent backend provenance. Refresh or retry must not create
  duplicate assistant messages.
- A terminal or explicitly closed Agent session must not continue presenting an
  actionable interaction composer. Provider prose cannot keep or reopen an
  interaction after authoritative session state becomes terminal.
- `persist_as_artifact: true` on an expected output persists the normalized
  final assistant response as an `agent_output` artifact when the request is
  conversational and does not require a provider-created file.
- A request that explicitly requires a named file or byte-level verification
  continues to use workspace output planning, path confinement, verification,
  and then artifact persistence. Capturing response text must not falsely
  satisfy a required provider-created file.
- If persistence was not requested, the final response remains execution
  result content and no reusable artifact is created.

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

Provider events without a transport sequence still receive a RAGenius event
sequence. OpenClaw approval events are deduplicated by the compound provider
reference `{approval_id, event_kind}` because OpenClaw 2026.6.8 does not attach
a Gateway sequence to those events.

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
- explicit request-side interaction requirements;
- required binaries, platform, workspace, and staged artifacts;
- Gateway scope requirements. OpenClaw 2026.6.8 external approval mediation
  requires both `operator.admin` and `operator.approvals`;
- administrator-enabled provider approval behavior where required.

OpenClaw approval preflight also requires effective `security: allowlist`,
`ask: on-miss`, and `askFallback: deny`. `ask: on-miss` with
`security: full` is not approval-capable because no command produces an
allowlist miss.

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
- OpenClaw expiry may return `decision: null` without emitting an
  `exec.approval.resolved` event. The adapter expires the local interaction from
  the provider response or elapsed authoritative expiry, not from a required
  resolved event.
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
