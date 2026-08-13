# RAGenius Execution Subsystem Security Guide

## Current Security Guarantees

- Unknown or disabled skills are rejected.
- Unknown tools are rejected.
- Tool input is validated before execution.
- Permission checks run before every tool call.
- `rag_retrieval_tool` is read-only.
- Side-effecting tools require explicit policy.
- `require_confirmation` pauses execution before the tool runs.
- Sensitive fields are redacted in log summaries.
- Interactive APIs require service authentication with the `execution` scope.
- App and session scope is checked on every interaction, event, response, and cancellation request.
- Provider text and provider events cannot authorize an action; only a typed, versioned user response can resolve an interaction.
- Interaction responses are single-use and idempotent. Replays with the same key return the original outcome; another logical response conflicts.
- Authentication handoff accepts only `completed` or `cancelled`; secrets are never accepted as interaction input.
- Unknown and oversized provider events fail the execution closed.
- Service restart fails nonterminal interactive sessions without replaying a response.

## Redacted Fields

- `authorization`
- `cookie`
- `set-cookie`
- `api_key`
- `apikey`
- `access_token`
- `refresh_token`
- `password`
- `secret`
- `private_key`
- bearer-token-like strings

## Interactive Agent Controls

Interactive transports are disabled by default with
`CODEX_APP_SERVER_INTERACTIVE_ENABLED=false` and
`OPENCLAW_GATEWAY_INTERACTIVE_ENABLED=false`. Enabling a transport does not
weaken the existing policy classifier or change provider policy.

Provider preflight checks the configured protocol version, transport,
interaction types, cancellation support, and reviewed recovery class. A
selected skill fails with `INTERACTIVE_CAPABILITY_UNAVAILABLE` when its
published requirements exceed the active adapter. It does not fall back to an
autonomous provider because that would remove required user mediation.

Interaction prompts are limited to 2,000 characters, clarification responses
to 8,000 characters, option sets to 20 items, provider protocol messages to
the configured transport limit, and normalized provider event payloads to
65,536 UTF-8 bytes.

On restart, durable `starting`, `running`, and `waiting_for_interaction`
sessions become failed with `AGENT_EXECUTION_INTERRUPTED`; pending interactions
are cancelled. Current adapters do not synthesize, infer, or replay an answer.

## OpenClaw Policy Boundary

RAGenius never changes OpenClaw policy. The normal one-shot profile is
`security: full`, `ask: on-miss`, `askFallback: deny`. Disposable interactive
approval acceptance uses `security: allowlist`, `ask: on-miss`,
`askFallback: deny` only after an administrator changes the profile, restarts
the Gateway, and verifies the effective policy. The protected Gateway
credential requires the externally configured approval scopes and never
crosses into the app or browser. See
`docs/openclaw-execution-policy-profiles.md`.

## Rollback

Disable both interactive feature flags, restart the execution subsystem,
restore and verify the normal OpenClaw profile, then run read-only one-shot
smoke tests. Existing one-shot Agent execution remains available; an
interactive execution interrupted by rollback fails explicitly and must be
retried.

## High-Risk Tool Policy

- `rag_adapter` read-only retrieval can be auto-allowed
- side-effecting API tools require explicit policy
- discovered MCP write tools are treated as side-effecting

## Dry Run Safety

Dry run validates request, skill, tool availability, and permissions, but does not execute side-effecting tools.
