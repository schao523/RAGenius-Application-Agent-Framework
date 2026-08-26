# Codex Interactive MCP Live Results

Date opened: 2026-08-25  
Last updated: 2026-08-26

## Implementation Gate

Automated implementation and compatibility gates passed before live rollout:

- Execution subsystem: 520 tests, 512 passed, 8 live tests skipped; lint and typecheck passed.
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
implemented. Live user-facing authentication handoff acceptance remains
pending.

## Live Matrix

| Row | Capability | State | Execution ID | Evidence required before pass |
| --- | --- | --- | --- | --- |
| 1 | Gmail MCP approval accept | Pending explicit live test | Not run | One uniquely marked message; one provider response; no duplicate send |
| 2 | Gmail MCP approval deny | Pending explicit live test | Not run | No message; failed or blocked normalized result |
| 3 | Gmail MCP approval cancel | Pending explicit live test | Not run | No message; authoritative cancellation |
| 4 | Approved URL authentication handoff | Ready for controlled live test | Not run | Scoped no-store launch, verifier success, same-turn resume |
| 5 | Unknown or blocked authentication target | Ready for controlled live test | Not run | No browser/application launch and bounded diagnostic |
| 6 | Managed instruction-skill authentication | Ready after approved target configuration | Not run | Approved target, verifier success, and same-turn continuation |
| 7 | Computer Use manual action | Pending explicit live test | Not run | User acknowledgement followed by provider-observed verification |
| 8 | Duplicate interaction response | Pending explicit live test | Not run | One provider response and at most one external write |

## Evidence Rules

Record only execution ID, timestamp, normalized status, interaction type, bounded diagnostic code, operation evidence, and duplicate count. Do not record recipient addresses, message bodies beyond a unique test marker, tokens, cookies, authentication URLs, query strings, schemas, `_meta`, OTPs, or recovery codes.

Production capability flags must remain disabled until the relevant row passes.
Authentication rows require an administrator-approved target referencing
`codex-apps-gmail-auth`; verifier installation alone is not activation.
