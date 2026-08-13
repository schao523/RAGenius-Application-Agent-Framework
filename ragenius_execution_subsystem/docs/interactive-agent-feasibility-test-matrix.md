# Interactive Agent Transport Feasibility Test Matrix

Date: 2026-08-13

## Purpose

Verify the behavior that RAGenius must rely on before defining a general
interactive Agent execution contract. Tests target the installed Codex
app-server and OpenClaw Gateway versions. This document is a test specification,
not a provider contract.

## Safety Boundary

- Use a disposable directory under `ragenius_execution_subsystem/.test_tmp`.
- Do not modify provider configuration, approval allowlists, credentials, or
  external services.
- Do not submit destructive, privileged, browser-control, or external-write
  requests.
- Treat credentials, provider session handles, and raw authentication material
  as secrets and redact them from recorded evidence.
- A blocked or unsupported result is valid evidence and must not be worked
  around by weakening provider security.

## Evidence To Record

For every test record the provider and CLI version, transport, request method,
event or response types, correlation identifiers, final state, elapsed time,
and observed limitation. Preserve only bounded and redacted excerpts.

## Codex App-Server Tests

| ID | Test | Required observation | Pass condition |
| --- | --- | --- | --- |
| CX-01 | Generate protocol schemas | Available requests, notifications, approval and user-input types | Schemas generate and expose typed session/turn/event methods |
| CX-02 | Initialize connection | Protocol handshake and version/capability response | Client initializes without interactive terminal parsing |
| CX-03 | Start harmless turn | Thread/session id, turn id, sequenced events, final response | A deterministic read-only prompt completes through structured messages |
| CX-04 | Session continuation | A second turn references the first turn's session context | Continuation uses a stable provider session/thread handle |
| CX-05 | Structured approval | Approval request id, choices, response method, resumed result | A harmless workspace write pauses and resumes through typed approval messages |
| CX-06 | Structured user input | Input request id, response schema, resumed result | The provider requests and accepts non-authorizing input without prose parsing |
| CX-07 | Cancellation | Cancel method, acknowledgement, terminal event | A running turn is cancelled idempotently and stops producing work events |
| CX-08 | Reconnect/recovery | Session lookup, running-state reconciliation, replay/cursor behavior | A new client can reconcile state without assuming unsupported event replay |
| CX-09 | Authentication handoff | Typed auth-required signal or documented absence | Authentication behavior can be represented without collecting secrets |

## OpenClaw Gateway Tests

| ID | Test | Required observation | Pass condition |
| --- | --- | --- | --- |
| OC-01 | Probe Gateway | Version, reachability, authentication mode, capability level | Local authenticated Gateway is reachable over WebSocket |
| OC-02 | Inspect protocol surface | Request, response, event envelopes and method names | Typed envelopes and correlation ids are available without TUI parsing |
| OC-03 | Start harmless agent run | Session key/id, run id, Agent events, final response | Read-only request completes through Gateway RPC/events |
| OC-04 | Session continuation | Second request reuses a stable session and prior context | Continuation works independently of the RAGenius execution id |
| OC-05 | Exec approval round trip | `exec.approval.requested`, decision method and completion behavior | A harmless command can pause and resume through a single-use decision |
| OC-06 | Structured user input | Typed clarification/selection event or documented absence | RAGenius can distinguish input from approval without parsing prose |
| OC-07 | Cancellation | Abort/cancel method and terminal behavior | Cancellation is correlated to one run and is idempotent |
| OC-08 | Reconnect/recovery | Session/run lookup and event replay or reconciliation behavior | A new client can recover authoritative state after disconnect |
| OC-09 | Authentication handoff | Typed auth-required signal or documented absence | Authentication can be represented as user action without secret collection |

## Cross-Provider Acceptance Questions

1. Which provider identifiers must RAGenius persist separately from
   `execution_id`?
2. Does continuation resume the same turn, or start a new turn in the same
   provider session?
3. Which interaction types are authoritative typed events, and which are only
   model text?
4. Can interactions be answered exactly once and correlated to a provider
   request?
5. What cancellation and reconnect guarantees are actually observable?
6. Can the existing one-shot CLI remain a safe autonomous fallback?

## Decision Rule

A provider qualifies for the general interactive channel only for capabilities
verified through structured protocol behavior. Unsupported capabilities remain
explicit provider capability flags; RAGenius must not emulate them by parsing
terminal prompts or treating conversational text as authorization.
