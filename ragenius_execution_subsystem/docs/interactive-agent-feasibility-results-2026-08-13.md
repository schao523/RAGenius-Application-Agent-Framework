# Interactive Agent Transport Feasibility Results

Date: 2026-08-13
Platform: Windows host with `OpenClawGateway` WSL distribution

## Scope

These results execute the safe subset of
`interactive-agent-feasibility-test-matrix.md`. They establish observed
transport behavior for contract and design work. They do not certify either
provider for unrestricted interactive execution.

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
| OC-02 | Pass for protocol surface | Gateway RPC returned typed JSON. Installed runtime code exposes request/response correlation, sequenced events, gap detection, `exec.approval.requested`, `exec.approval.resolved`, and `exec.approval.resolve`. A custom raw event subscriber was not implemented in this test. |
| OC-03 | Pass | Gateway `agent` accepted a read-only request and returned a run id, canonical session key, provider session id, structured status, and final payload. |
| OC-04 | Pass | Two requests used one session key and produced different run ids but the same provider session id. The second returned the remembered token `Claw-482`. |
| OC-05 | Protocol verified; live test blocked | Installed approval protocol accepts `allow-once`, `allow-always`, and `deny`. The effective local execution policy is `security: full`, `ask: off`; changing it was outside the test boundary. No live approval was triggered. |
| OC-06 | Not observed | No authoritative Agent-generated clarification request was observed. OpenClaw `/btw` is a user-initiated side message, not an Agent input request. Prose questions cannot be normalized as authorization or structured interaction. |
| OC-07 | Pass | An accepted sleep-only run returned a run id. `chat.abort` returned `aborted: true` with that exact run id. `agent.wait` then reported `error: aborted` and `stopReason: aborted`. |
| OC-08 | Partial pass | `sessions.list` returned the canonical key, provider session id, run state, and `hasActiveRun`. `agent.wait` supports post-disconnect reconciliation. Installed client code detects event sequence gaps and reconnects, but event replay was not established. |
| OC-09 | Partial | Gateway exposes structured authentication, token, scope, pairing, and protocol-mismatch error codes. External tool authentication handoff was not exercised. |

### OpenClaw Conclusions

- OpenClaw Gateway is technically feasible as the primary interactive OpenClaw
  transport for sessions, run lifecycle, cancellation, events, and execution
  approvals.
- The persisted RAGenius provider handle must contain the canonical session key,
  provider session id when available, and current run id.
- Live approval acceptance requires an administrator-enabled `ask` policy and a
  Gateway credential with `operator.approvals`; RAGenius must not change those
  settings automatically.
- General clarification needs a separately designed OpenClaw managed tool or
  plugin. Until then, OpenClaw advertises no structured clarification
  capability.

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
