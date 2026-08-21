# OpenClaw Chat-Level Interaction Design

Date: 2026-08-21

## Status

Approved for staged implementation planning on 2026-08-21. No production
capability is authorized until the production acceptance gate passes.

## Goal

Support OpenClaw conversational selection, clarification, review, revision,
continuation, and cancellation without a custom structured wait plugin.
RAGenius preserves one OpenClaw session and starts a new provider run for each
user follow-up.

## Non-Goals

- Do not parse Agent prose into typed interactions.
- Do not advertise OpenClaw typed clarification or selection.
- Do not resume a completed provider run.
- Do not provide exactly-once follow-up or external-write guarantees.
- Do not implement TaskFlow, a YouTube adapter, or a generic workflow engine.
- Do not replace Codex typed interactions or OpenClaw execution approvals.

## Architecture

```text
Execution Composer / chat
  -> ragenius_app_skeleton ownership-checked proxy
  -> execution-subsystem chat-session API
  -> InteractiveAgentSessionManager
  -> OpenClawGatewayAdapter
  -> Gateway agent(sessionKey=stable, runId=new)
```

The existing provider-neutral session, event, execution, artifact, and
confirmation stores remain authoritative. Chat follow-ups use a separate API
and store path from `AgentInteractionRecord`.

### Session Versus Run

The session is the continuity anchor. A run is one bounded provider invocation.
The Agent session persists:

```text
agent_session_id
execution scope
canonical provider_session_ref
current provider_run_ref
turn_sequence
session_version
state
idle_expires_at
capability snapshot
```

Every accepted follow-up increments `turn_sequence` and updates the current run
reference. Prior run identifiers remain visible only through bounded internal
event history.

### Lifecycle Changes

Add `ready_for_follow_up` to Agent-session and execution lifecycle schemas.
For chat-level OpenClaw sessions, `run_completed` records the turn result and
moves to `ready_for_follow_up`. It does not clear the adapter's session mapping.

Submitting a follow-up atomically claims the current session version, moves it
to `running`, invokes `agent` with the same canonical session key, records the
new run id, and emits `run_started`. A successful turn returns to
`ready_for_follow_up`.

`End session` and idle expiry transition an idle chat session to `completed`.
Authoritative cancellation transitions an active session to `cancelled` only
after provider confirmation.

### Adapter Changes

Extend the provider-neutral adapter with an optional chat operation rather than
overloading typed `respond`:

```ts
sendFollowUp(handle, claim): Promise<ProviderSessionHandle>
```

The OpenClaw implementation:

1. validates that no run is active;
2. submits `agent` with the protected canonical session key;
3. supplies a turn-specific idempotency key;
4. validates the returned run id;
5. replaces active run routing without replacing session routing;
6. streams and reconciles the new run normally.

The protected handle becomes session-stable and run-mutable. Event routing must
remove the old run alias before registering the new run. Session aliases remain
exact and agent-scoped.

### Persistence And Idempotency

Add a durable chat-turn record containing RAGenius scope, turn sequence,
idempotency key, bounded request summary, state, provider acknowledgement
status, timestamps, and normalized result. Do not persist raw provider keys,
unbounded messages, secrets, or raw reasoning.

Allowed turn states are:

```text
claimed -> submitted -> running -> completed | failed | cancelled
                    \-> delivery_unknown
```

Conditional updates serialize turns. A second concurrent submission receives
`CHAT_RUN_ALREADY_ACTIVE`. Same-key retries replay the stored outcome. After an
ambiguous provider acknowledgement, reconciliation must inspect the canonical
session before allowing another turn.

The serialization primitive is durable: use a database conditional update or
lease keyed by Agent session and expected session version. OpenClaw accepted
two concurrent distinct idempotency keys in live testing, so adapter-local or
process-local maps cannot enforce this invariant.

Persist provider acknowledgement separately from terminal outcome. Provider
same-key replay returned the same run id in live testing, but it does not
replace RAGenius idempotency and recovery records.

### Policy Handling

The initial execution's policy decision and immutable operation plan define the
maximum follow-up envelope. Follow-ups are classified before provider contact.
Equal-or-lower-risk conversational input may continue. Escalation, new
artifacts, broader access, a different selected skill, or a new external write
returns `CHAT_FOLLOW_UP_REQUIRES_NEW_EXECUTION`.

This avoids adding mid-execution confirmation semantics in the MVP. A future
design may support a new single-use confirmation per turn.

### App Design

Do not reuse `AgentInteractionCard` for chat follow-ups. Add a separate
OpenClaw follow-up panel shown only in `ready_for_follow_up`:

- free-text `Reply`;
- `Continue` shortcut;
- `Revise` with required text;
- `Graceful cancel` shortcut;
- `End session`;
- `Cancel current run` only while running.

Buttons create ordinary bounded follow-up messages. The UI never extracts
options from prose automatically. It shows submitting, active-run, stale
version, delivery-unknown, expired, closed, and cancellation states.

### Builder Design

Builder reviews `interaction_channel` as fingerprinted governance metadata.
TaskFlow approval does not prove runtime availability: discovery, observed
fingerprint, app binding, published projection, provider version, and
chat-level preflight must all agree at execution time.

### Recovery

On connection loss, the adapter reconciles the canonical session and current
run through provider lookup and `agent.wait`; it assumes no event replay. An
idle session may remain continuable after reconnection or service restart only
when its protected session reference and compatible provider version are
durably restored. An active run with irreconcilable status fails closed.

`agent.wait` normal completion is normalized from `status: ok` with
`stopReason: stop`. A provider `timeout` after restart is not terminal success;
it leaves the turn reconciliation-required or `delivery_unknown` and prevents
new dispatch until resolved.

Provider session deletion is not a lifecycle authority. Live testing showed a
deleted key could be accepted again and could retain apparent context.
RAGenius therefore rejects follow-up before provider contact whenever its own
durable session is missing, closed, expired, or version-incompatible.

### Compatibility

The existing one-shot OpenClaw provider remains unchanged. The chat-level
feature has a separate disabled-by-default flag and exact OpenClaw version
allowlist. Structured OpenClaw interaction work remains deferred.

Bundled-skill discovery uses the stable approved root
`/home/openclaw/.openclaw/tools`; version-specific Node package paths are not
configuration contracts. Existing exact-package containment, symlink, file,
depth, and byte limits remain unchanged.

## Error Model

Minimum stable errors:

```text
CHAT_SESSION_NOT_READY
CHAT_SESSION_CLOSED
CHAT_SESSION_VERSION_STALE
CHAT_RUN_ALREADY_ACTIVE
CHAT_FOLLOW_UP_REQUIRES_NEW_EXECUTION
CHAT_FOLLOW_UP_DELIVERY_UNKNOWN
CHAT_SESSION_RECONCILIATION_FAILED
CHAT_SESSION_VERSION_UNSUPPORTED
```

Errors remain scoped, bounded, redacted, and recoverable only when the suggested
action cannot duplicate a provider run.

## Acceptance

Provider feasibility authorizes implementation only after exact-version live
proof of same-session turns, continuation, cancellation, disconnect, restart,
and timeout behavior. The 2026-08-21 matrix passed that gate.

Production rollout requires all CL-01 through CL-28 to pass against the final
implementation. The production test plan includes unit, route, persistence,
app, Builder, security, and opt-in live Gateway coverage.
