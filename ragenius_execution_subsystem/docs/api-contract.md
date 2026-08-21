# RAGenius Execution Subsystem API Contract

## Implemented Routes

### `GET /healthz`

Returns:

```json
{ "status": "ok" }
```

### `GET /readyz`

Returns:

```json
{
  "status": "ready",
  "checks": {
    "database": "not_configured"
  }
}
```

### `POST /v1/executions`

Request:

```json
{
  "request_type": "execute_skill",
  "app_id": "app_001",
  "session_id": "sess_001",
  "skill_id": "video_director_skill",
  "input": {
    "prompt": "Explain RAG simply",
    "duration": 30
  }
}
```

Responses:

- `200` completed
- `200` dry run
- `202` pending confirmation
- `400` validation error
- `403` permission blocked
- `404` unknown or disabled skill

When the execution subsystem is configured with `BUILDER_BASE_URL`, skill resolution may fall back to a builder-managed published skill that is explicitly bound to the requesting app.

### `GET /v1/skills`

Returns registered skill metadata.

### `GET /v1/skills/:skill_id`

Returns detailed metadata for a single skill.

### `GET /v1/tools`

Returns registered tool metadata.

### `POST /v1/tools/discover/mcp`

Request:

```json
{
  "provider_id": "mcp_mock_001"
}
```

Returns mock discovered tools mapped into the internal tool schema.

### `GET /v1/executions/:execution_id`

Returns the scoped execution status. Requires `app_id` and `session_id`.

### `GET /v1/executions/:execution_id/logs`

Returns scoped redacted execution logs.

## Interactive Agent Routes

All routes require a service credential with the `execution` scope and exact
`app_id` plus `session_id` query scope. Provider handles and correlation
references are never returned.

### `GET /v1/executions/:execution_id/interactions`

Returns normalized interactions with type, state, version, prompt, bounded
options, expiry, and public sequence. A wrong scope returns `404`.

### `GET /v1/executions/:execution_id/events`

Accepts `after_sequence` and `limit` (maximum 200). Returns normalized events
and `next_after_sequence` for cursor polling.

### `POST /v1/executions/:execution_id/interactions/:interaction_id/responses`

```json
{
  "expected_version": 1,
  "idempotency_key": "client-generated-stable-key",
  "response": { "kind": "approval", "decision": "allow_once" }
}
```

Supported response kinds are `approval`, `selection`, `clarification`, and
`user_action`. Stale versions, expiry, type mismatch, and a second logical
resolution return `409`. An exact idempotent replay returns `200` with
`outcome: replay` and does not contact the provider again.

### `POST /v1/executions/:execution_id/cancel`

Cancels only the exact scoped active execution. `200` means provider
cancellation was confirmed; an unconfirmed cancellation returns `409`.

## Interactive Failure Semantics

- Disabled/unavailable transport: `INTERACTIVE_ADAPTER_UNAVAILABLE`.
- Missing reviewed capability: `INTERACTIVE_CAPABILITY_UNAVAILABLE`.
- Service restart: `AGENT_EXECUTION_INTERRUPTED`.
- Expired interaction: `AGENT_INTERACTION_EXPIRED`.
- Unknown or oversized provider event: `INVALID_PROVIDER_EVENT`.
- No automatic fallback to one-shot execution occurs for a selected skill that
  requires interactive transport.
