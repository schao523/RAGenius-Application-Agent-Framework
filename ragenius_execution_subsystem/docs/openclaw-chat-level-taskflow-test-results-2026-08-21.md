# OpenClaw Chat-Level TaskFlow Test Results

Date: 2026-08-21

## Decision

The provider-level and RAGenius-owned acceptance gates passed for the exact
OpenClaw and TaskFlow versions recorded below. Chat-level interaction remains
disabled by default and may be enabled only with the published trusted
projection, exact-version allowlist, Gateway credential, and an app service
credential that includes the `execution` scope.

The minimum functional proof passed on OpenClaw `2026.6.8 (844f405)`:

- explicit `/taskflow` invocation;
- one stable provider session with distinct sequential run ids;
- ordinary selection and clarification follow-ups;
- outline review, one revision, and Continue;
- graceful chat-level cancellation;
- adapter disconnect and Gateway restart recovery;
- correlated authoritative abort;
- bounded timeout followed by abort.

This result does not authorize typed OpenClaw clarification or selection and
does not prove same-run resumption.

## Installed Runtime

- OpenClaw CLI and Gateway: `2026.6.8 (844f405)`
- Gateway protocol: `4`
- Gateway endpoint: loopback `ws://127.0.0.1:18789`
- Authenticated scopes: `operator.admin`, `operator.approvals`
- TaskFlow source: `openclaw-bundled`
- TaskFlow provider reference: `taskflow`
- TaskFlow properties: eligible, enabled, model-visible, user-invocable, and
  command-visible
- TaskFlow `SKILL.md` SHA-256:
  `d8b6a48d329aef0a8a72d008f1e2104db55e0228c7b2785042b815c1812861d1`
- RAGenius package fingerprint under the approved broad root:
  `sha256:v1:8bf1f1a1a60b10d4a6ba53deb9a0adc2244319dc1c07ebd653e9a788a3a3c5bc`

Provider run ids, provider session ids, and the canonical session key were
recorded only as SHA-256 hashes in the disposable probe output. No credential,
raw provider handle, or reasoning trace was retained.

## Case Results

| ID | Result | Observation |
| --- | --- | --- |
| CL-01 | Pass | Gateway health, version, protocol, authentication, and required scopes passed without configuration mutation. |
| CL-02 | Pass after configuration correction | Initial discovery failed closed because the configured root targeted `.../tools/node/...`. After changing it to `/home/openclaw/.openclaw/tools`, live Builder state reported TaskFlow `available`, approved at the matching fingerprint, enabled for one app, and included in a synchronized published projection. Chat-level interaction metadata must still be republished after its schema is implemented. |
| CL-03 | Pass | The initial provider message used explicit `/taskflow`; provider inventory reported TaskFlow command-visible and the response established the requested TaskFlow marker and selection step. |
| CL-04 | Pass | The initial run returned one run id, completed with `status: ok`, and produced a bounded three-title response. |
| CL-05 | Pass | Sequential requests used distinct run ids, one canonical session, one provider session, and retained marker `TF-8d7cf3e1`. |
| CL-06 | Pass | The second run selected title 2 and retained the earlier marker. |
| CL-07 | Pass | An ordinary bounded audience question was answered in a new run and applied to the outline. No typed-wait claim was made. |
| CL-08 | Pass | Continue produced a final Markdown response from the reviewed outline. |
| CL-09 | Pass | A distinct revision run changed bullet 3 to audit evidence; the next run retained that revision. |
| CL-10 | Pass | Graceful Cancel returned a bounded cancellation summary and did not claim authoritative abort. |
| CL-11 | Pass | `chat.abort` acknowledged the exact run and `agent.wait` returned `aborted`. |
| CL-12 | Pass | Provider replay returned one run; RAGenius returned `replay` for the same durable key without a second provider call. |
| CL-13 | Pass | RAGenius accepted one follow-up and rejected the concurrent key with `CHAT_RUN_ALREADY_ACTIVE`; the provider-level observation still confirms OpenClaw alone does not serialize these runs. |
| CL-14 | Pass | Scoped refresh returned `ready_for_follow_up`, five persisted turns, and no provider references. |
| CL-15 | Pass | Closing and reconnecting the adapter while idle preserved context; the next run returned the exact marker. |
| CL-16 | Pass | After provider acknowledgement and adapter disconnect, a new connection reconciled the accepted run as `ok` through `agent.wait`; no duplicate was sent. |
| CL-17 | Pass | After a Gateway service restart while idle, the same session retained marker `RESTART-c3df5b33`. |
| CL-18 | Pass, fail closed | Restart during a harmless active run reconciled as `timeout`, never success. Disposable cleanup then removed the session. Production must retain the non-success state until authoritative reconciliation or closure. |
| CL-19 | Pass | After execution-service restart, the idle session rehydrated and retained marker `REHYDRATE-ac8bea94c2` in a new run. |
| CL-20 | Pass after fail-closed correction | After deleting the exact disposable provider session, RAGenius returned `CHAT_PROVIDER_SESSION_UNAVAILABLE`, marked the execution failed, and did not create a replacement run. |
| CL-21 | Pass | A one-second `agent.wait` returned `timeout`; correlated abort then returned `aborted`. |
| CL-22 | Pass | Wrong app/session scope returned enumeration-resistant `EXECUTION_NOT_FOUND` before provider contact. |
| CL-23 | Pass | External publication escalation returned `CHAT_FOLLOW_UP_REQUIRES_NEW_EXECUTION`. |
| CL-24 | Pass | The strict follow-up schema rejected an added artifact reference; skill and artifact bindings cannot change in continuation. |
| CL-25 | Pass after stable-error correction | End closed the idle session once; later continuation returned `CHAT_SESSION_CLOSED`. |
| CL-26 | Pass | A 3-second acceptance TTL moved the idle session to completed; later continuation returned `CHAT_SESSION_CLOSED`. |
| CL-27 | Pass after redaction correction | Public history contained five monotonic turns and 94 bounded events without provider run/session/turn/event keys. A local review found and removed raw `run_id` from public event payloads before the final live rerun. |
| CL-28 | Pass | Unsupported-version fixtures reject chat-level capability before session creation; exact live version `2026.6.8` passed preflight. |

## Critical Findings

### Trusted root must survive runtime upgrades

The approved broad-directory model is required in the active environment, not
only in documentation. The stale version-specific `node` locator caused every
bundled TaskFlow package inspection to fail even though provider inventory was
healthy. Use `/home/openclaw/.openclaw/tools` as the trusted package root and
keep package containment and fingerprint limits unchanged.

Follow-up verification confirmed TaskFlow `available` with fingerprint
`sha256:v1:8bf1f1a1a60b10d4a6ba53deb9a0adc2244319dc1c07ebd653e9a788a3a3c5bc`.
The approved fingerprint matched, its app binding was enabled, and Builder
projection revision `1787303510208` was synchronized and published without an
error.

### Concurrency is a RAGenius responsibility

OpenClaw did not enforce one active run per submitted session key. Two
near-simultaneous different idempotency keys both completed. The implementation
must use a durable compare-and-set or lease before dispatch; an in-memory check
is insufficient across execution-service processes.

### Provider session deletion is not a sufficient closure boundary

Deleting the listed session did not make a repeated submitted key fail and did
not reliably erase contextual recall. RAGenius closure, expiry, and ownership
must be authoritative. A closed, expired, missing, or version-mismatched
RAGenius session must fail before any Gateway call.

### Provider idempotency is useful but not sufficient

OpenClaw replayed the same run for the same idempotency key. RAGenius must still
persist the claimed key, provider acknowledgement state, run id, and normalized
outcome so restart recovery never relies solely on provider behavior.

## Cleanup And Restoration

- Seven disposable `taskflow_probe` sessions and transcripts were deleted.
- A final session inventory contained zero `taskflow_probe` entries.
- Gateway runtime was healthy and admin-capable after two controlled restarts.
- Effective exec policy remained `security: full`, `ask: on-miss`.
- Gateway configuration SHA-256 remained
  `6a91b7d272f748858e31aaf78e2a22440a5b5e0cd2b8f00656301f5c931d3442`
  before and after testing.
- No local output file, browser action, credential action, network publication,
  destructive operation, or external write was requested.

## Verification

- Provider probes passed CL-01, CL-03 through CL-12, CL-15 through CL-18, and
  CL-21 against the live Gateway. Provider identifiers were retained only as
  SHA-256 hashes.
- RAGenius execution `execution_e36b2639daea` passed replay, concurrency,
  selection, clarification, revision, Continue, isolation, policy, history,
  and closure cases.
- Execution `execution_6ad1f6e4fb24` passed restart rehydration; execution
  `execution_a156fc5d2dfb` passed deleted-provider-session rejection; execution
  `execution_7abf4b9d1b5c` passed graceful cancellation.
- The authoritative scoped cancellation test ended with execution status
  `cancelled` after correcting the idle-completion transition race.
- Execution subsystem: 464 tests, 457 passed, 7 skipped, 0 failed; ESLint
  passed; Prisma validation and generation passed.
- Builder: 119 passed with 2 subtests and no failures.
- App backend: 127 passed, 1 skipped, 0 failed.
- Frontend: 155 passed across 16 files; the Vite production build passed.

## Operational Requirement

TaskFlow was explicitly re-reviewed with `interaction_channel: chat_level` and
published as Builder revision `1787309327435`. The synchronized execution
projection matched fingerprint
`sha256:v1:8bf1f1a1a60b10d4a6ba53deb9a0adc2244319dc1c07ebd653e9a788a3a3c5bc`.

The existing app service credential initially lacked the `execution` scope and
correctly received `SERVICE_SCOPE_REQUIRED`. Production activation must add
`execution` to that credential's scopes; the live matrix used a process-only
override and did not rewrite secret-bearing `.env` files.
