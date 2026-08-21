# OpenClaw Chat-Level TaskFlow Test Results

Date: 2026-08-21

## Decision

The provider-level chat workflow is feasible, but the production gate is not
yet complete. OpenClaw chat-level interaction must remain disabled until the
RAGenius-owned governance, concurrency, persistence, isolation, policy, and
lifecycle cases are implemented and pass.

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
| CL-02 | Fail closed | The live Builder catalog contains TaskFlow but marks it `invalid` with an empty fingerprint. The configured root still targets `.../tools/node/...`, while the installed runtime uses `.../tools/node-v22.22.0/...`. The real discovery adapter returned `available` and a valid fingerprint when tested with the approved broad root `/home/openclaw/.openclaw/tools`. Approval, binding, and publication were therefore not tested. |
| CL-03 | Pass | The initial provider message used explicit `/taskflow`; provider inventory reported TaskFlow command-visible and the response established the requested TaskFlow marker and selection step. |
| CL-04 | Pass | The initial run returned one run id, completed with `status: ok`, and produced a bounded three-title response. |
| CL-05 | Pass | Sequential requests used distinct run ids, one canonical session, one provider session, and retained marker `TF-8d7cf3e1`. |
| CL-06 | Pass | The second run selected title 2 and retained the earlier marker. |
| CL-07 | Pass | An ordinary bounded audience question was answered in a new run and applied to the outline. No typed-wait claim was made. |
| CL-08 | Pass | Continue produced a final Markdown response from the reviewed outline. |
| CL-09 | Pass | A distinct revision run changed bullet 3 to audit evidence; the next run retained that revision. |
| CL-10 | Pass | Graceful Cancel returned a bounded cancellation summary and did not claim authoritative abort. |
| CL-11 | Pass | `chat.abort` acknowledged the exact run and `agent.wait` returned `aborted`. |
| CL-12 | Provider pass; RAGenius pending | Repeating one provider idempotency key returned the same run id and result. Durable RAGenius normalized-outcome replay is not implemented. |
| CL-13 | RAGenius gate pending | OpenClaw accepted both concurrent different-key submissions and created two runs. RAGenius must atomically claim one active run before provider contact. |
| CL-14 | Implementation-dependent | The `ready_for_follow_up` API and app rehydration state do not exist yet. |
| CL-15 | Pass | Closing and reconnecting the adapter while idle preserved context; the next run returned the exact marker. |
| CL-16 | Pass | After provider acknowledgement and adapter disconnect, a new connection reconciled the accepted run as `ok` through `agent.wait`; no duplicate was sent. |
| CL-17 | Pass | After a Gateway service restart while idle, the same session retained marker `RESTART-c3df5b33`. |
| CL-18 | Pass, fail closed | Restart during a harmless active run reconciled as `timeout`, never success. Disposable cleanup then removed the session. Production must retain the non-success state until authoritative reconciliation or closure. |
| CL-19 | Implementation-dependent | Durable execution-service restart rehydration for chat-level sessions is not implemented. |
| CL-20 | RAGenius gate pending | After `sessions.delete`, OpenClaw accepted a replacement run for the same submitted key and unexpectedly still returned the old marker. RAGenius must reject a missing/deleted durable session before provider contact and must not infer provider deletion from context loss. |
| CL-21 | Pass | A one-second `agent.wait` returned `timeout`; correlated abort then returned `aborted`. |
| CL-22 | Implementation-dependent | Chat follow-up scope APIs do not yet exist. |
| CL-23 | Implementation-dependent | Follow-up policy-delta enforcement does not yet exist. |
| CL-24 | Implementation-dependent | Artifact and selected-skill stability checks do not yet exist. |
| CL-25 | Implementation-dependent | Durable chat-session closure does not yet exist. |
| CL-26 | Implementation-dependent | Durable idle expiry does not yet exist. |
| CL-27 | Implementation-dependent | Multi-run normalized history and public redaction APIs do not yet exist. |
| CL-28 | Pass for existing preflight | The existing adapter test rejects unsupported Gateway versions before start. Chat-level capability remains absent and therefore is not advertised. |

## Critical Findings

### Trusted root must survive runtime upgrades

The approved broad-directory model is required in the active environment, not
only in documentation. The stale version-specific `node` locator caused every
bundled TaskFlow package inspection to fail even though provider inventory was
healthy. Use `/home/openclaw/.openclaw/tools` as the trusted package root and
keep package containment and fingerprint limits unchanged.

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

- Both disposable TypeScript probes compiled with `tsc --noEmit`.
- Targeted OpenClaw discovery and Gateway adapter tests passed: 13 tests, zero
  failures.
- The unsupported-version preflight fixture passed.
- A broader sandboxed test invocation produced two unrelated `spawn EPERM`
  failures in process-supervisor tests; the targeted matrix tests passed and no
  production source was changed by this feasibility work.

## Next Gate

Do not write or execute the production implementation plan as though the matrix
fully passed. The plan must explicitly close CL-02, CL-12 through CL-14, CL-19,
CL-20, and CL-22 through CL-27, while preserving the observed provider behavior
for CL-03 through CL-11 and CL-15 through CL-18.

