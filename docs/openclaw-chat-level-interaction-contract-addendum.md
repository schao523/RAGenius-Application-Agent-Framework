# OpenClaw Chat-Level Interaction Contract Addendum

Date: 2026-08-21

## Status

Approved for implementation planning on 2026-08-21. This document does not
authorize production rollout until the production acceptance gate passes.

This addendum extends `docs/interactive-agent-execution-contract.md` for an
OpenClaw capability that preserves one provider session across multiple
completed Agent runs. It does not change the typed interaction contract for
Codex or OpenClaw execution approvals.

## Purpose

OpenClaw 2026.6.8 exposes no native typed clarification or selection wait
signal through the ordinary Gateway Agent path. RAGenius may nevertheless
support conversational selection, clarification, review, revision,
continuation, and cancellation by sending each user response as a new Agent
turn in the same canonical OpenClaw session.

## Normative Distinction

Chat-level interaction is not a typed provider interaction.

```text
typed interaction
  provider run is blocked on one correlated response

chat-level follow-up
  provider run completed
  provider session remains open
  user may start another run in that session
```

RAGenius must not create `AgentInteractionRecord` entries by parsing assistant
prose. OpenClaw chat-level selection and clarification must not be advertised
in `AgentInteractionCapabilities.interaction_types`.

## Capability Contract

The provider capability snapshot gains:

```ts
type AgentChatCapabilities = {
  chat_level_interaction: boolean;
  same_session_continuation: boolean;
  structured_wait_signal: boolean;
  same_run_resumption: boolean;
  exactly_once_follow_up: boolean;
  runtime_cancellation: boolean;
};
```

The initial tested OpenClaw profile is expected to be:

```text
chat_level_interaction: true
same_session_continuation: true
structured_wait_signal: false
same_run_resumption: false
exactly_once_follow_up: false
runtime_cancellation: true
```

Capability advertisement is version-gated and comes only from live-compatible
adapter preflight. Skill metadata cannot create a provider capability.

## Lifecycle

One RAGenius execution may own one OpenClaw session and multiple provider runs:

```text
running -> ready_for_follow_up -> running
   |               |               |
   +-> failed      +-> completed   +-> cancelled
                   +-> expired
```

`run_completed` ends only the current provider run when chat-level interaction
is active. It moves the Agent session and execution to
`ready_for_follow_up`; it does not remove the protected session handle.

`completed` means the user ended the session or its idle period closed
normally. `expired` is represented as a completed session with bounded expiry
evidence unless an active provider run timed out, which remains `failed`.

The persisted Agent session contains the stable provider session reference,
the current provider run reference, a monotonic turn sequence, a session
version, and idle expiry. Provider references remain service-only.

## Follow-Up Contract

```ts
type AgentChatFollowUp = {
  expected_session_version: number;
  idempotency_key: string;
  kind: "reply" | "continue" | "revise" | "graceful_cancel";
  text?: string;
};
```

Rules:

- `reply` and `revise` require bounded non-empty text.
- `continue` submits a server-defined ordinary continuation message and may
  include bounded non-authorizing guidance.
- `graceful_cancel` submits a server-defined request to stop remaining work and
  summarize completed work. It is not authoritative cancellation.
- Only `ready_for_follow_up` accepts a follow-up.
- One session permits at most one active provider run and one claimed
  follow-up submission. RAGenius enforces this with a durable conditional
  claim or lease before provider contact; OpenClaw does not serialize distinct
  idempotency keys for the same submitted session.
- The adapter sends the turn to the exact canonical session key with a unique
  provider idempotency key and records the returned run id before reporting
  acceptance.
- Duplicate RAGenius idempotency keys replay the stored normalized result.
- Provider idempotency is supplementary evidence only. RAGenius persists its
  claimed key, provider acknowledgement state, run reference, and normalized
  outcome before relying on replay behavior after restart.
- If provider acceptance cannot be reconciled, RAGenius reports
  `delivery_unknown`; it never reports completion or automatically submits a
  replacement turn.
- Assistant prose and apparent option lists are display content only.

## Service APIs

```text
GET  /v1/executions/{execution_id}/chat-session?app_id=&session_id=
POST /v1/executions/{execution_id}/follow-ups?app_id=&session_id=
POST /v1/executions/{execution_id}/end-chat-session?app_id=&session_id=
POST /v1/executions/{execution_id}/cancel
```

The app backend proxies these endpoints only after user, app, and session
ownership checks. Browser clients never receive Gateway credentials, canonical
provider session keys, provider run ids, or raw provider handles.

## Policy Boundary

Every follow-up is another provider invocation. It must remain within the
original execution's confirmed policy and operation envelope.

For the MVP, a follow-up that raises risk, introduces an unplanned external
write, changes the selected skill, adds new artifacts, or requires broader
network/workspace access fails with `CHAT_FOLLOW_UP_REQUIRES_NEW_EXECUTION`.
The user must submit a new execution through normal policy classification and
confirmation.

`Continue` is ordinary chat input. It is not a RAGenius typed approval. If the
original confirmed request included a provider-delegated external operation,
OpenClaw owns operation binding and duplicate-side-effect prevention. RAGenius
must label that trust model and must not claim exactly-once enforcement.

## Cancellation And Closure

- `graceful_cancel` is an ordinary follow-up and may produce a final summary.
- When a completed `graceful_cancel` turn contains a bounded final summary, the
  app backend persists that summary exactly once as an assistant chat message
  linked to the execution, then closes the local chat-level Agent session.
  This presentation lifecycle does not make the request an authorization or
  imply authoritative provider cancellation.
- Authoritative cancellation uses `chat.abort` with the exact active run and
  session, followed by `agent.wait` reconciliation.
- `End session` is accepted only with no active run. It closes local
  continuation while preserving bounded history.
- Idle expiry closes a session only when no run is active.
- Wrong scope, stale session version, duplicate concurrent turn, closed
  session, and invalid provider session fail closed.
- RAGenius session state is authoritative. Provider session deletion, absence,
  recreation, or apparent context retention never reopens a locally closed,
  expired, missing, or version-incompatible session.
- A restart or disconnect that yields only provider `timeout` is not success.
  The turn remains `delivery_unknown` or reconciliation-required until an
  authoritative terminal state is established or the session is closed.

## Builder Governance

The reviewed Agent-skill interaction policy gains:

```ts
interaction_channel: "none" | "typed" | "chat_level";
```

TaskFlow may be published as `chat_level` only when its discovered package,
fingerprint, OpenClaw runtime target, and supported provider version are
administrator-approved. Existing app binding and trusted projection rules
remain mandatory.

OpenClaw bundled-skill discovery must trust an administrator-configured stable
tools parent such as `/home/openclaw/.openclaw/tools`, not a Node-version-
specific package path. Containment and package fingerprint limits still apply
to every exact discovered skill directory.

## App UX

Execution Composer exposes OpenClaw under `Interactive Agent` and submits
`interaction_requirements: { transport: "interactive", style: "chat" }`.
Preflight requires the version-gated `chat_level_interaction` capability; no
typed clarification or selection capability is advertised.

The app displays completed Agent output followed by a chat follow-up composer
with `Reply`, `Continue without reply`, `Revise`, `Stop and summarize`,
`Cancel current run`, and `Cancel interaction` as state-appropriate actions.
Long Agent output is confined to an independently scrollable response region;
the reply field and state-appropriate actions remain outside that region and
visible. After `Stop and summarize` completes, the final summary is projected
into the normal chat transcript and the follow-up composer closes. A bounded
`Finish and close` fallback may be shown if automatic finalization must be
retried.

The app must say that follow-ups start a new Agent run in the same OpenClaw
session. It must not say that OpenClaw is paused, that an option is formally
bound, or that a response is exactly-once.

## Acceptance Gates

The implementation-feasibility gate requires live proof of exact-version
Gateway preflight, explicit TaskFlow activation, same-session multi-run
continuity, ordinary selection and clarification turns, review/revision/
continue, graceful and authoritative cancellation, disconnect/restart
reconciliation, and bounded timeout behavior. The 2026-08-21 provider matrix
passed this gate and authorizes implementation.

The production-rollout gate requires all CL-01 through CL-28 to pass against
the implemented RAGenius APIs, persistence, Builder governance, app UX, and
recovery behavior. OpenClaw chat-level interaction remains disabled by default
until that gate passes for the exact approved OpenClaw and TaskFlow versions.
Typed OpenClaw clarification and selection remain unsupported. The disposable
Task 10 plugin remains experimental evidence and is not a production
dependency.
