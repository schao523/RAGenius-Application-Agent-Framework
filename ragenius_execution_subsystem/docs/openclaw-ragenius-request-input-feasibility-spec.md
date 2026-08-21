# OpenClaw RAGenius Request Input Feasibility Specification

Date: 2026-08-13

## Status

Technical feasibility specification. This document does not authorize plugin
installation, production enablement, or an interactive clarification capability
claim.

Initial live evidence confirms the preferred candidate's basic yield and
same-session continuation primitive on OpenClaw 2026.6.8. It does not complete
the feasibility matrix or authorize capability advertisement.

Task 10 subsequently passed the minimal typed Candidate A path but did not pass
every production gate. The dated feasibility results are authoritative for the
observed matrix status; OpenClaw clarification and selection remain disabled.
In particular, the disposable implementation did not prove exactly-once
continuation across a crash between provider acceptance and durable run-id
commit, serialize overlapping resolution dispatch, or prove cross-runtime file
locking.

## Purpose

Determine whether an administrator-managed OpenClaw native plugin can provide a
typed, correlated, non-authorizing user-input interaction for RAGenius. The
plugin must let an Agent invoke `ragenius_request_input`, pause safely, receive
exactly one RAGenius response, and resume without parsing assistant prose or
collecting secrets.

## Installed Basis

OpenClaw 2026.6.8 provides:

- `registerTool` for a native Agent tool;
- plugin-attributed Agent event emission;
- run-scoped plugin context and lifecycle cleanup;
- scoped custom Gateway methods through `registerGatewayMethod`;
- structured session, run, cancellation, and Gateway authentication surfaces.

A prior live probe found no built-in structured clarification mechanism. The
feasibility test must prove that these plugin primitives compose into a safe
request/response channel; their separate existence is not sufficient.

## Candidate Protocol

Two provider-internal continuation mechanisms must be compared. Both expose the
same provider-neutral RAGenius interaction record and security boundary.

### Candidate A: Yielded managed sub-agent (preferred)

1. The plugin starts or owns a dedicated sub-agent session with a stable
   `sessionKey` and `deliver: false`.
2. The sub-agent invokes `ragenius_request_input`. The plugin persists the
   typed request and returns control so the current model turn can call
   `sessions_yield`.
3. `sessions_yield` ends that model turn. It does not suspend the provider
   invocation in place.
4. After RAGenius resolves the request, the plugin calls
   `api.runtime.subagent.run` with the same `sessionKey`, a new provider run id,
   and a structured continuation message containing the resolved interaction.
5. The resumed turn either completes, fails, or creates another typed request
   and yields again.

This candidate provides `same_session_new_turn` continuation, not `same_turn`
continuation. Session history retention, run ownership, cancellation, restart
behavior, and exactly-once result delivery must be observed rather than
assumed. RAGenius remains the only user-facing delivery surface.

### Candidate B: Pending in-tool waiter (comparison only)

The tool call remains pending while a plugin-owned promise waits for a Gateway
resolution. This candidate can preserve same-tool-call semantics, but it is
acceptable only if Gateway responsiveness, bounded resource use, cancellation,
expiry, and restart cleanup all pass. It must not be preferred merely because
its semantics resemble Codex app-server.

Tool name:

```text
ragenius_request_input
```

Tool arguments:

```ts
type RequestInputArgs = {
  question: string;             // 1..2000 characters
  options?: Array<{
    id: string;                 // stable opaque id, 1..64 characters
    label: string;              // 1..200 characters
    description?: string;       // at most 500 characters
  }>;                           // at most 20 unique options
  allows_free_text: boolean;
};
```

The plugin-generated request carries:

```ts
type OpenClawInputRequest = {
  request_id: string;
  plugin_protocol_version: "1";
  agent_id: string;
  session_key: string;
  provider_run_id: string;
  tool_call_id: string;
  question: string;
  options: RequestInputArgs["options"];
  allows_free_text: boolean;
  secret_input: false;
  created_at_ms: number;
  expires_at_ms: number;
  binding_nonce_hash: string;
};
```

OpenClaw 2026.6.8 loads Gateway methods and Agent tools in separate runtime
plugin instances. The tested cross-runtime binding therefore creates a bounded
pool of random one-use nonces during the authenticated `start` call, persists
only their hashes with the trusted session binding, and lets each tool request
consume one hash. The execution adapter keeps the raw pool in memory and selects
the nonce whose hash matches the request. Restart loses the raw pool and fails
pending requests closed. Raw nonces are never written to plugin state or exposed
to the model.

For Candidate A, `provider_run_id` identifies the turn that created the
request. Resolution also records a distinct `continuation_run_id`; the two ids
must never be collapsed. The stable `session_key` is the continuity anchor.
Resolution uses a durable `continuation_pending` phase before calling the
provider and stores the returned run id before reporting `applied`. A retry
before provider acceptance is resumable, and replay after durable completion
returns the original run id. The crash window after provider acceptance but
before that run id is stored remains a failed production gate rather than an
exactly-once claim. The disposable fixture also does not lease or serialize the
`continuation_pending` transition before provider dispatch, so overlapping
identical resolutions can start duplicate provider runs. A production design
must close both windows before advertising the capability.

The proposed Gateway methods are plugin-owned names, not core approval
namespaces:

```text
ragenius.interaction.get
ragenius.interaction.resolve
```

`resolve` accepts the full request identity, one opaque idempotency key, and
either selected option ids or bounded free text. It never accepts approval,
credential, filesystem, network, or policy decisions.

## Security Boundary

- The plugin is installed only from an administrator-configured local directory
  after source review and fingerprint approval.
- The plugin is disabled by default and capability discovery is read-only.
- Only the execution subsystem connects to the plugin Gateway methods.
- Browser and app clients never receive Gateway credentials or provider handles.
- The plugin rejects passwords, OTPs, cookies, access tokens, recovery codes,
  private keys, and fields marked secret.
- A clarification response cannot authorize a command or mutate an OpenClaw
  allowlist. Provider execution approvals remain on the separate
  `exec.approval.*` protocol.
- Request resolution requires exact request, session, run, tool-call, expiry,
  and binding-nonce matches.
- Pending state is bounded by count, payload bytes, and TTL. Logs contain only
  redacted identifiers and bounded summaries.
- Plugin restart, Gateway restart, cancellation, or lost run ownership fails
  pending requests closed; it never synthesizes an answer.

## Test Environment

- Use a disposable plugin directory and disposable OpenClaw session.
- Do not install into an administrator-approved production plugin directory.
- Do not change external services, credentials, browser state, or approval
  allowlists.
- Keep the normal OpenClaw one-shot execution profile unless a test explicitly
  needs the interactive approval profile; clarification tests themselves must
  not require `exec`.
- Record OpenClaw/plugin versions, plugin fingerprint, Gateway method/event
  names, correlation identifiers, final state, elapsed time, and bounded
  redacted evidence.
- Remove the disposable plugin, config entry, sessions, and temporary state
  after testing.

## Feasibility Matrix

| ID | Test | Required observation | Pass condition |
| --- | --- | --- | --- |
| RI-01 | Plugin validation and discovery | Generated metadata, manifest, tool name, Gateway methods, fingerprint | OpenClaw validates the plugin and advertises exactly the reviewed surfaces without starting long-lived work during discovery |
| RI-02 | Tool context identity | Agent/session/run/tool-call identifiers available to the tool | The plugin derives every required correlation field from trusted runtime context, not model-supplied arguments |
| RI-03 | Typed request event | Plugin emits one bounded request event | RAGenius can identify request type and correlation without parsing text; event is visible only to the authenticated adapter |
| RI-04 | Non-blocking suspension | Tool waits while Gateway remains responsive | Health, cancellation, and unrelated sessions continue while one tool call waits |
| RI-05 | Selection response | Resolve with one valid option | The same tool call resumes once and the Agent reports the selected option |
| RI-06 | Free-text response | Resolve bounded non-secret text | The same tool call resumes once with exact normalized text |
| RI-07 | Duplicate response | Repeat idempotency key and then use a different key | Original outcome is replayed for the same key; a second logical resolution is rejected without resuming twice |
| RI-08 | Scope and binding isolation | Wrong app/session/run/tool-call/nonce and unprivileged credential attempts | Every mismatch fails closed and the pending request remains unresolved |
| RI-09 | Expiry | Leave request unanswered beyond a short TTL | Tool returns a typed expired outcome, pending state is removed, and no answer is inferred |
| RI-10 | Cancellation | Abort the exact run while waiting | Pending request is cancelled, waiter is released, and no later response can resume it |
| RI-11 | Disconnect and reconnect | Disconnect adapter while waiting, then reconnect | Adapter reconciles through `get`; no event replay is assumed and no duplicate interaction is created |
| RI-12 | Plugin or Gateway restart | Restart while waiting | Pending request fails closed with an explicit interrupted outcome unless durable recovery is independently proven |
| RI-13 | Concurrent isolation | Two sessions request input concurrently | Responses resume only their matching tool calls and event/state keys do not collide |
| RI-14 | Multiple requests in one run | Agent requests two sequential inputs | Each request has a distinct id and tool-call binding; responses are processed in order |
| RI-15 | Secret rejection | Prompt or response attempts to request/send secret-shaped data | Plugin or execution subsystem rejects it before persistence or Agent delivery and emits bounded diagnostics |
| RI-16 | Authorization separation | Clarification asks to approve a command or external write | Request is rejected or normalized as unsupported; it cannot resolve an exec approval |
| RI-17 | Output and resource bounds | Oversized question/options/response and pending-request flood | Limits are enforced without blocking the Gateway or leaking payloads into logs |
| RI-18 | One-shot compatibility | Run autonomous `openclaw agent --json` without interactive adapter | Tool is unavailable or fails preflight explicitly; one-shot execution never waits indefinitely for RAGenius input |
| RI-19 | Upgrade compatibility | Run against exact supported OpenClaw version and one unsupported fixture/version | Capability is advertised only for the tested plugin/OpenClaw protocol pair |
| RI-20 | Same-session continuation | Yield after one request, then call `api.runtime.subagent.run` with the same session key and the resolved value | Continuation has a new run id, retains prior session context, and uses the exact structured response without prose parsing |
| RI-21 | Repeated yield | Request, resolve, continue, request again, and resolve again in one sub-agent session | Two distinct interactions and continuation runs complete in order without lost context or cross-resolution |
| RI-22 | Completion delivery | Complete a yielded continuation with plugin runtime delivery disabled | RAGenius receives one correlated terminal result and OpenClaw produces no duplicate requester or external announcement |
| RI-23 | Yield eligibility | Attempt the flow without an active owned child and from an unsupported tool profile | Preflight rejects the flow explicitly; the Agent does not poll or claim to be paused |

Initial evidence status:

- RI-20: pass for stable session context and distinct continuation run ids;
- RI-21: pass for two sequential yield/continue cycles;
- RI-22: partial, because `deliver: false` suppressed configured external
  delivery and transcript output was singular, but adapter event
  deduplication was not exercised;
- RI-23: observed behavior differs from the original expectation. On OpenClaw
  2026.6.8, `sessions_yield` succeeds without active child work. The final gate
  must therefore require an owned plugin sub-agent session and supported
  runtime version rather than an active grandchild.

## Decision Gates

The managed tool is feasible only if RI-01 through RI-23 pass and the observed
protocol provides:

1. trusted run and tool-call identity;
2. one correlated request event or queryable pending record;
3. non-blocking bounded suspension or yielded same-session continuation;
4. exactly-once local resolution with safe provider idempotence;
5. cancellation, expiry, and restart cleanup;
6. session isolation and secret/authorization separation.

Prefer Candidate A if it passes RI-20 through RI-23 because it does not retain
a live tool waiter. Candidate B may be selected only if Candidate A fails a
required safety or lifecycle property and the waiter passes RI-04 through
RI-19. If neither candidate supplies trusted identity, bounded lifecycle, and
exactly-once local resolution, structured OpenClaw clarification is not
feasible. Do not replace either candidate with prose parsing.

## Required Evidence And Follow-Up

Save a dated feasibility result containing the matrix outcome, observed event
and RPC schemas, scope requirements, timeout behavior, cleanup evidence, and
all limitations. Only after approval of passing results should RAGenius update
the shared capability profile, write the plugin contract/design, and create a
separate staged implementation plan. Until then OpenClaw must continue to
advertise neither `clarification` nor `selection`.
