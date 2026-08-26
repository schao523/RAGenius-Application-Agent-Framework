# Managed Authentication Verifier Registry Design

## Scope

This design adds a trusted verifier registry to `ragenius_execution_subsystem`
and one concrete verifier for the Gmail connection used by Codex interactive
Agent execution. It does not add Builder MCP administration, arbitrary verifier
plugins, or authentication support for OpenClaw.

## Observed Basis

Codex app-server `0.146.0` generated bindings expose:

- `mcpServerStatus/list`, scoped by `threadId`, with each server's
  `authStatus` and tool inventory;
- `mcpServer/tool/call`, scoped by the same `threadId`;
- authentication states `unsupported`, `notLoggedIn`, `bearerToken`, and
  `oAuth`.

A sanitized live probe on 2026-08-26 found Gmail under the `codex_apps` MCP
server. The server reported `bearerToken`, exposed `gmail.get_profile`, and a
same-thread call to that read-only tool returned a non-error structured result.
The separately configured `GMAIL_MCP_ACCESS_TOKEN` belongs to RAGenius's direct
MCP tool provider and must not be used to attest Codex authentication.

## Decision

Use a compile-time trusted verifier registry. A configured managed
authentication target becomes eligible only when its `verifierId` resolves to
an installed verifier. Verifiers receive a restricted provider-owned
verification context tied to the protected execution handle. They never receive
credentials and cannot select arbitrary commands or URLs from model output.

The first verifier has id `codex-apps-gmail-auth`. It verifies the Gmail
credential domain used by the active Codex thread by:

1. listing MCP server status with that exact `threadId` and
   `detail: "toolsAndAuthOnly"`;
2. requiring the `codex_apps` server, an authenticated status, and the
   `gmail.get_profile` tool;
3. calling `gmail.get_profile` with fixed empty arguments through that same
   thread;
4. accepting only a non-error response with bounded evidence;
5. returning a bounded diagnostic code without persisting profile data,
   response content, URLs, or credentials.

## Interfaces

`ManagedAuthenticationVerifierRegistry` owns immutable verifier lookup:

```ts
class ManagedAuthenticationVerifierRegistry {
  constructor(verifiers: readonly ManagedAuthenticationVerifier[]);
  get(id: string): ManagedAuthenticationVerifier | undefined;
  has(id: string): boolean;
  asReadonlyMap(): ReadonlyMap<string, ManagedAuthenticationVerifier>;
}
```

Construction rejects blank ids and duplicate ids. The registry does not support
runtime mutation or dynamic imports.

The verifier input gains a provider-neutral discriminated verification context:

```ts
type ManagedAuthenticationVerificationContext = {
  backend: "codex_cli";
  codexMcp: {
    listServerStatus(): Promise<readonly CodexMcpServerVerificationStatus[]>;
    callReadOnlyTool(input: {
      server: string;
      tool: string;
      arguments: Readonly<Record<string, unknown>>;
    }): Promise<CodexMcpVerificationToolResult>;
  };
};
```

The adapter builds this facade from the protected transport and thread id. The
facade is not exposed through API responses or persisted interaction records.
Only installed verifier code can call it.

## Gmail Verification Semantics

Successful verification requires all of the following:

- backend is `codex_cli`;
- `codex_apps` is present for the active thread;
- `authStatus` is `bearerToken` or `oAuth`;
- `gmail.get_profile` is present;
- its fixed `{}` call does not throw and does not return `isError: true`;
- the result contains at least one content block or structured content.

Failures return one of these bounded diagnostic codes:

- `codex_mcp_context_unavailable`
- `gmail_mcp_server_unavailable`
- `gmail_mcp_not_authenticated`
- `gmail_profile_probe_unavailable`
- `gmail_profile_probe_failed`
- `gmail_profile_probe_invalid`

No raw provider error or response content is returned to the client.

## Composition And Configuration

The production composition root installs the trusted Gmail verifier and passes
the registry's read-only map to `CodexAppServerAdapter`. Installation alone does
not advertise authentication handoff. The capability remains disabled unless:

- `CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED=true`; and
- `CODEX_MANAGED_AUTH_TARGETS_JSON` contains an approved target referencing
  `codex-apps-gmail-auth`.

Unknown verifier ids remain ineligible. Runtime configuration cannot define a
server name, probe tool, arguments, executable, or verifier implementation.

## New MCP Onboarding Rule

A verifier is not required per tool. One verifier covers one distinct
credential domain and may serve all tools that use that authenticated
connection. A new verifier or trusted descriptor is required only when a new
MCP introduces an interactive credential domain that RAGenius must attest.
Non-interactive API-key/service-token MCPs and MCPs that do not use managed
authentication handoff require no verifier.

Every new verifier must have a provider-owned, non-mutating probe in the same
execution credential context. If no such probe exists, managed authentication
handoff remains unavailable for that MCP.

## Security And Failure Behavior

- Verification is bound to the protected live Codex thread.
- The model cannot provide or alter verifier ids, server names, tools, or probe
  arguments.
- Profile content and credentials are never logged or persisted.
- Timeouts, malformed responses, missing tools, and transport errors fail
  closed.
- Duplicate interaction resolution remains governed by the existing single-use
  state machine; verification cannot produce a second provider response.
- Process restart behavior remains unchanged: a lost protected handle cannot be
  reconstructed and the execution fails safely.

## Testing

Tests cover registry duplicate rejection and immutable lookup; target
eligibility; authenticated, unauthenticated, missing-server, missing-tool,
provider-error, malformed-result, and transport-failure Gmail probes; exact
thread correlation; composition-root registration; redaction; and unchanged
behavior when the feature or target is absent.
