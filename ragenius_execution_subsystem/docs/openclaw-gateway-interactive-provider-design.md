# OpenClaw Gateway Interactive Provider Design

Date: 2026-08-13

## Purpose

Add a capability-gated OpenClaw Gateway adapter for interactive lifecycle,
execution approvals, cancellation, and recovery while preserving the existing
one-shot WSL CLI provider.

## Observed Basis

OpenClaw `2026.6.8` Gateway passed live tests for health, Agent submission,
stable session continuation, session lookup, `chat.abort`, and `agent.wait`.
Installed runtime code exposes sequenced events and execution-approval request,
resolution, and decision methods. The current local effective policy has
`ask: off`, so a live approval round trip remains an administrator-gated
acceptance test.

## Components

```text
InteractiveAgentSessionManager
  -> OpenClawGatewayAdapter
      -> authenticated Gateway WebSocket client
      -> RPC request registry
      -> event sequence/gap detector
      -> session/run reconciler
```

The execution subsystem owns Gateway connectivity. The app and browser never
receive Gateway URLs, tokens, device identities, or provider session keys.

## Connectivity

The initial implementation uses one adapter-managed authenticated connection
and routes events by canonical session key and run id. Reconnect creates a new
connection, reauthenticates, and reconciles every active execution.

Required scopes are least privilege:

- normal Agent runs: provider-documented read/write scopes needed for `agent`,
  `agent.wait`, sessions, and cancellation;
- approval mediation: `operator.approvals` in addition to normal execution
  scopes.

The adapter must reject a configuration that exposes a non-loopback insecure
Gateway. It must not modify Gateway binding, token, device pairing, or approval
policy.

## Start And Continue Flow

1. Probe Gateway health, version, authentication, scopes, and configured
   execution approval policy.
2. Allocate a provider session key independent of `execution_id`, scoped to
   `{app_id, session_id, agent_session_id}`.
3. Submit `agent` with a unique idempotency key and persist the canonical
   session key plus returned run id.
4. Normalize run and tool events until terminal or interaction requested.
5. A post-interaction continuation that cannot resume the same provider run
   starts a new run in the same session and records
   `continuation_mode = same_session_new_turn`.

The current execution-id-derived session key remains valid only for the
one-shot fallback and must not be reused by the interactive adapter.

## Approval Mapping

`exec.approval.requested` becomes an `approval` interaction containing a
bounded command summary, cwd label, expiry, and only decisions supported by
both RAGenius policy and the provider request.

MVP decisions map as follows:

| RAGenius | OpenClaw |
| --- | --- |
| `allow_once` | `allow-once` |
| `deny` | `deny` |
| `cancel_execution` | `deny`, then correlated `chat.abort` |

`allow-always` is never projected. A resolved or expired provider approval is
reconciled as a stale interaction and cannot be retried with another decision.

Live approval capability is advertised only when preflight confirms an
administrator-enabled ask policy and `operator.approvals` scope.

## Clarification Limitation

No typed Agent-generated clarification event was observed. `/btw` is
user-initiated and does not satisfy the interaction contract. Therefore the
initial adapter capability excludes `clarification` and `selection`.

A later milestone may install an administrator-managed RAGenius OpenClaw tool
or plugin that emits a correlated Gateway event and waits for a response. That
tool requires its own feasibility test and reviewed fingerprint before the
adapter advertises those capabilities.

## Events And Gaps

Gateway events are normalized and deduplicated by event sequence and provider
identifier. The adapter persists the latest sequence. A sequence gap forces
reconnect and reconciliation; it does not synthesize missing tool or approval
events.

`sessions.list`, the canonical session record, and `agent.wait` are the
authoritative recovery sources. Event replay remains `none` until an explicit
provider guarantee is tested.

## Cancellation

Send `chat.abort` with exact canonical session key and run id. Cancellation is
successful only when the response confirms that run id or reconciliation shows
the run terminal as aborted. `agent.wait` supplies the final stop reason.

## WSL Workspace Boundary

The Gateway adapter reuses the corrected per-run WSL staging and inspection
rules. Interactive session work must not replace the concrete run workspace
root or weaken containment. Every provider run receives its own staged input
and expected-output mapping even when several runs share one provider session.

## Compatibility And Fallback

- Feature flag: `OPENCLAW_GATEWAY_INTERACTIVE_ENABLED=false` by default.
- Gateway version, health, authentication, scopes, and methods are checked at
  startup and before first use.
- Existing `OpenClawCliProvider` remains the autonomous fallback.
- Requests requiring unsupported interaction types fail preflight rather than
  falling back to prompt conventions.

## Tests

- RPC correlation, idempotency, event sequencing, gap detection, and reconnect.
- Stable session with multiple runs and execution-independent key generation.
- Approval allow-once, deny, expiry, duplicate resolution, and wrong-run scope.
- Correlated cancellation and `agent.wait` reconciliation.
- WSL staging containment across multiple runs in one session.
- Missing scope, ask-off policy, token mismatch, Gateway unavailable, and
  protocol mismatch.
- Opt-in live smoke for continuation and cancellation; administrator-gated live
  smoke for approval.
