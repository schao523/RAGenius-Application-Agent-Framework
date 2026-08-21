# OpenClaw Chat-Level TaskFlow Test Matrix

Date: 2026-08-21

## Status

Pre-implementation live feasibility and acceptance matrix. Passing this matrix
does not authorize typed OpenClaw clarification or selection.

## Safety Profile

- Use the exact administrator-approved local OpenClaw and TaskFlow versions.
- Use one disposable RAGenius app and chat session.
- Use local text/Markdown outputs only.
- Do not use credentials, browser control, external publication, destructive
  commands, or external writes.
- Preserve bounded redacted RPC/event evidence and remove disposable sessions
  and outputs afterward.

## Reference Workflow

```text
Use the selected TaskFlow Skill.
Generate three possible report titles and ask me to select one.
After I select, create a short outline.
Show the outline and let me continue, revise, or cancel.
If I continue, create the final Markdown report in the required output path.
```

The user selects title 2, requests one bounded revision, then continues.

## Matrix

| ID | Test | Required observation | Pass condition |
| --- | --- | --- | --- |
| CL-01 | Gateway preflight | Health, authenticated scope, exact version, required methods | Read-only preflight passes without changing Gateway configuration |
| CL-02 | TaskFlow governance | Discovery, fingerprint, approval, app binding, published projection | The selected TaskFlow package and runtime target match the active trusted projection |
| CL-03 | Explicit activation | Initial prompt identifies the selected TaskFlow Skill | Provider evidence shows TaskFlow activation or fails explicitly; inference alone is insufficient |
| CL-04 | Initial run | Submit the reference workflow | Gateway returns one run id and canonical session key; output is bounded and terminal |
| CL-05 | Stable session | Submit a marker in run 1 and request it in run 2 | Run ids differ, canonical session/provider session remain stable, and context is retained |
| CL-06 | Selection follow-up | User replies with title 2 | A new run in the same session uses title 2 without a typed wait claim |
| CL-07 | Clarification follow-up | Agent asks a bounded ordinary question; user replies | New run retains the question context and applies the answer |
| CL-08 | Review and continue | Agent presents an outline; user selects Continue | New run continues from the displayed outline and produces the expected next result |
| CL-09 | Revision loop | User requests one revision, reviews it, then continues | Distinct sequential runs preserve the revision and complete in order |
| CL-10 | Graceful cancellation | From an idle session, send the graceful-cancel shortcut | Agent stops remaining work and returns a bounded summary; no claim of authoritative abort is made |
| CL-11 | Authoritative cancellation | Abort a correlated long-running harmless run | `chat.abort` identifies the exact run and `agent.wait` reports aborted/cancelled |
| CL-12 | Duplicate submission | Repeat one follow-up idempotency key | One provider run is created and the stored normalized outcome is replayed |
| CL-13 | Concurrent submission | Send two different follow-ups while idle at nearly the same time | Exactly one is claimed; the other receives `CHAT_RUN_ALREADY_ACTIVE` without provider contact |
| CL-14 | Refresh while idle | Reload the app in `ready_for_follow_up` | Session history and actionable follow-up state rehydrate without provider references leaking |
| CL-15 | Disconnect while idle | Disconnect and reconnect before a follow-up | Canonical session reconciliation succeeds and the next run retains context |
| CL-16 | Disconnect after submit | Lose the adapter connection around provider acknowledgement | Reconciliation identifies the accepted run or returns `CHAT_FOLLOW_UP_DELIVERY_UNKNOWN`; no automatic duplicate is sent |
| CL-17 | Gateway restart while idle | Restart Gateway with no active run | Session either resumes with retained context or closes explicitly; it never silently starts a new unrelated session |
| CL-18 | Gateway restart while active | Restart during a harmless active run | Run reconciles authoritatively or fails closed with no success claim |
| CL-19 | Execution-service restart while idle | Restart RAGenius after a completed turn | Durable scope/session state rehydrates only when provider version and canonical session still match |
| CL-20 | Invalid or missing session | Corrupt/delete the provider session before follow-up | Follow-up fails with bounded reconciliation diagnostics and does not create a replacement session |
| CL-21 | Turn timeout | Run exceeds the configured harmless timeout | Current run fails; session continuation is disabled until reconciliation completes |
| CL-22 | Scope isolation | Attempt follow-up with wrong app, session, execution, user, or service scope | Every mismatch fails before provider contact and reveals no session existence |
| CL-23 | Policy non-escalation | Change a read-only workflow into filesystem/network/external-write work | Follow-up returns `CHAT_FOLLOW_UP_REQUIRES_NEW_EXECUTION` and performs no provider call |
| CL-24 | Artifact and skill stability | Try to add an artifact or change selected skill in a follow-up | Request requires a new execution; original session governance remains unchanged |
| CL-25 | Session closure | End an idle session, then submit another follow-up | Session closes once and all later turns fail with `CHAT_SESSION_CLOSED` |
| CL-26 | Idle expiry | Leave an idle session past configured TTL | Session closes normally with expiry evidence and no provider call |
| CL-27 | Event and history integrity | Inspect all runs and turns | Monotonic RAGenius events show each run and outcome; raw provider refs, secrets, and reasoning are absent from app APIs |
| CL-28 | Unsupported version | Run preflight against an unsupported fixture/version | Chat-level capability is not advertised and execution fails before session creation |

## Required Gate

All CL-01 through CL-28 must pass, or the provider must demonstrate the exact
documented fail-closed behavior. CL-05 through CL-09 are the minimum functional
TaskFlow proof. CL-11 through CL-28 are mandatory production gates.

The gate does not require:

- a typed clarification/selection event;
- same-run resumption;
- a custom request-input plugin;
- exactly-once external side effects.

## Evidence Record

For every live case record:

- OpenClaw and TaskFlow versions and approved fingerprints;
- RAGenius execution, Agent-session, and turn identifiers;
- hashed canonical session identity, never the raw key in public evidence;
- provider run-id hashes and status;
- elapsed time and reconciliation method;
- bounded redacted final message or error;
- cleanup result and restored Gateway policy.

## Decision

If the required gate passes, write the staged implementation plan for the
contract and design. If it fails, keep chat-level interaction disabled and
record whether the blocker belongs to session continuity, follow-up dispatch,
recovery, policy enforcement, or TaskFlow activation.
