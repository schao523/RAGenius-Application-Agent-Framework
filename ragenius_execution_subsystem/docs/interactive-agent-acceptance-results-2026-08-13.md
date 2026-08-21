# Interactive Agent Execution Acceptance Results

Date: 2026-08-13

## Scope

This record covers Task 9 acceptance for the provider-neutral interactive
Agent execution channel. Identifiers are synthetic or redacted. Provider
credentials, provider session handles, and raw authentication payloads are not
included.

## Automated Acceptance

| Area | Result | Evidence |
| --- | --- | --- |
| Execution subsystem | Pass | Full test suite, build, lint, typecheck, and Prisma schema validation passed. |
| Recovery | Pass | Durable `starting`, `running`, and `waiting_for_interaction` sessions fail closed after restart; pending interactions are cancelled and no provider response is replayed. |
| Security | Pass | Provider-event allowlisting and size bounds, unsupported interaction rejection, spoofed authorization rejection, replay protection, scoped access, and cancellation races passed. |
| App backend | Pass | 125 tests passed and 1 was skipped, including approval, clarification, refresh while waiting, lane persistence, and cancellation flows. |
| App frontend | Pass | 153 tests and the production build passed, including provider-neutral interaction rendering and response handling. |
| Builder | Pass | 118 tests plus 2 subtests passed. Existing `datetime.utcnow` deprecation warnings remain. |

## Live Provider Acceptance

### Codex App-Server

- Version: Codex CLI `0.146.0`.
- Fresh Task 9 smoke: app-server initialization passed and a bounded read-only
  turn completed through the production adapter.
- Earlier same-branch feasibility evidence passed two-turn continuation,
  dynamic selection through `ragenius_request_input`, disposable command
  approval, multiple interactions in one turn, and correlated cancellation.
- Result: accepted behind the disabled-by-default interactive feature flag and
  startup capability preflight.

### OpenClaw Gateway

- Version: OpenClaw CLI and Gateway `2026.6.8`.
- Gateway status at Task 9 verification: active, loopback-only, configuration
  audit clean, and CLI device authentication admin-capable.
- Earlier same-branch production-client evidence passed continuation,
  cancellation, allow-once exactly once, deny without execution, expiry,
  duplicate-resolution idempotency, scope reduction, and restoration to the
  normal `full/on-miss/deny` profile.
- Fresh Task 9 smoke: passed live completion and correlated cancellation through
  the production Gateway client. The credential was read from WSL with approved
  host access, held only in the test process environment, and never logged or
  written by RAGenius.
- An earlier token-mismatch result was caused by a sandbox-denied WSL read whose
  error text was mistakenly supplied as the token. It was not Gateway credential
  drift. No credential or execution policy was changed to obtain the passing run.
- Result: OpenClaw interactive session and cancellation transport is accepted
  behind its disabled-by-default feature flag. Approval acceptance additionally
  requires the documented administrator-controlled temporary policy profile.

## Recovery And Rollback

- Startup reconciliation never attempts blind provider replay. Interrupted
  non-terminal sessions transition to a stable failed state with
  `AGENT_EXECUTION_INTERRUPTED`.
- Interactive transports remain disabled by default. Removing either provider
  flag restores one-shot execution without changing provider policy.
- The startup script validates OpenClaw's protected credential when interactive
  OpenClaw is enabled and never mutates the Gateway execution policy.

## Known Limitations

- OpenClaw does not advertise structured clarification or selection. Those
  capabilities remain unavailable because the separate Task 10 feasibility
  experiment and any subsequently approved production design.
- Codex app-server is experimental. Supported-version and capability preflight
  must remain fail closed during upgrades.
- External deployments still require a separately provisioned credential with
  the documented scopes; a local configuration token is test evidence, not a
  production credential-distribution design.
