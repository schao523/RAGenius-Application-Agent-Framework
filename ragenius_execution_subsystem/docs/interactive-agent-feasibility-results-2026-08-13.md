# Interactive Agent Transport Feasibility Results

Date: 2026-08-13
Platform: Windows host with `OpenClawGateway` WSL distribution

## Scope

These results execute the safe subset of
`interactive-agent-feasibility-test-matrix.md`. They establish observed
transport behavior for contract and design work. They do not certify either
provider for unrestricted interactive execution. The OpenClaw approval-policy
retest was an administrator-authorized exception to the original test-matrix
rule prohibiting provider configuration changes.

## Installed Versions

- Codex CLI: `0.146.0`
- OpenClaw CLI and Gateway: `2026.6.8 (844f405)`
- OpenClaw Gateway: loopback `ws://127.0.0.1:18789`, connectivity probe `ok`,
  admin-capable

## Codex App-Server Results

| ID | Result | Observation |
| --- | --- | --- |
| CX-01 | Pass | Experimental JSON schemas generated successfully. Typed methods include `initialize`, `thread/start`, `thread/resume`, `turn/start`, `turn/interrupt`, approvals, permissions, dynamic tool calls, and `item/tool/requestUserInput`. |
| CX-02 | Pass | `initialize` completed over newline-delimited JSON-RPC on stdio and returned platform and user-agent metadata. No terminal prompt parsing was required. |
| CX-03 | Pass | A read-only turn produced correlated thread and turn identifiers plus `turn/started`, item events, deltas, and `turn/completed`. |
| CX-04 | Pass | Two turns reused one thread. The first stored `RAGenius-731`; the second returned `RAGenius-731`, proving session-context continuation. |
| CX-05 | Pass | A harmless `Set-Content` request emitted `item/commandExecution/requestApproval` with request id, thread id, turn id, item id, command, cwd, allowed decisions, and proposed policy amendment. Returning `{decision: "accept"}` resumed the same turn and created the disposable file. The same turn later emitted a second approval, proving interactions are one-to-many per execution. |
| CX-06 | Pass with adapter tool | Merely asking the model to request input produced prose and completed the turn; the built-in request was not emitted. Supplying a `ragenius_request_input` dynamic tool emitted a typed `item/tool/call`. Returning `Beta` resumed the same turn, which completed with `SELECTED: Beta`. |
| CX-07 | Pass | `turn/interrupt` acknowledged a correlated thread/turn request. The terminal turn event reported `status: interrupted` after approximately one second. |
| CX-08 | Partial | `thread/resume` and thread lookup are present in generated schemas, including rejoining a running thread. A fresh-process reconnect and pending-interaction recovery test was not executed. No event replay guarantee was established. |
| CX-09 | Partial | Typed account-login methods, authentication notifications, and token-refresh server requests exist. No login was initiated because the test boundary prohibits collecting or changing credentials. |

### Codex Conclusions

- `codex app-server` is technically feasible as the primary interactive Codex
  transport.
- Codex thread id, turn id, JSON-RPC request id, and item/call id are distinct
  identifiers and must not be collapsed into the RAGenius execution id.
- Command and file approvals can pause and resume the same turn.
- General non-authorizing input should use a RAGenius-defined dynamic tool. The
  app-server's built-in `requestUserInput` must remain capability-gated until a
  supported collaboration mode is independently verified.
- Codex app-server is marked experimental, so schema generation and protocol
  compatibility checks are required at startup and during upgrades.

## OpenClaw Gateway Results

| ID | Result | Observation |
| --- | --- | --- |
| OC-01 | Pass | Gateway health and status calls succeeded over the authenticated local Gateway. Runtime status was active and the event loop was healthy. |
| OC-02 | Pass for protocol surface | Gateway RPC returned typed JSON. Installed runtime code exposes request/response correlation, sequenced events, gap detection, `exec.approval.requested`, `exec.approval.resolved`, and `exec.approval.resolve`. A live event subscriber later confirmed that approval events are structured but carry no Gateway `seq`; their approval ids are the deduplication keys. |
| OC-03 | Pass | Gateway `agent` accepted a read-only request and returned a run id, canonical session key, provider session id, structured status, and final payload. |
| OC-04 | Pass | Two requests used one session key and produced different run ids but the same provider session id. The second returned the remembered token `Claw-482`. |
| OC-05 | Pass with constraints | The effective policy was set to `security: allowlist`, `ask: on-miss`, and `askFallback: deny`; `security: full` produced no miss and therefore no approval request. A harmless Agent `printf` emitted correlated `exec.approval.requested` events. `allow-once` resumed and executed exactly once; `deny` resumed without execution. A one-second direct request expired with `decision: null`. Duplicate resolve calls returned `{ok:true}` idempotently but emitted only one resolved event. An external subscriber required both `operator.admin` and `operator.approvals`; `operator.approvals` alone is sufficient only for OpenClaw's process-internal approval runtime. |
| OC-06 | Pass: documented absence | A live read-only probe requested a native structured Alpha/Beta clarification. Run `47cffdad-1f91-4287-b1b0-692f4107cf08` completed normally in 3.66 seconds with an ordinary assistant payload beginning `UNSUPPORTED:`. The run's tool inventory contained no clarification, selection, prompt, or user-input tool; no correlated input event or paused state was emitted. OpenClaw `/btw` remains a user-initiated side message, not an Agent input request. |
| OC-07 | Pass | An accepted sleep-only run returned a run id. `chat.abort` returned `aborted: true` with that exact run id. `agent.wait` then reported `error: aborted` and `stopReason: aborted`. |
| OC-08 | Partial pass | `sessions.list` returned the canonical key, provider session id, run state, and `hasActiveRun`. `agent.wait` supports post-disconnect reconciliation. Installed client code detects event sequence gaps and reconnects, but event replay was not established. |
| OC-09 | Partial | Gateway exposes structured authentication, token, scope, pairing, and protocol-mismatch error codes. External tool authentication handoff was not exercised. |
| OC-10 | Pass for yielded continuation primitive | A disposable plugin-owned sub-agent session called `sessions_yield` twice without spawning child work. Each yield ended its provider run with `waitForRun` status `ok` and persisted a structured `{status: "yielded"}` tool result. Calling `api.runtime.subagent.run` again with the same session key created a new run id each time, retained both test markers, and appended the continuation as a new user turn. `deliver: false` produced no configured external delivery. |

### OpenClaw Conclusions

- OpenClaw Gateway is technically feasible as the primary interactive OpenClaw
  transport for sessions, run lifecycle, cancellation, events, and execution
  approvals.
- The persisted RAGenius provider handle must contain the canonical session key,
  provider session id when available, and current run id.
- Live approval acceptance requires `security: allowlist`, administrator-enabled
  `ask: on-miss`, and `askFallback: deny`. The installed visibility rules require
  an external adapter credential to have both `operator.admin` and
  `operator.approvals`; the narrower approval-only scope works only for
  OpenClaw's process-internal approval runtime. RAGenius must not change these
  settings automatically.
- Provider duplicate resolutions are idempotently accepted rather than
  rejected. RAGenius must enforce single-use interaction state locally and
  deduplicate approval events by approval id because those events have no
  Gateway sequence number.
- General clarification needs a separately designed OpenClaw managed tool or
  plugin. Until then, OpenClaw advertises no structured clarification
  capability.
- A yielded plugin-owned sub-agent is now the preferred clarification
  feasibility candidate. The observed semantic is `same_session_new_turn`,
  not same-turn tool resumption: one stable session key anchored four distinct
  provider run ids across two yield/continue cycles.
- `sessions_yield` worked without active child work in the installed 2026.6.8
  runtime, although its documentation describes sub-agent completion as the
  primary use. RAGenius must version-gate and regression-test this behavior.
- This probe did not establish typed request persistence, adapter resolution,
  cancellation while yielded, restart recovery, or idempotent external
  completion delivery. OpenClaw must still advertise no structured
  clarification capability until the remaining feasibility matrix passes.

## Cross-Provider Findings

1. A RAGenius execution may contain multiple provider runs and multiple
   interactions.
2. Provider session identity, provider run identity, and RAGenius execution
   identity are different resources.
3. Codex can resume a paused same-turn dynamic tool call. OpenClaw continuation
   is currently verified as a new run in the same session.
4. Cancellation is correlated and feasible for both providers.
5. Reconnect must use status reconciliation. Neither provider should be assumed
   to replay every missed event.
6. Authentication must be modeled as user action and capability recheck, not a
   secret response submitted through RAGenius.
7. Existing one-shot CLI providers remain useful autonomous fallbacks but do not
   qualify as general interactive transports.

## Contract Constraints Derived From Testing

- Add one provider-neutral `waiting_for_interaction` execution status; keep
  pre-execution `pending_confirmation` separate.
- Persist interactions as append-only, individually correlated, single-use
  records.
- Allow only capabilities declared by the active adapter and verified during
  preflight.
- Never parse prose as an approval or assume a question means the provider turn
  is resumable.
- Treat `allow-always` and provider policy mutation as out of scope for the
  initial implementation.
- Keep provider credentials and protected handles out of app-facing payloads.
