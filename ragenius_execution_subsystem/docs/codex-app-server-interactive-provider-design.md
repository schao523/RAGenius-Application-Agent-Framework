# Codex App-Server Interactive Provider Design

Date: 2026-08-13

## Purpose

Add a capability-gated Codex interactive adapter without replacing the existing
autonomous `codex exec --json` provider.

## Observed Basis

Codex CLI `0.146.0` app-server passed live tests for JSON-RPC initialization,
structured events, two-turn thread continuation, correlated command approval,
a RAGenius dynamic interaction tool, and `turn/interrupt`. The protocol is
experimental and must be version-checked.

## Components

```text
InteractiveAgentSessionManager
  -> CodexAppServerAdapter
      -> CodexAppServerProcess (one per active execution in MVP)
      -> newline JSON-RPC codec
      -> provider event normalizer
      -> pending provider request registry
```

The per-execution process preserves failure isolation and the existing
execution-owned process-supervision rule. It remains alive while a same-turn
interaction is pending, subject to a bounded interaction TTL. A shared daemon
is explicitly deferred.

## Adapter Interface

```ts
interface InteractiveAgentAdapter {
  readonly backend: AgentBackend;
  preflight(input: InteractivePreflightInput): Promise<InteractivePreflightResult>;
  start(input: InteractiveStartInput): Promise<ProviderSessionHandle>;
  respond(handle: ProviderSessionHandle, interaction: ClaimedInteraction): Promise<void>;
  cancel(handle: ProviderSessionHandle): Promise<ProviderCancellationResult>;
  reconcile(handle: ProviderSessionHandle): Promise<ProviderReconciliationResult>;
}
```

`ProviderSessionHandle` is execution-subsystem internal and contains thread id,
active turn id, pending JSON-RPC request mapping, protocol version, and process
supervisor reference. It contains no user-facing path or credential.

## Start Flow

1. Generate or load schemas known to the supported Codex version range.
2. Spawn `codex app-server --stdio` without `shell: true`.
3. Send `initialize`, then `initialized`.
4. Send `thread/start` with scoped cwd, sandbox, approval policy, reviewer
   `user`, and `ephemeral: true` for the initial release.
5. Resolve and stage selected artifacts into the execution-owned workspace.
6. Supply `ragenius_request_input` as a dynamic tool when the execution allows
   clarification or selection, and prepend trusted protocol guidance that
   requires the tool whenever such user input is needed.
7. Build the turn input from the trusted protocol guidance, staged artifact
   manifest, expected-output instructions, and delimited user query.
8. Send `turn/start` and persist thread/turn identifiers before processing
   subsequent events.

## Explicit Request Routing

`ExecuteAgentRequest.interaction_requirements` is the provider-neutral signal
for interactive transport. Codex consumes only structured style. Composer's
Interactive Agent mode allows both
clarification and selection without requiring either. Advanced callers may
also supply `required_types`. The execution engine combines both arrays with
governed skill policy before adapter preflight:

- capability requirements are the union of allowed and required request types
  and all interaction
  types required by the selected skill transport;
- fulfillment requirements are only explicit required types plus the selected
  skill's supported types only when its interaction requirement is `required`;
- any non-empty capability requirement routes Codex through app-server;
- completion fails with `REQUIRED_INTERACTION_NOT_OBSERVED` when a fulfillment
  requirement was never emitted as a typed `ragenius_request_input` call.

The one-shot `codex exec` provider is not eligible for these requests. The
execution subsystem applies only conservative high-confidence inference for
explicit imperatives such as "ask me to select" and "ask me for
clarification". It does not attempt general semantic classification. Resolved
requirements are persisted in execution metadata and required occurrences are
enforced at completion.

## Interaction Mapping

| Codex message | RAGenius interaction |
| --- | --- |
| `item/commandExecution/requestApproval` | `approval` |
| `item/fileChange/requestApproval` | `approval` |
| `item/permissions/requestApproval` | `approval`, but only permissions already bounded by confirmed RAGenius policy may be offered |
| `item/tool/call` for `ragenius_request_input` | `clarification` or `selection` based on validated arguments |
| account or MCP login requirement | `authentication_handoff` |

Legacy approval request forms may be normalized only when covered by generated
schemas and adapter tests.

The adapter returns only `accept`, `decline`, or `cancel` equivalents. Codex
session approval and policy-amendment responses are not exposed in the MVP.

## Dynamic Interaction Tool

```json
{
  "type": "function",
  "name": "ragenius_request_input",
  "description": "Ask the user one bounded non-secret question.",
  "inputSchema": {
    "type": "object",
    "required": ["question"],
    "properties": {
      "question": { "type": "string", "maxLength": 2000 },
      "options": {
        "type": "array",
        "maxItems": 20,
        "items": { "type": "string", "maxLength": 200 }
      },
      "allows_free_text": { "type": "boolean" }
    }
  }
}
```

The tool description states that it cannot request secrets or approvals. The
execution subsystem validates arguments again before creating an interaction.

## Event Normalization

Thread, turn, item, message delta, tool, warning, error, and completion messages
become provider-neutral events. JSON-RPC request ids are stored only as
protected correlation references. Raw reasoning is discarded. Message deltas
are coalesced, bounded, and accumulated into the normalized final assistant
response. When an expected output requests artifact persistence, the session
manager persists that final response through the shared Agent output artifact
persister and includes the resulting artifact reference in the terminal
execution result. Explicit provider-created file outputs retain workspace
verification requirements and are not satisfied by response capture.

## Cancellation

Use `turn/interrupt` with the exact thread and turn. Wait for a terminal turn
event, then terminate the app-server process. If the interrupt is not confirmed
within the grace period, terminate the full process tree and return failed
cleanup diagnostics rather than `cancelled`.

## Recovery

During the MVP, a process loss while a provider request is pending fails the
execution with `AGENT_EXECUTION_INTERRUPTED`; JSON-RPC request continuation
cannot be reconstructed safely. Completed-turn continuation may use
`thread/resume` in a later phase after a fresh-process recovery smoke test.

No event replay is assumed. Reconciliation reads thread/turn state and appends a
synthetic normalized recovery event.

## Compatibility And Fallback

- Feature flag: `CODEX_APP_SERVER_INTERACTIVE_ENABLED=false` by default.
- Preflight checks CLI version, schema compatibility, initialization, and
  required methods.
- Unsupported protocol versions disable only interactive Codex execution.
- Autonomous requests continue through the existing `CodexCliProvider`.
- An execution requiring interaction never silently falls back to one-shot
  Codex.

## Tests

- JSON-RPC framing, ids, out-of-order responses, malformed messages, and output
  bounds.
- Multiple approvals in one turn and single-use responses.
- Dynamic interaction tool selection and free-text responses.
- Interactive Agent mode without an Agent Skill, with clarification and
  selection both available.
- Required-interaction completion failure when Codex never calls the dynamic
  tool.
- Explicit selection wording raises a required selection without requiring the
  user to name `ragenius_request_input`.
- Selected artifacts are staged and referenced by safe workspace-relative
  paths.
- Final response is returned conversationally with persistence off and becomes
  a reusable `agent_output` artifact with persistence on.
- Cancellation before and during tool execution.
- Interaction expiry and process-tree cleanup.
- Protocol version mismatch and autonomous fallback eligibility.
- Opt-in live smoke matching the 2026-08-13 feasibility cases.
