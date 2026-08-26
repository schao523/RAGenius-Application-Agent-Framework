# Codex Interactive Skill, Plugin, And MCP Runbook

Date: 2026-08-26

## Safety Baseline

All new capabilities are disabled by default. Enable one capability at a time only in a controlled test environment. Never put service tokens, OAuth tokens, cookies, authentication URLs, OTPs, or recovery codes in these JSON settings or in test evidence.

The execution subsystem and app backend must use service authentication with the `execution` scope before interactive launch routes are exposed. Restart the execution subsystem after changing any setting.

## Runtime Settings

```powershell
$env:CODEX_MCP_ELICITATION_ENABLED = "false"
$env:CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED = "false"
$env:CODEX_INTERACTIVE_USER_ACTION_ENABLED = "false"
$env:CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON = '[]'
$env:CODEX_MANAGED_AUTH_TARGETS_JSON = '[]'
```

`CODEX_MCP_ELICITATION_ENABLED` enables the version-gated decoder for bounded `form`, `openai/form`, and URL elicitation. Unsupported schemas fail closed.

`CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED` permits authentication handoff only when an administrator-configured target also has an installed trusted verifier. The current production composition registers no verifier, so authentication targets remain unavailable even when this flag is true.

`CODEX_INTERACTIVE_USER_ACTION_ENABLED` permits bounded non-secret manual-action requests. A user acknowledgement is not external-write authorization; Codex must verify observable state afterward.

`CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON` is an array of exact lowercase ASCII hosts. Wildcards, schemes, paths, ports, Unicode names, and URL fragments are invalid.

`CODEX_MANAGED_AUTH_TARGETS_JSON` has this shape:

```json
[
  {
    "id": "administrator-target-id",
    "label": "Administrator-defined label",
    "launch": {
      "kind": "https_url",
      "url": "https://approved.example/signin"
    },
    "allowedHosts": ["approved.example"],
    "verifierId": "installed-verifier-id"
  }
]
```

For a trusted application window, `launch` instead uses:

```json
{
  "kind": "provider_window",
  "provider": "computer_use",
  "application": "Administrator-defined application label"
}
```

Configuration alone never makes a target eligible. `verifierId` must resolve to a trusted, non-mutating verifier injected by the execution subsystem composition root.

## Activation Order

1. Confirm `CODEX_APP_SERVER_INTERACTIVE_ENABLED=true` and a supported Codex app-server version.
2. Confirm service authentication is required and the app credential has the `execution` scope.
3. Enable only `CODEX_MCP_ELICITATION_ENABLED`; restart and run approval accept, deny, and cancel tests.
4. Enable `CODEX_INTERACTIVE_USER_ACTION_ENABLED`; restart and run a non-secret manual-action test.
5. Do not enable authentication handoff until a real verifier is installed and its target passes exact-host validation.
6. Record sanitized evidence before enabling any capability in production.

The startup script prints only effective booleans and configured host/target counts. It never prints hosts, targets, verifier IDs, or launch URLs. This summary is the safe capability inspection method.

## Rollback

Set all three feature flags to `false`, set both JSON arrays to `[]`, and restart the execution subsystem. Existing one-shot Agent mode, structured clarification/selection, and OpenClaw behavior remain unchanged. Pending provider requests are not reconstructed after restart; interrupted executions fail closed.

## Failure Interpretation

- `MCP_ELICITATION_UNSUPPORTED`: request shape or version is unsupported.
- `AUTHENTICATION_HANDOFF_NOT_VERIFIED`: complete sign-in and retry only if a trusted verifier is installed.
- `INTERACTION_LAUNCH_UNAVAILABLE`: scope, state, version, ticket, host, or target validation failed.
- `MCP_OPERATION_BLOCKED`: a required MCP operation was denied, cancelled, or failed; later assistant prose cannot convert it to success.
- `AGENT_OPERATION_VERIFICATION_FAILED`: required operation evidence is absent or cannot be correlated safely.
