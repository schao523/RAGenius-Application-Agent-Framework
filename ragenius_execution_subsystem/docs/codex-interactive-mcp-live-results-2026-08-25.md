# Codex Interactive MCP Live Results

Date opened: 2026-08-25  
Last updated: 2026-08-27

## Implementation Gate

Automated implementation and compatibility gates passed before live rollout:

- Execution subsystem: 530 tests, 522 passed, 8 live tests skipped; lint and typecheck passed.
- App backend: 131 passed, 1 skipped.
- App frontend: 182 passed; production build passed.
- Focused recovery, redaction, scoped launch, Codex adapter, and unchanged OpenClaw Gateway tests passed.

All five rollout settings remain disabled or empty by default. The trusted
`codex-apps-gmail-auth` verifier is installed in the production composition
root, but it advertises no capability unless authentication handoff is enabled
and an approved target references it.

## Gmail Verifier Feasibility Evidence

On 2026-08-26, a sanitized Codex app-server `0.146.0` probe established that:

- Gmail is exposed through the `codex_apps` MCP server;
- the active connection reported `bearerToken`;
- `gmail.get_profile` was available;
- a same-thread call returned a non-error structured result.

The probe emitted no account profile, token, URL, or message data. Automated
registry, verifier, same-thread binding, redaction, and safe-default tests are
implemented. A live managed authentication handoff now verifies and resumes the
same execution successfully.

## Live Matrix

| Row | Capability | State | Execution ID | Evidence required before pass |
| --- | --- | --- | --- | --- |
| 1 | Gmail MCP approval accept | Pass | `execution_1e48ce74e8e0` | One uniquely marked message; one provider response; no duplicate send |
| 2 | Gmail MCP approval deny | Pass | `execution_049b8a382791` | No message; blocked normalized result with `permission_denied` |
| 3 | Gmail MCP approval cancel | Pass | `execution_cb9ec0d04263` | No message; authoritative cancellation |
| 4 | Approved authentication handoff | Pass with output-format caveat | `execution_99dbeefa9695` | Trusted target resolved once, verifier succeeded, and the same execution resumed without exposing provider data |
| 5 | Unknown or blocked authentication target | Pass | `execution_961059c0f818` | No browser/application launch and bounded diagnostic |
| 6 | Managed instruction-skill authentication | Deferred | Not run | Approved target, verifier success, and same-turn continuation |
| 7 | Generic user action with browser control | Deferred | `execution_3626fc999ce0` | Interaction transport passed; provider semantic verification remains unresolved |
| 8 | Duplicate interaction response | Deferred | Not run | One provider response and at most one external write |

## Evidence Rules

Record only execution ID, timestamp, normalized status, interaction type, bounded diagnostic code, operation evidence, and duplicate count. Do not record recipient addresses, message bodies beyond a unique test marker, tokens, cookies, authentication URLs, query strings, schemas, `_meta`, OTPs, or recovery codes.

Production capability flags must remain disabled until the relevant row passes.
Authentication rows require an administrator-approved target referencing
`codex-apps-gmail-auth`; verifier installation alone is not activation.

## Gmail Live Test Run: 2026-08-26

Baseline: repository `41235a5`, Codex CLI `0.146.0`.

Automated gate: 530 tests, 522 passed, 8 live tests skipped; typecheck and lint
passed. The first sandboxed run produced two `spawn EPERM` failures in process
supervision fixtures; the unrestricted rerun passed with zero failures.

| Test | Execution ID | Result | Sanitized evidence |
| --- | --- | --- | --- |
| G-01 safe defaults | `execution_1e2306400cad` | Pass | Managed handoff was disabled, no interaction was created, and the read-only run completed without exposing an account identifier. |
| G-02 read-only profile | `execution_c4cc8ab6e407` | Partial | Gmail connectivity was reported as `GMAIL_PROFILE_CONNECTED`, but Codex added a preamble instead of returning only the requested token. Evidence remained provider-reported. |
| G-03 managed handoff, initial | `execution_7be3319f2522` | Fail closed | The expected `authentication_handoff` interaction was created for `codex-gmail`. Completion returned `AUTHENTICATION_HANDOFF_NOT_VERIFIED`; the Codex app-server then disconnected with code 1. No provider data was exposed. |
| G-03 managed handoff, fixed rerun | `execution_99dbeefa9695` | Pass with output-format caveat | The interaction resolved once, the trusted same-thread status and `gmail.get_profile` probes succeeded, and the same execution completed with `GMAIL_HANDOFF_VERIFIED`. Codex added progress preambles instead of returning only the requested token. No Gmail data or account identifier appeared in execution-subsystem logs. |
| G-04 unknown target | `execution_961059c0f818` | Pass | `unapproved-gmail` returned `AUTHENTICATION_TARGET_NOT_APPROVED`; no interaction or launch occurred. |
| G-05 deny send | `execution_049b8a382791` | Pass | The operation ended blocked with `permission_denied`, `sent: false`, and no message or draft created. |
| G-06 cancel send | `execution_cb9ec0d04263` | Pass | Cancellation was authoritative and no controlled message was sent. |
| G-07 accept send | `execution_1e48ce74e8e0` | Pass | One authorized message was sent to the controlled recipient with no duplicate send. |

The initial G-03 failure was caused by the bounded Codex app-server transport
rejecting the `codex_apps` status response because its single JSON line exceeded
the previous 1 MiB default. The transport then closed, cancelling the pending
authentication request. The fix raises the still-bounded default to 2 MiB and
retrieves MCP server status with one-entry cursor pagination, including repeated
cursor and page-count guards.

The execution subsystem was restarted after the test with MCP elicitation,
authentication handoff, user action, allowed hosts, and managed targets disabled
or empty. The startup script currently displays an array count of one for an
empty JSON array in this PowerShell environment; behavioral testing confirmed
that no managed target was active during G-01.

## Deferred Acceptance Work

The following cases are intentionally outside the initial open-source release
gate:

- managed authentication initiated by an approved instruction skill;
- duplicate interaction-response handling under a live provider write;
- browser or Computer Use post-action semantic verification.

The generic user-action transport did create, persist, resolve, and resume the
interaction. In `execution_3626fc999ce0`, the resumed provider issued fresh
tool calls but returned `USER_ACTION_NOT_VERIFIED`. This is not accepted as
semantic verification and must not enable `CODEX_INTERACTIVE_USER_ACTION_ENABLED`
by default.

## Release Activation Decision

The open-source release uses the safe profile: MCP elicitation, managed
authentication handoff, and generic user action are disabled by default, with
empty host and managed-target allowlists. The Gmail path may be enabled only as
an explicit administrator opt-in using the trusted `codex-apps-gmail-auth`
verifier and the controlled configuration in the live test plan. Generic user
action remains disabled until its deferred verification case passes.
