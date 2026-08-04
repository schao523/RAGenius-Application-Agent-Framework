# Phase 3.1 Design: Real Gmail MCP Support

## Purpose

Phase 3.1 extends the existing Phase 3 MCP seam from mock-backed behavior to one real provider:

- Gmail MCP over remote HTTP
- endpoint: `https://gmailmcp.googleapis.com/mcp/v1`
- auth: OAuth2 Bearer token
- integration model: single shared service identity

This is a vertical slice, not a general MCP completion effort.

## Scope

Phase 3.1 will add:

- real MCP HTTP lifecycle support in `ragenius_execution_subsystem`
- Gmail MCP provider configuration
- real `initialize`, `notifications/initialized`, `tools/list`, and `tools/call`
- explicit discovery and allowlisting of Gmail tools
- read-only Gmail execution first
- permission-scoped registration of discovered Gmail tools
- Builder normalization support for Gmail read operations as `review_required`

Phase 3.1 will not add:

- per-user OAuth
- Gmail write/send flows yet
- arbitrary MCP provider support beyond the generic seam plus Gmail target
- auto-finalization of Gmail contracts in Builder

## Goals

- Prove one real MCP provider works end to end
- Keep Builder/runtime architecture unchanged
- Preserve app isolation and explicit permission enforcement
- Avoid over-broad Gmail capability exposure
- Keep the first slice read-only

## Non-Goals

- No send mail in the first slice
- No create draft in the first slice
- No generic user-provided OAuth token passthrough
- No direct Builder storage of secrets
- No freeform MCP tool inference at runtime

## Configuration Model

Use the existing `MCP_SERVERS_JSON` with Gmail-specific runtime data:

```json
[
  {
    "id": "gmail",
    "transport": "http",
    "baseUrl": "https://gmailmcp.googleapis.com/mcp/v1",
    "authTokenEnv": "GMAIL_MCP_ACCESS_TOKEN",
    "enabled": true
  }
]
```

Runtime secret:

- `GMAIL_MCP_ACCESS_TOKEN`

This token stays in `ragenius_execution_subsystem` runtime env, not Builder.

## Runtime Architecture

### 1. Real HTTP MCP client

Replace the mock-only execution path with a real client seam for HTTP MCP.

Required operations:

- `initialize`
- `notifications/initialized`
- `tools/list`
- `tools/call`

Transport behavior:

- send OAuth bearer token in `Authorization` header
- support MCP session handling if the server returns session identifiers
- keep connection logic provider-scoped by `provider_id`

### 2. Gmail provider registration

Gmail remains just one MCP provider in config:

- provider id: `gmail`

Discovery flow:

1. runtime connects to Gmail MCP
2. runtime initializes session
3. runtime requests `tools/list`
4. runtime filters the returned tools through a local allowlist
5. runtime registers the allowed tools into `ToolRegistry`

### 3. Allowlist model

Do not expose every discovered Gmail tool automatically.

Phase 3.1 should register only allowlisted read tools, for example:

- search/list messages
- get message
- get thread
- list labels

Exact tool ids depend on the actual Gmail MCP `tools/list` response.

### 4. Tool id mapping

Preserve explicit provider-scoped ids in registry:

- `mcp.gmail.<tool_name>`

Example:

- `mcp.gmail.search_messages`
- `mcp.gmail.get_thread`

No alias layer yet. Keep Phase 3.1 simple and explicit.

## Permission Model

All Gmail MCP tools remain explicit and permission-scoped.

Read-only Gmail tools:

- `external_api.read`

Write Gmail tools:

- reserved for later
- would use `external_api.write`
- would require confirmation

Phase 3.1 policy:

- read-only Gmail skills are always `review_required` in Builder
- execution may still be `auto_allow` or `restricted` by runtime policy, but not auto-finalized by Builder

## Builder Normalization

Builder should gain a narrow Gmail read-only inference family, for example:

- `gmail_read_operation`

Supported intent examples:

- search Gmail messages
- list recent emails
- inspect matching threads

Builder behavior:

- infer candidate Gmail MCP read tools only if Gmail provider/tool ids are known in runtime contract assumptions
- generate explicit `required_tools`
- generate explicit draft workflow
- mark all Gmail contracts `review_required`
- never auto-finalize Gmail Phase 3.1 skills

## Workflow Shape

No new workflow primitive is required beyond the current Phase 3 seam.

Use:

- `service_call` for Gmail MCP invocation

Example shape:

1. validate input
2. `service_call` to `mcp.gmail.search_messages`
3. end

This keeps MCP invocation explicit and consistent with the current service boundary.

## Observability

Execution summaries should include:

- `provider_id = gmail`
- discovered tool id used
- whether the tool was read-only
- MCP transport failure classification when applicable

Failure classes to handle explicitly:

- provider not configured
- auth missing
- auth rejected
- MCP initialize failure
- `tools/list` failure
- `tools/call` failure
- unsupported tool not allowlisted

## Error Handling

Map Gmail MCP failures into RAGenius runtime errors:

- auth/config problem -> `MCP_PROVIDER_AUTH_FAILED` or `MCP_PROVIDER_NOT_CONFIGURED`
- initialization failure -> `MCP_INITIALIZE_FAILED`
- discovery failure -> `MCP_DISCOVERY_FAILED`
- call failure -> `MCP_TOOL_CALL_FAILED`
- allowlist rejection -> `MCP_TOOL_NOT_ALLOWED`

Do not leak raw bearer tokens or raw auth headers in logs.

## Test Strategy

### Unit tests

- HTTP MCP client initialize flow
- bearer token header injection
- `tools/list` mapping into `ToolRegistry`
- allowlist filtering
- `tools/call` result normalization

### Integration tests

- discover Gmail tools through mocked HTTP MCP responses
- execute one read-only Gmail sample skill end to end
- verify disabled/unconfigured Gmail provider fails closed
- verify missing token fails cleanly
- verify non-allowlisted discovered tool is not exposed

### Sample skill

Add one sample skill such as:

- `gmail_message_search`

Input:

- `query`

Output:

- normalized message/thread list

Required tool:

- discovered Gmail read tool id

Result type:

- `json`

## Acceptance Criteria

Phase 3.1 is complete when:

- `ragenius_execution_subsystem` can connect to Gmail MCP over HTTP
- bearer token auth works through runtime env config
- Gmail `tools/list` can be fetched and filtered
- at least one Gmail read-only tool is registered in `ToolRegistry`
- at least one Gmail read-only skill executes successfully end to end
- Builder can normalize a Gmail read-only skill draft as `review_required`
- tests cover discovery, execution, auth failure, and allowlist filtering

## Recommended Implementation Order

1. Add real HTTP MCP client seam
2. Add Gmail runtime config usage with bearer auth
3. Implement `initialize` + `tools/list`
4. Add allowlist filtering and registry mapping
5. Implement `tools/call`
6. Add one sample Gmail read-only skill
7. Add Builder Gmail read-only normalization
8. Add tests and docs

## Recommendation

Start with one concrete Gmail read capability only:

- message search or thread search

Do not include Gmail write in Phase 3.1. The right follow-up slice is:

- **Phase 3.2: Gmail draft creation with confirmation gating**
